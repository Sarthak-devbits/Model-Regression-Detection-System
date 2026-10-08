"""Golden dataset tools.

Usage (from the repo root):
    uv run python scripts/golden.py validate [VERSION] [--strict]
    uv run python scripts/golden.py stats VERSION
    uv run python scripts/golden.py schema
    uv run python scripts/golden.py new FROM_VERSION TO_VERSION
    uv run python scripts/golden.py freeze VERSION
"""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from shared.golden import VERSION_PATTERN, GoldenDataset, version_number
from shared.golden_quality import Severity, check_dataset, dataset_stats

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "golden"
REGISTRY_PATH = GOLDEN_DIR / "registry.json"
SCHEMA_PATH = GOLDEN_DIR / "schema.json"


# ---------- files ----------


def dataset_path(version: str) -> Path:
    return GOLDEN_DIR / version / "cases.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"versions": {}}
    return read_json(REGISTRY_PATH)


# ---------- loading with friendly errors ----------


def load_for_cli(version: str) -> GoldenDataset | None:
    """Load a dataset, printing readable errors instead of a stack trace."""
    path = dataset_path(version)
    if not path.exists():
        print(f"  error: {path.relative_to(ROOT)} does not exist")
        return None
    try:
        raw = read_json(path)
    except json.JSONDecodeError as exc:
        print(f"  error: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        return None
    try:
        return GoldenDataset.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            message = err["msg"].removeprefix("Value error, ")
            print(f"  error: {describe_location(raw, err['loc'])}: {message}")
        return None


def describe_location(raw: Any, loc: tuple[Any, ...]) -> str:
    """Turn ('cases', 3, 'expected', 'category') into 'gc-0004 -> expected.category'."""
    if len(loc) >= 2 and loc[0] == "cases" and isinstance(loc[1], int):
        try:
            case_id = raw["cases"][loc[1]].get("id", f"cases[{loc[1]}]")
        except (IndexError, KeyError, AttributeError, TypeError):
            case_id = f"cases[{loc[1]}]"
        rest = ".".join(str(part) for part in loc[2:]) or "(case)"
        return f"{case_id} -> {rest}"
    return ".".join(str(part) for part in loc) or "(dataset)"


# ---------- commands ----------


def validate_version(version: str, registry: dict[str, Any], strict: bool) -> bool:
    print(f"\n{version}")
    dataset = load_for_cli(version)
    if dataset is None:
        return False

    ok = True
    if dataset.dataset_version != version:
        print(f"  error: file says dataset_version={dataset.dataset_version}, folder is {version}")
        ok = False

    entry = registry["versions"].get(version)
    if entry is None:
        print(f"  error: {version} is not listed in golden/registry.json")
        ok = False
    elif entry["status"] == "frozen" and entry["content_hash"] != dataset.content_hash():
        next_version = f"v{version_number(version) + 1}"
        print(
            f"  error: {version} is frozen but its content changed. "
            f"Frozen versions are the eval bar and must not change; "
            f"start a new version with: make golden-new FROM={version} TO={next_version}"
        )
        ok = False

    findings = check_dataset(dataset)
    for f in findings:
        where = f"{f.case_id}: " if f.case_id else ""
        print(f"  {f.severity}: [{f.check}] {where}{f.message}")

    errors = sum(1 for f in findings if f.severity is Severity.ERROR)
    warnings = len(findings) - errors
    if errors or (strict and warnings):
        ok = False

    status = entry["status"] if entry else "unregistered"
    verdict = "ok" if ok else "FAILED"
    print(
        f"  {verdict}: {len(dataset.cases)} cases, {errors} errors, {warnings} warnings ({status}{', strict' if strict else ''})"
    )
    return ok


def cmd_validate(args: argparse.Namespace) -> int:
    registry = load_registry()
    versions = [args.version] if args.version else sorted(registry["versions"], key=version_number)
    if not versions:
        print("No versions registered in golden/registry.json")
        return 1
    results = [validate_version(v, registry, args.strict) for v in versions]
    return 0 if all(results) else 1


def cmd_stats(args: argparse.Namespace) -> int:
    dataset = load_for_cli(args.version)
    if dataset is None:
        return 1
    stats = dataset_stats(dataset)
    tags = stats.pop("edge_cases")
    print(f"\n{args.version}: {len(dataset.cases)} cases\n")
    print(f"  {'category':<12}{'easy':>6}{'medium':>8}{'hard':>6}{'total':>7}")
    for category, row in stats.items():
        total = sum(row.values())
        print(f"  {category:<12}{row['easy']:>6}{row['medium']:>8}{row['hard']:>6}{total:>7}")
    print("\n  edge case tags")
    for tag, count in tags.items():
        print(f"  {tag:<16}{count:>4}")
    return 0


def cmd_schema(_: argparse.Namespace) -> int:
    write_json(SCHEMA_PATH, GoldenDataset.model_json_schema(by_alias=True))
    print(f"wrote {SCHEMA_PATH.relative_to(ROOT)}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.to_version in registry["versions"]:
        print(f"error: {args.to_version} already exists")
        return 1
    source = load_for_cli(args.from_version)
    if source is None:
        return 1
    draft = source.model_copy(update={"dataset_version": args.to_version})
    write_json(dataset_path(args.to_version), draft.model_dump(mode="json", by_alias=True))
    registry["versions"][args.to_version] = {
        "status": "draft",
        "based_on": args.from_version,
        "content_hash": None,
        "case_count": None,
        "frozen_at": None,
    }
    write_json(REGISTRY_PATH, registry)
    print(f"created draft {args.to_version} from {args.from_version}")
    print("next: add or fix cases, then note the changes in golden/CHANGELOG.md")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    registry = load_registry()
    entry = registry["versions"].get(args.version)
    if entry is None:
        print(f"error: {args.version} is not registered")
        return 1
    if entry["status"] == "frozen":
        print(f"error: {args.version} is already frozen")
        return 1
    if not validate_version(args.version, registry, strict=True):
        print("\nNot frozen: fix every error and warning first (freezing uses --strict).")
        return 1
    dataset = load_for_cli(args.version)
    assert dataset is not None
    entry.update(
        status="frozen",
        content_hash=dataset.content_hash(),
        case_count=len(dataset.cases),
        frozen_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    write_json(REGISTRY_PATH, registry)
    print(f"\nfroze {args.version}: {len(dataset.cases)} cases, hash {entry['content_hash'][:12]}")
    return 0


# ---------- entry point ----------


def version_arg(value: str) -> str:
    if not re.fullmatch(VERSION_PATTERN, value):
        raise argparse.ArgumentTypeError(f"'{value}' is not a version like v1, v2")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Golden dataset tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate one or all versions")
    p.add_argument("version", nargs="?", type=version_arg)
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="coverage table for one version")
    p.add_argument("version", type=version_arg)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("schema", help="regenerate golden/schema.json")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("new", help="start a new draft version from an existing one")
    p.add_argument("from_version", type=version_arg)
    p.add_argument("to_version", type=version_arg)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("freeze", help="lock a version as an official eval bar")
    p.add_argument("version", type=version_arg)
    p.set_defaults(func=cmd_freeze)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

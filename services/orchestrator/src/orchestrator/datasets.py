"""Load a golden dataset version and turn its cases into worker messages."""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from shared.golden import load_dataset
from shared.runs import CaseTask


class DatasetError(Exception):
    """The requested dataset can't be used for a run."""


@dataclass(frozen=True)
class LoadedDataset:
    version: str
    status: str
    cases: list[CaseTask]


def load_cases(golden_dir: Path, version: str) -> LoadedDataset:
    registry_path = golden_dir / "registry.json"
    if not registry_path.exists():
        raise DatasetError(f"{registry_path} not found")
    entry = json.loads(registry_path.read_text(encoding="utf-8"))["versions"].get(version)
    if entry is None:
        raise DatasetError(f"dataset {version} is not in the registry")

    try:
        dataset = load_dataset(golden_dir / version / "cases.json")
    except (OSError, ValidationError) as exc:
        raise DatasetError(f"dataset {version} could not be loaded: {exc}") from exc

    if entry["status"] == "frozen" and entry["content_hash"] != dataset.content_hash():
        raise DatasetError(f"dataset {version} changed after it was frozen")

    cases = [
        CaseTask(
            case_id=case.id,
            email=case.input.email,
            expected_category=case.expected.category,
            ideal_summary=case.expected.summary,
            difficulty=case.expected_difficulty.value,
        )
        for case in dataset.cases
    ]
    return LoadedDataset(version=version, status=entry["status"], cases=cases)

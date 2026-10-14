import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from shared.golden import load_dataset
from shared.runs import CaseResult, GroupAccuracy, RunMetrics, Verdict
from shared.store import RunStore

REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeDispatcher:
    """Records dispatched runs instead of sending them to Redis."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def dispatch(self, run_id, cases, prompt, judge_prompt) -> None:
        if self.fail:
            raise ConnectionError("redis is down")
        self.calls.append({"run_id": run_id, "cases": cases, "prompt": prompt})


@pytest.fixture
def make_dispatcher() -> Callable[..., FakeDispatcher]:
    return FakeDispatcher


@pytest.fixture
def make_golden(tmp_path: Path) -> Callable[..., Path]:
    """Build a tiny golden dir with two cases, registered as draft or frozen."""

    def _make(status: str = "draft") -> Path:
        golden = tmp_path / "golden"
        (golden / "v1").mkdir(parents=True)
        cases = {
            "dataset_version": "v1",
            "description": "test",
            "labeling_guide_version": 1,
            "cases": [
                {
                    "id": f"gc-000{n}",
                    "input": {"email": f"Test email number {n} about a refund please."},
                    "expected": {"category": "billing", "summary": "Customer wants a refund."},
                    "expected_difficulty": "easy",
                    "notes": "test",
                    "added_in": "v1",
                }
                for n in (1, 2)
            ],
        }
        path = golden / "v1" / "cases.json"
        path.write_text(json.dumps(cases), encoding="utf-8")
        entry = {"status": status, "content_hash": None}
        if status == "frozen":
            entry["content_hash"] = load_dataset(path).content_hash()
        (golden / "registry.json").write_text(json.dumps({"versions": {"v1": entry}}))
        return golden

    return _make


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    target = tmp_path / "prompts"
    shutil.copytree(REPO_ROOT / "prompts", target)
    return target


@pytest.fixture
def complete_run() -> Callable[[Path, str], None]:
    """Pretend the workers finished a run: write one passing result and its metrics."""

    def _complete(database_path: Path, run_id: str) -> None:
        group = GroupAccuracy(total=1, passed=1, accuracy=1.0)
        metrics = RunMetrics(
            total=1,
            passed=1,
            accuracy=1.0,
            by_category={"billing": group},
            by_difficulty={"easy": group},
            judged=0,
            mean_judge_score=None,
            latency_p50_ms=None,
            latency_p95_ms=None,
            input_tokens=0,
            output_tokens=0,
            errors={},
        )
        result = CaseResult(
            case_id="gc-0001",
            difficulty="easy",
            expected_category="billing",
            predicted_category="billing",
            category_correct=True,
        )
        RunStore(database_path).save_results(run_id, [result], metrics, None, Verdict.NO_BASELINE)

    return _complete

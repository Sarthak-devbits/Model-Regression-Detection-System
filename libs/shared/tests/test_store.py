from datetime import UTC, datetime
from pathlib import Path

import pytest

from shared.prompts import PromptConfig
from shared.runs import (
    CaseResult,
    CreateRunRequest,
    GroupAccuracy,
    RunMetrics,
    RunStatus,
    Verdict,
)
from shared.store import RunNotFoundError, RunStore


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "test.sqlite3")


def request(version: str = "v1") -> CreateRunRequest:
    prompt = PromptConfig(version_id=version, created_at=datetime(2026, 1, 1, tzinfo=UTC), system_prompt="x")
    return CreateRunRequest(prompt=prompt, dataset_version="v1")


def metrics(accuracy: float = 1.0) -> RunMetrics:
    group = GroupAccuracy(total=1, passed=int(accuracy), accuracy=accuracy)
    return RunMetrics(
        total=1,
        passed=int(accuracy),
        accuracy=accuracy,
        by_category={"billing": group},
        by_difficulty={"easy": group},
        judged=0,
        mean_judge_score=None,
        latency_p50_ms=None,
        latency_p95_ms=None,
        input_tokens=10,
        output_tokens=5,
        errors={},
    )


def result(case_id: str = "gc-0001", correct: bool = True) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        difficulty="easy",
        expected_category="billing",
        predicted_category="billing" if correct else "general",
        category_correct=correct,
    )


def test_new_run_is_queued(store: RunStore) -> None:
    store.create_run("run_1", request(), judge_version="v1", case_count=1)
    run = store.get_run("run_1")
    assert run.status is RunStatus.QUEUED
    assert run.prompt_version == "v1"
    assert run.metrics is None
    assert run.is_baseline is False


def test_unknown_run_raises(store: RunStore) -> None:
    with pytest.raises(RunNotFoundError):
        store.get_run("nope")


def test_save_results_completes_the_run(store: RunStore) -> None:
    store.create_run("run_1", request(), judge_version="v1", case_count=1)
    store.save_results("run_1", [result()], metrics(), comparison=None, verdict=Verdict.NO_BASELINE)
    run = store.get_run("run_1")
    assert run.status is RunStatus.COMPLETED
    assert run.verdict is Verdict.NO_BASELINE
    assert run.metrics is not None and run.metrics.accuracy == 1.0
    assert run.finished_at is not None
    assert [r.case_id for r in store.get_case_results("run_1")] == ["gc-0001"]


def test_saving_twice_replaces_results_instead_of_duplicating(store: RunStore) -> None:
    store.create_run("run_1", request(), judge_version="v1", case_count=1)
    store.save_results("run_1", [result(correct=True)], metrics(), None, Verdict.NO_BASELINE)
    store.save_results("run_1", [result(correct=False)], metrics(0.0), None, Verdict.NO_BASELINE)
    results = store.get_case_results("run_1")
    assert len(results) == 1
    assert results[0].category_correct is False


def test_baseline_is_per_dataset_and_judge_version_and_can_move(store: RunStore) -> None:
    for run_id in ("run_1", "run_2"):
        store.create_run(run_id, request(), judge_version="v1", case_count=1)
    store.set_baseline("run_1")
    assert store.get_baseline_run_id("v1", "v1") == "run_1"
    store.set_baseline("run_2")
    assert store.get_baseline_run_id("v1", "v1") == "run_2"
    assert store.get_run("run_2").is_baseline is True
    assert store.get_run("run_1").is_baseline is False
    assert store.get_baseline_run_id("v1", "v2") is None


def test_list_runs_newest_first(store: RunStore) -> None:
    for run_id in ("run_a", "run_b", "run_c"):
        store.create_run(run_id, request(), judge_version="v1", case_count=1)
    assert [r.run_id for r in store.list_runs(limit=2)] == ["run_c", "run_b"]


def test_set_status_failed_records_error(store: RunStore) -> None:
    store.create_run("run_1", request(), judge_version="v1", case_count=1)
    store.set_status("run_1", RunStatus.FAILED, error="boom")
    run = store.get_run("run_1")
    assert run.status is RunStatus.FAILED
    assert run.error == "boom"

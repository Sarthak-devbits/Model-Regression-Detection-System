from pathlib import Path

import pytest

from eval_workers import tasks
from eval_workers.classifier_client import CallOutcome
from shared.classification import ClassifierOutput, ClassifyResponse, TokenUsage
from shared.runs import CaseResult, CreateRunRequest, RunStatus, Verdict
from shared.store import RunStore


@pytest.fixture
def fake_classifier(monkeypatch: pytest.MonkeyPatch):
    """Replace the HTTP call with a function returning queued outcomes, and count calls."""
    outcomes: list[CallOutcome] = []
    calls = {"n": 0}

    def fake_call(client, email, prompt) -> CallOutcome:
        calls["n"] += 1
        return outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]

    monkeypatch.setattr(tasks, "call_classifier", fake_call)
    return outcomes, calls


def test_run_case_retries_then_records_the_error(fake_classifier, case_task) -> None:
    outcomes, calls = fake_classifier
    outcomes.append(CallOutcome("retryable", error="llm_unavailable"))
    result = tasks.run_case.apply(args=("run_1", case_task.model_dump(mode="json"), {})).get()
    assert calls["n"] == tasks.settings.task_max_retries + 1
    assert result["error"] == "llm_unavailable"
    assert result["category_correct"] is False


def test_run_case_recovers_after_one_retry(fake_classifier, case_task) -> None:
    outcomes, calls = fake_classifier
    response = ClassifyResponse(
        output=ClassifierOutput(category="billing", summary="Refund a double charge."),
        prompt_version="v1",
        model="m",
        latency_ms=300.0,
        usage=TokenUsage(input_tokens=100, output_tokens=10),
    )
    outcomes.extend([CallOutcome("retryable", error="llm_unavailable"), CallOutcome("ok", response)])
    result = tasks.run_case.apply(args=("run_1", case_task.model_dump(mode="json"), {})).get()
    assert calls["n"] == 2
    assert result["category_correct"] is True
    assert result["error"] is None


def test_judge_case_skips_cases_without_summary(case_task) -> None:
    failed = CaseResult(case_id="gc-0001", difficulty="easy", expected_category="billing", error="x").model_dump(mode="json")
    result = tasks.judge_case.apply(args=(failed, "run_1", case_task.model_dump(mode="json"), {})).get()
    assert result == failed


def test_judge_case_with_fake_judge(monkeypatch: pytest.MonkeyPatch, case_task) -> None:
    monkeypatch.setattr(tasks.settings, "llm_provider", "fake")
    produced = CaseResult(
        case_id="gc-0001",
        difficulty="easy",
        expected_category="billing",
        predicted_category="billing",
        category_correct=True,
        summary=case_task.ideal_summary,
    ).model_dump(mode="json")
    rubric = {
        "version_id": "v1",
        "created_at": "2026-01-01T00:00:00Z",
        "system_prompt": "Grade it.",
    }
    result = tasks.judge_case.apply(args=(produced, "run_1", case_task.model_dump(mode="json"), rubric)).get()
    assert result["judge_score"] == 5


def test_aggregate_without_baseline(tmp_path: Path, make_result, prompt_request) -> None:
    store = RunStore(tmp_path / "db.sqlite3")
    store.create_run("run_1", prompt_request, judge_version="v1", case_count=2)
    verdict = tasks.aggregate("run_1", [make_result("gc-0001"), make_result("gc-0002")], store)
    assert verdict is Verdict.NO_BASELINE
    assert store.get_run("run_1").status is RunStatus.COMPLETED


def test_aggregate_against_baseline_detects_regression(tmp_path: Path, make_result, prompt_request) -> None:
    store = RunStore(tmp_path / "db.sqlite3")
    good = [make_result(f"gc-{i:04d}") for i in range(1, 11)]
    store.create_run("run_base", prompt_request, judge_version="v1", case_count=10)
    tasks.aggregate("run_base", good, store)
    store.set_baseline("run_base")

    worse = [*good[:9], make_result("gc-0010", predicted="general")]
    store.create_run("run_new", prompt_request, judge_version="v1", case_count=10)
    verdict = tasks.aggregate("run_new", worse, store)

    run = store.get_run("run_new")
    assert verdict is Verdict.CRITICAL  # 100% -> 90% is a 10-point drop
    assert run.comparison is not None
    assert run.comparison.accuracy_delta_pp == -10.0
    assert [f.case_id for f in run.comparison.regressions] == ["gc-0010"]


@pytest.fixture
def prompt_request() -> CreateRunRequest:
    return CreateRunRequest.model_validate(
        {
            "prompt": {
                "version_id": "v1",
                "created_at": "2026-01-01T00:00:00Z",
                "system_prompt": "Classify.",
            },
            "dataset_version": "v1",
        }
    )


def test_outage_makes_the_run_inconclusive_not_a_regression(tmp_path: Path, make_result, prompt_request) -> None:
    store = RunStore(tmp_path / "db.sqlite3")
    store.create_run("run_1", prompt_request, judge_version="v1", case_count=3)
    results = [
        make_result("gc-0001"),
        make_result("gc-0002", predicted=None, error="llm_unavailable"),
        make_result("gc-0003", predicted=None, error="classifier_unreachable: ConnectError"),
    ]
    verdict = tasks.aggregate("run_1", results, store)
    run = store.get_run("run_1")
    assert verdict is Verdict.INCONCLUSIVE
    assert run.comparison is None
    assert run.error is not None and "67%" in run.error


def test_invalid_model_output_is_not_an_infrastructure_error(make_result) -> None:
    results = [make_result("gc-0001", predicted=None, error="invalid_model_output")]
    assert tasks.infrastructure_error_rate(results) == 0.0

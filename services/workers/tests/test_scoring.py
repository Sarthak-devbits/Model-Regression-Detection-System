from eval_workers.classifier_client import CallOutcome
from eval_workers.scoring import build_case_result, compute_metrics, percentile, retry_delay
from shared.classification import ClassifierOutput, ClassifyResponse, TokenUsage


def ok_outcome(category: str) -> CallOutcome:
    response = ClassifyResponse(
        output=ClassifierOutput(category=category, summary="A summary."),
        prompt_version="v1",
        model="m",
        latency_ms=250.0,
        usage=TokenUsage(input_tokens=100, output_tokens=10),
    )
    return CallOutcome("ok", response=response)


def test_correct_prediction(case_task) -> None:
    result = build_case_result(case_task, ok_outcome("billing"))
    assert result.category_correct is True
    assert result.summary == "A summary."
    assert (result.latency_ms, result.input_tokens) == (250.0, 100)


def test_wrong_prediction(case_task) -> None:
    result = build_case_result(case_task, ok_outcome("general"))
    assert result.category_correct is False
    assert result.predicted_category == "general"


def test_failed_call_counts_as_incorrect_with_error(case_task) -> None:
    outcome = CallOutcome("invalid_output", error="invalid_model_output", raw_output="oops")
    result = build_case_result(case_task, outcome)
    assert result.category_correct is False
    assert result.error == "invalid_model_output"
    assert result.raw_output == "oops"
    assert result.summary is None


def test_percentile_nearest_rank() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 100.0
    assert percentile([], 50) is None


def test_metrics_summarise_a_run(make_result) -> None:
    results = [
        make_result("gc-0001", "billing", "billing", judge_score=5, latency_ms=100.0),
        make_result("gc-0002", "billing", "general", judge_score=3, latency_ms=300.0),
        make_result("gc-0003", "technical", "technical", difficulty="hard", latency_ms=200.0),
        make_result("gc-0004", "account", None, error="llm_unavailable"),
    ]
    m = compute_metrics(results)
    assert (m.total, m.passed, m.accuracy) == (4, 2, 0.5)
    assert m.by_category["billing"].accuracy == 0.5
    assert m.by_category["technical"].accuracy == 1.0
    assert m.by_difficulty["hard"].passed == 1
    assert (m.judged, m.mean_judge_score) == (2, 4.0)
    assert m.latency_p50_ms == 200.0
    assert m.errors == {"llm_unavailable": 1}


def test_retry_delay_doubles_and_caps() -> None:
    assert [retry_delay(n) for n in range(6)] == [5, 10, 20, 40, 80, 120]

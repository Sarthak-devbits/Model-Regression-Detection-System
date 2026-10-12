"""Turn raw call outcomes into case results, and case results into run metrics."""

import math
from collections import Counter, defaultdict

from eval_workers.classifier_client import CallOutcome
from shared.runs import CaseResult, CaseTask, GroupAccuracy, RunMetrics


def build_case_result(task: CaseTask, outcome: CallOutcome) -> CaseResult:
    """Score one case: exact category match, plus latency and tokens when available."""
    base = CaseResult(case_id=task.case_id, difficulty=task.difficulty, expected_category=task.expected_category)
    if outcome.kind != "ok" or outcome.response is None:
        return base.model_copy(update={"error": outcome.error, "raw_output": outcome.raw_output})

    response = outcome.response
    predicted = response.output.category
    return base.model_copy(
        update={
            "predicted_category": predicted,
            "category_correct": predicted == task.expected_category,
            "summary": response.output.summary,
            "latency_ms": response.latency_ms,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
    )


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile: the smallest value with at least pct% of values at or below it."""
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def group_accuracy(results: list[CaseResult], key: str) -> dict[str, GroupAccuracy]:
    """Accuracy per value of a field, e.g. per expected_category or per difficulty."""
    groups: dict[str, list[CaseResult]] = defaultdict(list)
    for result in results:
        groups[str(getattr(result, key))].append(result)
    return {
        name: GroupAccuracy(
            total=len(members),
            passed=sum(r.category_correct for r in members),
            accuracy=sum(r.category_correct for r in members) / len(members),
        )
        for name, members in sorted(groups.items())
    }


def compute_metrics(results: list[CaseResult]) -> RunMetrics:
    total = len(results)
    passed = sum(r.category_correct for r in results)
    scores = [r.judge_score for r in results if r.judge_score is not None]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    return RunMetrics(
        total=total,
        passed=passed,
        accuracy=passed / total if total else 0.0,
        by_category=group_accuracy(results, "expected_category"),
        by_difficulty=group_accuracy(results, "difficulty"),
        judged=len(scores),
        mean_judge_score=sum(scores) / len(scores) if scores else None,
        latency_p50_ms=percentile(latencies, 50),
        latency_p95_ms=percentile(latencies, 95),
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        errors=dict(Counter(r.error for r in results if r.error)),
    )


def retry_delay(retries_so_far: int) -> int:
    """Exponential backoff in seconds: 5, 10, 20, 40 ... capped at 120."""
    return min(5 * 2**retries_so_far, 120)

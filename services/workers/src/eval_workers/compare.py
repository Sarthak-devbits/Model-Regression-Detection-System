"""Diff a run against its baseline and decide the verdict."""

from shared.runs import CaseFlip, CaseResult, Comparison, RunMetrics, Verdict


def points(current: float, baseline: float) -> float:
    """Accuracy difference in percentage points: 0.89 vs 0.94 gives -5.0."""
    return round((current - baseline) * 100, 2)


def optional_delta(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None:
        return None
    return current - baseline


def make_flip(baseline: CaseResult, current: CaseResult) -> CaseFlip:
    return CaseFlip(
        case_id=current.case_id,
        expected_category=current.expected_category,
        baseline_predicted=baseline.predicted_category,
        current_predicted=current.predicted_category,
        baseline_summary=baseline.summary,
        current_summary=current.summary,
        current_error=current.error,
    )


def find_flips(baseline_results: list[CaseResult], current_results: list[CaseResult]) -> tuple[list[CaseFlip], list[CaseFlip]]:
    """Cases that went pass -> fail (regressions) and fail -> pass (improvements)."""
    baseline_by_id = {r.case_id: r for r in baseline_results}
    regressions: list[CaseFlip] = []
    improvements: list[CaseFlip] = []
    for current in current_results:
        before = baseline_by_id.get(current.case_id)
        if before is None:
            continue
        if before.category_correct and not current.category_correct:
            regressions.append(make_flip(before, current))
        elif not before.category_correct and current.category_correct:
            improvements.append(make_flip(before, current))
    return regressions, improvements


def compare_runs(
    baseline_run_id: str,
    base: RunMetrics,
    baseline_results: list[CaseResult],
    cur: RunMetrics,
    current_results: list[CaseResult],
) -> Comparison:
    regressions, improvements = find_flips(baseline_results, current_results)
    shared_categories = sorted(cur.by_category.keys() & base.by_category.keys())
    return Comparison(
        baseline_run_id=baseline_run_id,
        accuracy_delta_pp=points(cur.accuracy, base.accuracy),
        by_category_delta_pp={
            name: points(cur.by_category[name].accuracy, base.by_category[name].accuracy) for name in shared_categories
        },
        judge_score_delta=optional_delta(cur.mean_judge_score, base.mean_judge_score),
        latency_p95_delta_ms=optional_delta(cur.latency_p95_ms, base.latency_p95_ms),
        tokens_delta=(cur.input_tokens + cur.output_tokens) - (base.input_tokens + base.output_tokens),
        regressions=regressions,
        improvements=improvements,
    )


def decide_verdict(accuracy_delta_pp: float, warn_pct: float, critical_pct: float) -> Verdict:
    """A drop bigger than warn_pct points is a warning; bigger than critical_pct is critical."""
    drop = -accuracy_delta_pp
    if drop > critical_pct:
        return Verdict.CRITICAL
    if drop > warn_pct:
        return Verdict.WARN
    return Verdict.PASS

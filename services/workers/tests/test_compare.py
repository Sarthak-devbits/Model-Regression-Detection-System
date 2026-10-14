import pytest

from eval_workers.compare import compare_runs, decide_verdict, find_flips, points
from eval_workers.scoring import compute_metrics
from shared.runs import Verdict


def test_points() -> None:
    assert points(0.89, 0.94) == -5.0


def test_flips_are_found_in_both_directions(make_result) -> None:
    baseline = [
        make_result("gc-0001", "billing", "billing"),
        make_result("gc-0002", "technical", "account"),
        make_result("gc-0003", "general", "general"),
    ]
    current = [
        make_result("gc-0001", "billing", "general"),
        make_result("gc-0002", "technical", "technical"),
        make_result("gc-0003", "general", "general"),
    ]
    regressions, improvements = find_flips(baseline, current)
    assert [f.case_id for f in regressions] == ["gc-0001"]
    assert regressions[0].baseline_predicted == "billing"
    assert regressions[0].current_predicted == "general"
    assert [f.case_id for f in improvements] == ["gc-0002"]


def test_comparison_deltas(make_result) -> None:
    baseline = [make_result(f"gc-{i:04d}", "billing", "billing") for i in range(1, 5)]
    current = [*baseline[:3], make_result("gc-0004", "billing", "general")]
    comparison = compare_runs("run_base", compute_metrics(baseline), baseline, compute_metrics(current), current)
    assert comparison.accuracy_delta_pp == -25.0
    assert comparison.by_category_delta_pp == {"billing": -25.0}
    assert len(comparison.regressions) == 1


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (+2.0, Verdict.PASS),
        (0.0, Verdict.PASS),
        (-3.0, Verdict.PASS),
        (-3.1, Verdict.WARN),
        (-8.0, Verdict.WARN),
        (-8.1, Verdict.CRITICAL),
    ],
)
def test_verdict_thresholds(delta: float, expected: Verdict) -> None:
    assert decide_verdict(delta, warn_pct=3.0, critical_pct=8.0) is expected

import pytest

from shared.runs import CaseResult, CaseTask


@pytest.fixture
def case_task() -> CaseTask:
    return CaseTask(
        case_id="gc-0001",
        email="I was charged twice, please refund one.",
        expected_category="billing",
        ideal_summary="Customer was charged twice and wants one charge refunded.",
        difficulty="easy",
    )


@pytest.fixture
def make_result():
    def _make(
        case_id: str = "gc-0001",
        expected: str = "billing",
        predicted: str | None = "billing",
        difficulty: str = "easy",
        **extra,
    ) -> CaseResult:
        return CaseResult(
            case_id=case_id,
            difficulty=difficulty,
            expected_category=expected,
            predicted_category=predicted,
            category_correct=predicted == expected,
            **extra,
        )

    return _make

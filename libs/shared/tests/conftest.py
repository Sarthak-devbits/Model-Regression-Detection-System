from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from shared.golden import GoldenDataset
from shared.prompts import PromptConfig

CaseFactory = Callable[..., dict[str, Any]]
DatasetFactory = Callable[..., GoldenDataset]


@pytest.fixture
def prompt() -> PromptConfig:
    return PromptConfig.model_validate(
        {
            "version_id": "v1",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "model": "gpt-4o-mini",
            "temperature": 0,
            "max_output_tokens": 200,
            "system_prompt": "Classify the email.",
            "few_shot_examples": [
                {
                    "email": "Refund my duplicate charge please.",
                    "category": "billing",
                    "summary": "Customer wants a duplicate charge refunded.",
                }
            ],
        }
    )


@pytest.fixture
def make_case() -> CaseFactory:
    """Build one valid case as a dict. Override any field with keyword arguments."""

    def _make(
        n: int,
        category: str = "billing",
        difficulty: str = "easy",
        email: str | None = None,
        edge_cases: list[str] | None = None,
        summary: str = "Customer asks a clear question about their account today.",
        **overrides: Any,
    ) -> dict[str, Any]:
        case = {
            "id": f"gc-{n:04d}",
            "input": {"email": email or f"This is test email number {n} with enough words in it."},
            "expected": {"category": category, "summary": summary},
            "expected_difficulty": difficulty,
            "edge_cases": edge_cases or [],
            "notes": "test case",
            "source": "hand_written",
            "added_in": "v1",
        }
        case.update(overrides)
        return case

    return _make


@pytest.fixture
def make_dataset() -> DatasetFactory:
    """Build a validated dataset from a list of case dicts."""

    def _make(cases: list[dict[str, Any]], version: str = "v1") -> GoldenDataset:
        return GoldenDataset.model_validate(
            {
                "dataset_version": version,
                "description": "test dataset",
                "labeling_guide_version": 1,
                "cases": cases,
            }
        )

    return _make

from datetime import UTC, datetime

import pytest

from shared.prompts import PromptConfig


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

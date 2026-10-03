from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.categories import Category
from shared.prompts import PromptConfig, load_prompt

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_FILES = sorted((REPO_ROOT / "prompts" / "classifier").glob("*.yaml"))


def minimal_prompt(**overrides) -> dict:
    data = {
        "version_id": "v9",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "system_prompt": "Classify the email.",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("path", PROMPT_FILES, ids=lambda p: p.name)
def test_every_committed_prompt_file_loads(path: Path) -> None:
    prompt = load_prompt(path)
    assert prompt.version_id == path.stem


def test_there_is_at_least_one_prompt_file() -> None:
    assert PROMPT_FILES, "expected prompts/classifier/*.yaml"


def test_defaults_are_applied() -> None:
    prompt = PromptConfig.model_validate(minimal_prompt())
    assert prompt.model == "gpt-4o-mini"
    assert prompt.temperature == 0.0
    assert prompt.few_shot_examples == []


def test_few_shot_category_must_be_valid() -> None:
    bad = minimal_prompt(few_shot_examples=[{"email": "hi", "category": "sales", "summary": "x"}])
    with pytest.raises(ValidationError, match="few_shot_examples"):
        PromptConfig.model_validate(bad)


def test_few_shot_category_becomes_enum() -> None:
    ok = minimal_prompt(few_shot_examples=[{"email": "hi", "category": "billing", "summary": "x"}])
    assert PromptConfig.model_validate(ok).few_shot_examples[0].category is Category.BILLING


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PromptConfig.model_validate(minimal_prompt(temprature=0.5))


def test_temperature_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="temperature"):
        PromptConfig.model_validate(minimal_prompt(temperature=3))


def test_file_name_must_match_version(tmp_path: Path) -> None:
    path = tmp_path / "v2.yaml"
    path.write_text(
        "version_id: v3\ncreated_at: 2026-01-01T00:00:00Z\nsystem_prompt: hi\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rename"):
        load_prompt(path)

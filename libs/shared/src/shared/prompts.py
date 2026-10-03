"""Prompt configs: the versioned YAML files CI runs the eval against."""

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from shared.categories import Category


class FewShotExample(BaseModel):
    """One worked example shown to the model before the real email."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    email: str = Field(min_length=1)
    category: Category
    summary: str = Field(min_length=1)


class PromptConfig(BaseModel):
    """Everything needed to reproduce one classifier call, apart from the email."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version_id: str = Field(pattern=r"^v\d+$")
    created_at: datetime
    description: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=300, gt=0, le=4000)
    system_prompt: str = Field(min_length=1)
    few_shot_examples: list[FewShotExample] = Field(default_factory=list)


def load_prompt(path: Path) -> PromptConfig:
    """Read a prompt YAML file. The file name must match its version_id (v1.yaml -> v1)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    prompt = PromptConfig.model_validate(data)
    if path.stem != prompt.version_id:
        raise ValueError(f"{path.name} contains version_id={prompt.version_id}; rename one of them")
    return prompt

"""Request and response contracts for the classifier service."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.categories import Category
from shared.prompts import PromptConfig


class ClassifyRequest(BaseModel):
    """What callers send: the email, plus the full prompt config to use."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=8000)
    prompt: PromptConfig


class ClassifierOutput(BaseModel):
    """What the LLM must return. Anything else counts as invalid output."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    summary: str = Field(min_length=1, max_length=300)


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ClassifyResponse(BaseModel):
    """What the service returns on success."""

    output: ClassifierOutput
    prompt_version: str
    model: str
    latency_ms: float = Field(ge=0)
    usage: TokenUsage


ErrorCode = Literal["invalid_model_output", "llm_unavailable", "llm_request_failed"]


class ErrorResponse(BaseModel):
    """What the service returns when the LLM call or its output fails."""

    error: ErrorCode
    detail: str
    retryable: bool
    raw_output: str | None = None

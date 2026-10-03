"""Configuration for the classifier service, read from environment variables."""

from typing import Literal

from pydantic import Field, SecretStr

from shared.settings import BaseServiceSettings


class ClassifierSettings(BaseServiceSettings):
    service_name: str = "classifier"
    llm_provider: Literal["openai", "fake"] = "openai"
    openai_api_key: SecretStr | None = None
    request_timeout_s: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)

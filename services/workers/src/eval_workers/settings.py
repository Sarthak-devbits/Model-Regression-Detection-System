"""Configuration for every worker process, read from environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr

from shared.settings import BaseServiceSettings


class WorkerSettings(BaseServiceSettings):
    service_name: str = "workers"
    # eval queue: calling the classifier service
    classifier_url: str = "http://localhost:8001"
    classifier_timeout_s: float = Field(default=60.0, gt=0)
    # judge queue: calling the judge LLM directly
    llm_provider: Literal["openai", "fake"] = "openai"
    openai_api_key: SecretStr | None = None
    judge_timeout_s: float = Field(default=60.0, gt=0)
    judge_rate_limit: str = "60/m"
    # reports queue: storage and thresholds
    database_path: Path = Path("./data/regci.sqlite3")
    warn_threshold_pct: float = Field(default=3.0, ge=0)
    critical_threshold_pct: float = Field(default=8.0, ge=0)
    max_infra_error_rate: float = Field(default=0.1, ge=0, le=1)
    # retries for transient failures (rate limits, timeouts)
    task_max_retries: int = Field(default=3, ge=0, le=10)

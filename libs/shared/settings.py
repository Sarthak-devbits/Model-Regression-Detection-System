"""Base settings that every service extends."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "ci", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    service_name: str = "unknown-service"
    environment: Environment = "local"
    log_level: LogLevel = "INFO"
    redis_url: str = Field(default="redis://localhost:6379/0")
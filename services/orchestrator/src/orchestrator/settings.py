"""Configuration for the orchestrator, read from environment variables."""

from pathlib import Path

from pydantic import SecretStr

from shared.settings import BaseServiceSettings


class OrchestratorSettings(BaseServiceSettings):
    service_name: str = "orchestrator"
    database_path: Path = Path("./data/regci.sqlite3")
    golden_dir: Path = Path("./golden")
    prompts_dir: Path = Path("./prompts")
    judge_prompt_version: str = "v1"
    orchestrator_api_token: SecretStr | None = None

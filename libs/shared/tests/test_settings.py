import pytest
from pydantic import ValidationError

from shared.settings import BaseServiceSettings


def test_defaults_apply_when_env_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    settings = BaseServiceSettings(_env_file=None)
    assert settings.service_name == "unknown-service"
    assert settings.environment == "local"


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "classifier")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = BaseServiceSettings(_env_file=None)
    assert settings.service_name == "classifier"
    assert settings.log_level == "DEBUG"


def test_rejects_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        BaseServiceSettings(_env_file=None)

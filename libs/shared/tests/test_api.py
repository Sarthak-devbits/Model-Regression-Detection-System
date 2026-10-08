from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from classifier_service.main import create_app
from classifier_service.settings import ClassifierSettings
from shared.llm import FakeLLMClient, LLMError, LLMResult

GOOD_REPLY = '{"category": "technical", "summary": "CSV export downloads nothing."}'


def make_client(llm) -> TestClient:
    settings = ClassifierSettings(_env_file=None, llm_provider="fake")  # type: ignore[call-arg]
    return TestClient(create_app(settings=settings, llm=llm))


@pytest.fixture
def body(prompt) -> dict:
    return {
        "email": "The CSV export button does nothing.",
        "prompt": prompt.model_dump(mode="json"),
    }


def test_healthz() -> None:
    with make_client(FakeLLMClient()) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm_provider": "fake"}


def test_classify_success(body) -> None:
    with make_client(FakeLLMClient(replies=[GOOD_REPLY])) as client:
        response = client.post("/classify", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["output"] == {"category": "technical", "summary": "CSV export downloads nothing."}
    assert data["prompt_version"] == "v1"
    assert set(data["usage"]) == {"input_tokens", "output_tokens"}


def test_invalid_model_output_is_a_clean_502(body) -> None:
    with make_client(FakeLLMClient(replies=["sorry, I am not JSON"])) as client:
        response = client.post("/classify", json=body)
    assert response.status_code == 502
    data = response.json()
    assert data["error"] == "invalid_model_output"
    assert data["retryable"] is False
    assert data["raw_output"] == "sorry, I am not JSON"


def test_missing_email_is_a_422(body) -> None:
    del body["email"]
    with make_client(FakeLLMClient()) as client:
        response = client.post("/classify", json=body)
    assert response.status_code == 422


class FailingLLM:
    def __init__(self, retryable: bool) -> None:
        self.retryable = retryable

    async def complete(self, **_: object) -> LLMResult:
        raise LLMError("provider trouble", retryable=self.retryable)


@pytest.mark.parametrize(
    ("retryable", "status", "code"),
    [(True, 503, "llm_unavailable"), (False, 502, "llm_request_failed")],
)
def test_llm_errors_map_to_status_codes(body, retryable, status, code) -> None:
    with make_client(FailingLLM(retryable)) as client:
        response = client.post("/classify", json=body)
    assert response.status_code == status
    assert response.json()["error"] == code
    assert response.json()["retryable"] is retryable


def test_service_refuses_to_start_without_api_key() -> None:
    settings = ClassifierSettings(_env_file=None, llm_provider="openai", openai_api_key=None)  # type: ignore[call-arg]
    app = create_app(settings=settings)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"), TestClient(app):
        pass


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    yield

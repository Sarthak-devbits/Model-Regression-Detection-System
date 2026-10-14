import httpx
import pytest

from eval_workers.classifier_client import call_classifier

OK_BODY = {
    "output": {"category": "billing", "summary": "Customer wants a refund."},
    "prompt_version": "v1",
    "model": "gpt-4o-mini",
    "latency_ms": 420.0,
    "usage": {"input_tokens": 300, "output_tokens": 20},
}


def client_answering(status: int, body=None, content: bytes | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if content is not None:
            return httpx.Response(status, content=content)
        return httpx.Response(status, json=body)

    return httpx.Client(base_url="http://classifier", transport=httpx.MockTransport(handler))


def error_body(error: str, retryable: bool, raw: str | None = None) -> dict:
    return {"error": error, "detail": "x", "retryable": retryable, "raw_output": raw}


def test_success() -> None:
    outcome = call_classifier(client_answering(200, OK_BODY), "email", {})
    assert outcome.kind == "ok"
    assert outcome.response is not None
    assert outcome.response.usage.input_tokens == 300


def test_invalid_model_output_keeps_raw_text() -> None:
    body = error_body("invalid_model_output", retryable=False, raw="not json")
    outcome = call_classifier(client_answering(502, body), "email", {})
    assert outcome.kind == "invalid_output"
    assert outcome.raw_output == "not json"


def test_llm_unavailable_is_retryable() -> None:
    outcome = call_classifier(client_answering(503, error_body("llm_unavailable", True)), "e", {})
    assert outcome.kind == "retryable"
    assert outcome.error == "llm_unavailable"


def test_llm_request_failed_is_final() -> None:
    body = error_body("llm_request_failed", retryable=False)
    outcome = call_classifier(client_answering(502, body), "e", {})
    assert outcome.kind == "failed"


@pytest.mark.parametrize(("status", "kind"), [(500, "retryable"), (404, "failed")])
def test_non_json_errors_use_the_status_code(status: int, kind: str) -> None:
    outcome = call_classifier(client_answering(status, content=b"<html>oops</html>"), "e", {})
    assert outcome.kind == kind
    assert outcome.error == f"classifier_http_{status}"


def test_unreachable_service_is_retryable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(base_url="http://classifier", transport=httpx.MockTransport(refuse))
    outcome = call_classifier(client, "e", {})
    assert outcome.kind == "retryable"
    assert outcome.error == "classifier_unreachable: ConnectError"

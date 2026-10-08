import json

import httpx2 as httpx
import pytest
from openai import AsyncOpenAI

from shared.llm import LLMError, OpenAIClient

SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def completion_body(content: str, finish_reason: str = "stop") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content, "refusal": None},
                "finish_reason": finish_reason,
                "logprobs": None,
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 25, "total_tokens": 145},
    }


def client_returning(status: int, body: dict, seen: list[dict] | None = None) -> OpenAIClient:
    """A real OpenAI SDK client whose HTTP traffic goes to a local function, not the internet."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(status, json=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sdk = AsyncOpenAI(api_key="test-key", http_client=http, max_retries=0)
    return OpenAIClient(sdk)


async def call(client: OpenAIClient):
    return await client.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        temperature=0,
        max_output_tokens=100,
        json_schema=SCHEMA,
    )


async def test_success_is_mapped_to_llm_result() -> None:
    client = client_returning(200, completion_body('{"category": "billing", "summary": "x"}'))
    result = await call(client)
    assert result.text == '{"category": "billing", "summary": "x"}'
    assert (result.input_tokens, result.output_tokens) == (120, 25)
    assert result.model == "gpt-4o-mini-2024-07-18"
    assert result.finish_reason == "stop"


async def test_request_uses_strict_structured_outputs() -> None:
    seen: list[dict] = []
    await call(client_returning(200, completion_body("{}"), seen))
    sent = seen[0]
    assert sent["temperature"] == 0
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["response_format"]["json_schema"]["schema"] == SCHEMA


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (503, True), (400, False), (401, False)],
)
async def test_http_errors_become_llm_errors(status: int, retryable: bool) -> None:
    client = client_returning(status, {"error": {"message": "nope", "type": "x"}})
    with pytest.raises(LLMError) as caught:
        await call(client)
    assert caught.value.retryable is retryable

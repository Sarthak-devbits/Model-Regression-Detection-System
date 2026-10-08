"""Provider adapter: the only place that knows how to talk to an LLM vendor.

Shared by the classifier service and the judge worker.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import openai
from openai import AsyncOpenAI

Message = dict[str, str]


@dataclass(frozen=True)
class LLMResult:
    """A provider-neutral reply."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str = "stop"
    refusal: str | None = None


class LLMError(Exception):
    """The LLM call itself failed. retryable=True means trying again later may work."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMClient(Protocol):
    """Anything with this method can be used as the LLM. Real or fake."""

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        temperature: float,
        max_output_tokens: int,
        json_schema: dict[str, Any],
    ) -> LLMResult: ...


class OpenAIClient:
    """LLMClient backed by the OpenAI Chat Completions API with structured outputs."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    @classmethod
    def from_api_key(cls, api_key: str, *, timeout_s: float, max_retries: int) -> "OpenAIClient":
        return cls(AsyncOpenAI(api_key=api_key, timeout=timeout_s, max_retries=max_retries))

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        temperature: float,
        max_output_tokens: int,
        json_schema: dict[str, Any],
    ) -> LLMResult:
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_completion_tokens=max_output_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "email_classification",
                        "strict": True,
                        "schema": json_schema,
                    },
                },
            )
        except openai.RateLimitError as exc:
            raise LLMError("rate limited by OpenAI", retryable=True) from exc
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise LLMError("could not reach OpenAI", retryable=True) from exc
        except openai.APIStatusError as exc:
            retryable = exc.status_code >= 500
            raise LLMError(f"OpenAI returned HTTP {exc.status_code}", retryable=retryable) from exc

        choice = response.choices[0]
        usage = response.usage
        return LLMResult(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            finish_reason=choice.finish_reason,
            refusal=getattr(choice.message, "refusal", None),
        )

    async def aclose(self) -> None:
        await self._client.close()


Responder = Callable[[list[Message]], str]


class FakeLLMClient:
    """Offline stand-in for tests and local runs without an API key.

    Returns scripted replies in order. When none are left, asks the responder function
    (if given) to produce a reply from the messages.
    """

    def __init__(self, replies: list[str] | None = None, responder: Responder | None = None) -> None:
        self._replies = list(replies or [])
        self._responder = responder
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        temperature: float,
        max_output_tokens: int,
        json_schema: dict[str, Any],
    ) -> LLMResult:
        self.calls.append(
            {
                "messages": messages,
                "model": model,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "json_schema": json_schema,
            }
        )
        if self._replies:
            text = self._replies.pop(0)
        elif self._responder is not None:
            text = self._responder(messages)
        else:
            raise RuntimeError("FakeLLMClient has no scripted replies left and no responder")
        return LLMResult(
            text=text,
            input_tokens=sum(len(m["content"].split()) for m in messages),
            output_tokens=len(text.split()),
            model=f"fake:{model}",
        )

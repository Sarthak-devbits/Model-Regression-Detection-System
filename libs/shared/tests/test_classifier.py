import pytest

from classifier_service.classifier import InvalidModelOutputError, classify_email
from classifier_service.llm import FakeLLMClient, LLMResult
from shared.categories import Category

GOOD_REPLY = '{"category": "billing", "summary": "Customer wants a refund for a double charge."}'


async def test_valid_reply_becomes_a_typed_response(prompt) -> None:
    llm = FakeLLMClient(replies=[GOOD_REPLY])
    response = await classify_email("I was charged twice.", prompt, llm)
    assert response.output.category is Category.BILLING
    assert response.prompt_version == "v1"
    assert response.latency_ms >= 0
    assert response.usage.output_tokens > 0


async def test_prompt_settings_are_passed_to_the_llm(prompt) -> None:
    llm = FakeLLMClient(replies=[GOOD_REPLY])
    await classify_email("I was charged twice.", prompt, llm)
    call = llm.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["temperature"] == 0
    assert call["max_output_tokens"] == 200


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("not json at all", "Invalid JSON"),
        ('{"category": "sales", "summary": "x"}', "category"),
        ('{"category": "billing"}', "summary"),
        ('{"category": "billing", "summary": "x", "confidence": 0.9}', "confidence"),
    ],
    ids=["not-json", "unknown-category", "missing-summary", "extra-field"],
)
async def test_invalid_replies_raise_with_the_raw_text(prompt, reply, reason) -> None:
    llm = FakeLLMClient(replies=[reply])
    with pytest.raises(InvalidModelOutputError, match=reason) as caught:
        await classify_email("anything", prompt, llm)
    assert caught.value.raw_output == reply


class OneShotLLM:
    """Returns one fixed LLMResult, to simulate provider-level outcomes."""

    def __init__(self, result: LLMResult) -> None:
        self.result = result

    async def complete(self, **_: object) -> LLMResult:
        return self.result


async def test_truncated_reply_is_invalid(prompt) -> None:
    llm = OneShotLLM(LLMResult('{"category": "bill', 50, 300, "m", finish_reason="length"))
    with pytest.raises(InvalidModelOutputError, match="cut off"):
        await classify_email("anything", prompt, llm)


async def test_refusal_is_invalid(prompt) -> None:
    llm = OneShotLLM(LLMResult("", 50, 5, "m", refusal="I can't help with that."))
    with pytest.raises(InvalidModelOutputError, match="refused"):
        await classify_email("anything", prompt, llm)


async def test_fake_keyword_mode_needs_no_script(prompt) -> None:
    response = await classify_email("I need a refund", prompt, FakeLLMClient())
    assert response.output.category is Category.BILLING
    assert response.model == "fake:gpt-4o-mini"

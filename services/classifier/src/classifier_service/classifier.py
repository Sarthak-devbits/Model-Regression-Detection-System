"""The feature under test: one function that classifies one email."""

import logging
import time

from pydantic import ValidationError

from classifier_service.llm import LLMClient
from classifier_service.prompting import OUTPUT_JSON_SCHEMA, build_messages
from shared.classification import ClassifierOutput, ClassifyResponse, TokenUsage
from shared.prompts import PromptConfig

log = logging.getLogger(__name__)


class InvalidModelOutputError(Exception):
    """The model replied, but not with a valid classification."""

    def __init__(self, reason: str, raw_output: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.raw_output = raw_output


def parse_model_output(text: str) -> ClassifierOutput:
    """Validate the model's reply. We never repair it: bad output is a real failure."""
    try:
        return ClassifierOutput.model_validate_json(text)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "reply"
        raise InvalidModelOutputError(f"{where}: {first['msg']}", text) from exc


async def classify_email(email: str, prompt: PromptConfig, llm: LLMClient) -> ClassifyResponse:
    messages = build_messages(prompt, email)

    started = time.perf_counter()
    result = await llm.complete(
        messages=messages,
        model=prompt.model,
        temperature=prompt.temperature,
        max_output_tokens=prompt.max_output_tokens,
        json_schema=OUTPUT_JSON_SCHEMA,
    )
    latency_ms = (time.perf_counter() - started) * 1000

    if result.refusal:
        raise InvalidModelOutputError("model refused to answer", result.refusal)
    if result.finish_reason == "length":
        raise InvalidModelOutputError("reply was cut off by max_output_tokens", result.text)

    output = parse_model_output(result.text)
    log.info(
        "classified",
        extra={
            "fields": {
                "category": output.category.value,
                "latency_ms": round(latency_ms, 1),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        },
    )
    return ClassifyResponse(
        output=output,
        prompt_version=prompt.version_id,
        model=result.model,
        latency_ms=latency_ms,
        usage=TokenUsage(input_tokens=result.input_tokens, output_tokens=result.output_tokens),
    )

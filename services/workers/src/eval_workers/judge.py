"""LLM-as-judge: grade a candidate summary 1-5 against the human-written ideal summary."""

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from shared.llm import LLMClient, Message
from shared.prompts import JudgePromptConfig

JUDGE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "score": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
    },
    "required": ["reason", "score"],
    "additionalProperties": False,
}


class JudgeVerdict(BaseModel):
    reason: str = Field(min_length=1)
    score: int = Field(ge=1, le=5)


class InvalidJudgeOutputError(Exception):
    pass


def build_judge_messages(judge_prompt: JudgePromptConfig, email: str, ideal: str, candidate: str) -> list[Message]:
    user = (
        f"<email>\n{email}\n</email>\n\n"
        f"<ideal_summary>\n{ideal}\n</ideal_summary>\n\n"
        f"<candidate_summary>\n{candidate}\n</candidate_summary>"
    )
    return [
        {"role": "system", "content": judge_prompt.system_prompt},
        {"role": "user", "content": user},
    ]


async def judge_summary(llm: LLMClient, judge_prompt: JudgePromptConfig, email: str, ideal: str, candidate: str) -> JudgeVerdict:
    result = await llm.complete(
        messages=build_judge_messages(judge_prompt, email, ideal, candidate),
        model=judge_prompt.model,
        temperature=judge_prompt.temperature,
        max_output_tokens=judge_prompt.max_output_tokens,
        json_schema=JUDGE_JSON_SCHEMA,
    )
    try:
        return JudgeVerdict.model_validate_json(result.text)
    except ValidationError as exc:
        raise InvalidJudgeOutputError(f"judge reply was not valid: {result.text[:200]}") from exc


# ---------- offline fake judge ----------

_TAG = r"<{0}>\n(.*?)\n</{0}>"


def overlap_judge_reply(messages: list[Message]) -> str:
    """Fake judge for LLM_PROVIDER=fake: scores by word overlap. Not a real judge."""
    text = messages[-1]["content"]
    ideal = re.search(_TAG.format("ideal_summary"), text, re.S)
    candidate = re.search(_TAG.format("candidate_summary"), text, re.S)
    ideal_words = set(ideal.group(1).lower().split()) if ideal else set()
    candidate_words = set(candidate.group(1).lower().split()) if candidate else set()
    union = ideal_words | candidate_words
    overlap = len(ideal_words & candidate_words) / len(union) if union else 0.0
    score = 1 + round(4 * overlap)
    return json.dumps({"reason": f"fake judge: {overlap:.0%} word overlap", "score": score})

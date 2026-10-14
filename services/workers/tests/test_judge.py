import json
from datetime import UTC, datetime

import pytest

from eval_workers.judge import (
    InvalidJudgeOutputError,
    build_judge_messages,
    judge_summary,
    overlap_judge_reply,
)
from shared.llm import FakeLLMClient
from shared.prompts import JudgePromptConfig

RUBRIC = JudgePromptConfig(version_id="v1", created_at=datetime(2026, 1, 1, tzinfo=UTC), system_prompt="Grade it.")


def test_messages_wrap_each_input_in_tags() -> None:
    messages = build_judge_messages(RUBRIC, "the email", "the ideal", "the candidate")
    assert messages[0] == {"role": "system", "content": "Grade it."}
    user = messages[1]["content"]
    assert "<email>\nthe email\n</email>" in user
    assert "<ideal_summary>\nthe ideal\n</ideal_summary>" in user
    assert "<candidate_summary>\nthe candidate\n</candidate_summary>" in user


async def test_valid_reply_becomes_verdict() -> None:
    llm = FakeLLMClient(replies=['{"reason": "Same meaning.", "score": 5}'])
    verdict = await judge_summary(llm, RUBRIC, "e", "ideal", "candidate")
    assert (verdict.score, verdict.reason) == (5, "Same meaning.")
    assert llm.calls[0]["model"] == "gpt-4o"


@pytest.mark.parametrize("reply", ['{"reason": "x", "score": 7}', "five", '{"score": 4}'])
async def test_invalid_reply_raises(reply: str) -> None:
    with pytest.raises(InvalidJudgeOutputError):
        await judge_summary(FakeLLMClient(replies=[reply]), RUBRIC, "e", "i", "c")


def test_fake_judge_scores_by_overlap() -> None:
    same = build_judge_messages(RUBRIC, "e", "refund the double charge", "refund the double charge")
    different = build_judge_messages(RUBRIC, "e", "refund the double charge", "password reset")
    assert json.loads(overlap_judge_reply(same))["score"] == 5
    assert json.loads(overlap_judge_reply(different))["score"] == 1

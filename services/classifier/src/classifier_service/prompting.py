"""Turn a prompt config and an email into the messages sent to the model."""

import json
from typing import Any

from shared.categories import Category
from shared.llm import Message
from shared.prompts import PromptConfig

# Sent to the model as the required reply format (OpenAI structured outputs).
OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [c.value for c in Category]},
        "summary": {"type": "string"},
    },
    "required": ["category", "summary"],
    "additionalProperties": False,
}


def wrap_email(email: str) -> str:
    """Put the email inside tags so the model can tell data from instructions."""
    return f"<email>\n{email}\n</email>"


def build_messages(prompt: PromptConfig, email: str) -> list[Message]:
    """System prompt, then each few-shot example as a user/assistant pair, then the email."""
    messages: list[Message] = [{"role": "system", "content": prompt.system_prompt}]
    for example in prompt.few_shot_examples:
        answer = {"category": example.category.value, "summary": example.summary}
        messages.append({"role": "user", "content": wrap_email(example.email)})
        messages.append({"role": "assistant", "content": json.dumps(answer)})
    messages.append({"role": "user", "content": wrap_email(email)})
    return messages

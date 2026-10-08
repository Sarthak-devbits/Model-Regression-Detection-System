"""Offline keyword guesser, used when LLM_PROVIDER=fake. Not a real classifier."""

import json

from shared.llm import Message

KEYWORDS: dict[str, tuple[str, ...]] = {
    "billing": ("refund", "invoice", "charge", "receipt", "bill", "payment"),
    "technical": ("error", "bug", "crash", "broken", "not working", "fails", "500"),
    "account": ("password", "log in", "login", "locked", "email address", "account"),
}


def keyword_reply(messages: list[Message]) -> str:
    """Guess a category from keywords in the last message and echo it as a summary."""
    content = messages[-1]["content"]
    email = content.lower()
    category = next(
        (name for name, words in KEYWORDS.items() if any(w in email for w in words)),
        "general",
    )
    words = content.replace("<email>", "").replace("</email>", "").split()
    summary = "Offline fake summary: " + " ".join(words[:12])
    return json.dumps({"category": category, "summary": summary})

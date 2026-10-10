"""Calls the classifier service and turns every possible response into a CallOutcome."""

from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from shared.classification import ClassifyResponse, ErrorResponse

OutcomeKind = Literal["ok", "invalid_output", "retryable", "failed"]


@dataclass(frozen=True)
class CallOutcome:
    kind: OutcomeKind
    response: ClassifyResponse | None = None
    error: str | None = None
    raw_output: str | None = None


def call_classifier(client: httpx.Client, email: str, prompt: dict[str, Any]) -> CallOutcome:
    try:
        reply = client.post("/classify", json={"email": email, "prompt": prompt})
    except httpx.TransportError as exc:
        return CallOutcome("retryable", error=f"classifier_unreachable: {type(exc).__name__}")

    if reply.status_code == 200:
        return CallOutcome("ok", response=ClassifyResponse.model_validate(reply.json()))

    try:
        body = ErrorResponse.model_validate(reply.json())
    except (ValueError, ValidationError):
        retryable = reply.status_code >= 500
        kind: OutcomeKind = "retryable" if retryable else "failed"
        return CallOutcome(kind, error=f"classifier_http_{reply.status_code}")

    if body.retryable:
        return CallOutcome("retryable", error=body.error)
    if body.error == "invalid_model_output":
        return CallOutcome("invalid_output", error=body.error, raw_output=body.raw_output)
    return CallOutcome("failed", error=body.error)

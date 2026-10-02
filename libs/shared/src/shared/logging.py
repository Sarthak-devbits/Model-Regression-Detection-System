"""Structured JSON logging with per-request context (run_id, case_id, ...)."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Default is None (not {}) so no mutable object is ever shared between contexts.
_log_context: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)


def _current() -> dict[str, Any]:
    return _log_context.get() or {}


def bind_context(**fields: Any) -> None:
    """Attach fields (e.g. run_id) to every log line in the current context."""
    _log_context.set({**_current(), **fields})


def clear_context() -> None:
    """Remove all bound fields, e.g. when a task finishes."""
    _log_context.set({})


class JsonFormatter(logging.Formatter):
    """Render each log record as one JSON object per line."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
            **_current(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    """Send all logs to stdout as JSON. Call once at service startup."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

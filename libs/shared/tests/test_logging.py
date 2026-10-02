import json
import logging
from collections.abc import Iterator

import pytest

from shared.logging import bind_context, clear_context, configure_logging


@pytest.fixture(autouse=True)
def _reset_context() -> Iterator[None]:
    clear_context()
    yield
    clear_context()


def read_last_line(capsys: pytest.CaptureFixture[str]) -> dict:
    out = capsys.readouterr().out.strip().splitlines()
    return json.loads(out[-1])


def test_logs_are_json_with_service_name(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("test-service")
    logging.getLogger("demo").info("hello")
    line = read_last_line(capsys)
    assert line["msg"] == "hello"
    assert line["service"] == "test-service"
    assert line["level"] == "info"


def test_bound_context_appears_on_every_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("test-service")
    bind_context(run_id="run_123")
    logging.getLogger("demo").info("case started", extra={"fields": {"case_id": "c-007"}})
    line = read_last_line(capsys)
    assert line["run_id"] == "run_123"
    assert line["case_id"] == "c-007"

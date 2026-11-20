"""Log lines are JSON with allow-listed attributes, and secrets are redacted (LOG-09, LOG-30)."""

import io
import json
import logging
from collections.abc import Iterator
from http import HTTPStatus

import pytest

from app.platform import EventName
from app.platform.adapters.logging_setup import (
    GENERIC_REDACTION_PATTERNS,
    REDACTED,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)

LONG_TOKEN = "a" * 48


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    root = logging.getLogger()
    handlers, level = tuple(root.handlers), root.level
    output = io.StringIO()
    yield output
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def lines_of(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_an_event_is_one_json_line_with_its_fixed_message(stream: io.StringIO) -> None:
    logger = configure_logging(stream, Redactor(GENERIC_REDACTION_PATTERNS))

    StandardLibraryEventRecorder(logger).record(
        EventName.REQUEST_COMPLETED,
        http_status_code=HTTPStatus.NO_CONTENT.value,
        message_text="never logged",
    )

    (line,) = lines_of(stream)
    assert line["event"] == "request.completed"
    assert line["message"] == "Request completed"
    assert line["service"] == "ai-service"
    assert line["level"] == "info"
    assert line["http_status_code"] == HTTPStatus.NO_CONTENT.value
    assert "message_text" not in line


def test_an_allowed_string_attribute_is_redacted(stream: io.StringIO) -> None:
    logger = configure_logging(stream, Redactor(GENERIC_REDACTION_PATTERNS))

    StandardLibraryEventRecorder(logger).record(
        EventName.REQUEST_FAILED, error_type=f"Failure {LONG_TOKEN} for someone@example.com"
    )

    (line,) = lines_of(stream)
    assert line["error_type"] == f"Failure {REDACTED} for {REDACTED}"


def test_a_library_record_is_forwarded_with_a_redacted_message(stream: io.StringIO) -> None:
    configure_logging(stream, Redactor(GENERIC_REDACTION_PATTERNS))

    logging.getLogger("some.library").warning("token %s rejected", LONG_TOKEN)

    (line,) = lines_of(stream)
    assert line["event"] == "log.forwarded"
    assert line["logger_name"] == "some.library"
    assert line["message"] == f"token {REDACTED} rejected"

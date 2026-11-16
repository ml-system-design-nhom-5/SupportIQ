"""Tests of the logging setup: JSON fields, allow-list, and redaction (LOG-09, LOG-10, LOG-30)."""

import io
import json
import logging
import re
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider

from supportiq_backend.platform import EventName
from supportiq_backend.platform.adapters.logging_setup import (
    BACKEND_LOGGER_NAME,
    GENERIC_REDACTION_PATTERNS,
    REDACTED,
    JsonLogFormatter,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)

ORDER_ID_PATTERN = re.compile(r"ORD-[0-9]{5}")
REDACTOR = Redactor((*GENERIC_REDACTION_PATTERNS, ORDER_ID_PATTERN))
EMAIL = "lan.tran@example.test"
ORDER_ID = "ORD-20931"
RAW_SESSION_ID = "Zk3Qm9xR2vT8wY1aB4cD7eF0gH3jK6lM9nP2qS5uV8x"
TICKET_ID = "TCK-1042"
TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z")
# Events of each level of the catalog, none of them with a handled-input level.
LEVELS_OF_THE_CATALOG = [
    (EventName.TICKET_CREATED, "info"),
    (EventName.PERMISSION_DENIED, "warning"),
    (EventName.REQUEST_FAILED, "error"),
]


class CapturedLog:
    """A logger with its own JSON handler, so no test touches the root logger."""

    def __init__(self) -> None:
        """Create the logger, its handler, and the event recorder on it."""
        self.stream = io.StringIO()
        self.logger = logging.Logger("supportiq_backend.test", level=logging.DEBUG)
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(JsonLogFormatter(REDACTOR))
        self.logger.addHandler(handler)
        self.events = StandardLibraryEventRecorder(self.logger)

    def lines(self) -> list[dict[str, object]]:
        """Return every captured line, parsed."""
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def text(self) -> str:
        """Return the captured output as written."""
        return self.stream.getvalue()


@pytest.fixture
def captured() -> CapturedLog:
    return CapturedLog()


@pytest.fixture
def restored_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = tuple(root.handlers), root.level
    yield
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = False


def test_event_line_has_the_fields_of_log_09(captured: CapturedLog) -> None:
    captured.events.record(EventName.TICKET_CREATED, ticket_id=TICKET_ID)

    (line,) = captured.lines()

    assert line["level"] == "info"
    assert line["service"] == "backend"
    assert line["event"] == "ticket.created"
    assert line["message"] == "Ticket created"
    assert line["ticket_id"] == TICKET_ID
    assert TIMESTAMP_PATTERN.fullmatch(str(line["timestamp"]))


def test_event_line_drops_attributes_that_are_not_allow_listed(captured: CapturedLog) -> None:
    captured.events.record(
        EventName.TICKET_CREATED,
        ticket_id=TICKET_ID,
        message_text="Where is my parcel?",
        display_name="Lan Tran",
        order_id=ORDER_ID,
    )

    (line,) = captured.lines()

    assert set(line) == {
        "timestamp",
        "level",
        "service",
        "event",
        "message",
        "trace_id",
        "span_id",
        "ticket_id",
    }


def test_event_line_redacts_known_patterns_in_allow_listed_text(captured: CapturedLog) -> None:
    captured.events.record(
        EventName.REQUEST_COMPLETED, http_route=f"/v1/x/{ORDER_ID}/{EMAIL}/{RAW_SESSION_ID}"
    )

    (line,) = captured.lines()

    assert line["http_route"] == f"/v1/x/{REDACTED}/{REDACTED}/{REDACTED}"


def test_event_line_keeps_integers_and_booleans(captured: CapturedLog) -> None:
    captured.events.record(
        EventName.ACCOUNT_STATUS_CHANGED, old_is_active=True, new_is_active=False, duration_ms=12
    )

    (line,) = captured.lines()

    assert (line["old_is_active"], line["new_is_active"], line["duration_ms"]) == (True, False, 12)


@pytest.mark.parametrize(("event", "level"), LEVELS_OF_THE_CATALOG)
def test_event_line_has_the_level_of_the_catalog(
    captured: CapturedLog, event: EventName, level: str
) -> None:
    captured.events.record(event)

    (line,) = captured.lines()

    assert line["level"] == level


def test_handled_input_line_has_the_handled_input_level_of_the_event(
    captured: CapturedLog,
) -> None:
    captured.events.record_handled_input(EventName.PSEUDONYMIZATION_FAILED)

    (line,) = captured.lines()

    assert line["level"] == "warning"
    assert line["event"] == "pseudonymization.failed"


def test_event_line_keeps_the_catalog_level_of_an_event_with_a_handled_input_level(
    captured: CapturedLog,
) -> None:
    captured.events.record(EventName.PSEUDONYMIZATION_FAILED)

    (line,) = captured.lines()

    assert line["level"] == "error"
    assert line["event"] == "pseudonymization.failed"


@pytest.mark.parametrize(("event", "level"), LEVELS_OF_THE_CATALOG)
def test_handled_input_line_of_an_event_without_a_handled_input_level_keeps_its_level(
    captured: CapturedLog, event: EventName, level: str
) -> None:
    captured.events.record_handled_input(event)

    (line,) = captured.lines()

    assert line["level"] == level


def test_event_line_carries_the_trace_and_span_of_the_current_span(captured: CapturedLog) -> None:
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("test_span") as span:
        captured.events.record(EventName.TICKET_CREATED)
        context = span.get_span_context()

    (line,) = captured.lines()
    assert line["trace_id"] == format(context.trace_id, "032x")
    assert line["span_id"] == format(context.span_id, "016x")


def test_event_lines_outside_a_span_carry_the_trace_of_the_process(captured: CapturedLog) -> None:
    captured.events.record(EventName.TICKET_CREATED)
    captured.events.record(EventName.TICKET_CREATED)

    (first, second) = captured.lines()

    assert re.fullmatch(r"[0-9a-f]{32}", str(first["trace_id"])) is not None
    assert re.fullmatch(r"[0-9a-f]{16}", str(first["span_id"])) is not None
    assert (first["trace_id"], first["span_id"]) == (second["trace_id"], second["span_id"])


def test_library_record_is_forwarded_with_a_redacted_message(captured: CapturedLog) -> None:
    captured.logger.warning("Key (order_id)=(%s) already exists for %s", ORDER_ID, EMAIL)

    (line,) = captured.lines()

    assert line["event"] == "log.forwarded"
    assert line["message"] == f"Key (order_id)=({REDACTED}) already exists for {REDACTED}"
    assert line["logger_name"] == "supportiq_backend.test"


def test_record_with_an_exception_keeps_only_the_error_type(captured: CapturedLog) -> None:
    secret_text = "The left side of the headphones makes no sound"
    error = ValueError(secret_text)
    record = captured.logger.makeRecord(
        "uvicorn.error", logging.ERROR, __file__, 1, "Failure", (), (ValueError, error, None)
    )

    captured.logger.handle(record)

    (line,) = captured.lines()

    assert line["error_type"] == "ValueError"
    assert secret_text not in captured.text()


@pytest.mark.usefixtures("restored_root_logger")
def test_configure_logging_sends_records_to_the_stream_as_json() -> None:
    stream = io.StringIO()

    backend_logger = configure_logging(stream, REDACTOR)
    StandardLibraryEventRecorder(backend_logger).record(EventName.STARTUP_COMPLETED)

    assert backend_logger.name == BACKEND_LOGGER_NAME
    assert json.loads(stream.getvalue())["event"] == "startup.completed"
    assert logging.getLogger("uvicorn.access").disabled


@pytest.mark.usefixtures("restored_root_logger")
def test_configure_logging_drops_library_records_below_warning() -> None:
    stream = io.StringIO()

    configure_logging(stream, REDACTOR)
    logging.getLogger("uvicorn.error").info("Started server process")

    assert stream.getvalue() == ""

"""The single logging setup of ai-service: JSON lines, allow-listed attributes (LOG-03).

Every record leaves as one JSON line with the fields of LOG-09. Only the attributes of
`ALLOWED_ATTRIBUTES` survive, as scalars (LOG-10), and every string is redacted for the
generic personal-data patterns (LOG-30). Records of libraries become `log.forwarded` events
whose message is redacted and whose traceback is reduced to the error type, because a library
message can quote a request value. This module follows the logging setup of backend.
"""

import json
import logging
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TextIO, assert_never

from opentelemetry import trace

from app.platform.domain import (
    EVENT_DESCRIPTIONS,
    SERVICE_NAME,
    TRACE_ID_FORMAT,
    EventAttributeValue,
    EventLevel,
    EventName,
)

AI_SERVICE_LOGGER_NAME = "app"
REDACTED = "<redacted>"
# The attributes that may leave the process, besides the fixed fields of LOG-09. Each one is
# Internal data (SEC-01). An attribute that is not listed here is dropped.
ALLOWED_ATTRIBUTES = frozenset(
    {
        "reason_code",
        "duration_ms",
        "error_type",
        "release_id",
        "model_version",
        "kb_version",
        "prompt_version",
        "http_method",
        "http_route",
        "http_status_code",
        "setting_names",
        "file_name",
        "reason",
        "asset",
        "file_path",
        "mask_type",
        "mask_count",
        "logger_name",
        # The events of the pipeline: versions, counts, reason codes, and durations only, never
        # a text of the message, the KB, or the draft (LOG-29).
        "index_version",
        "mapping_version",
        "document_count",
        "recommendation",
        "reason_codes",
        "warning_count",
        "analysis_ms",
        "llm_ms",
        "total_ms",
        "segment_count",
        "citation_count",
        "input_token_count",
        "output_token_count",
        "cost_micro_usd",
    }
)
# Email addresses, and long random tokens such as the service token or an API key.
GENERIC_REDACTION_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"[A-Za-z0-9_-]{40,}"),
)
_EVENT_KEY = "supportiq_event"
_ATTRIBUTES_KEY = "supportiq_attributes"
_SPAN_ID_FORMAT = "016x"
_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8


@dataclass(frozen=True, slots=True)
class _EventAttributes:
    values: tuple[tuple[str, EventAttributeValue], ...]


class Redactor:
    """Replace every match of the known personal-data patterns with `REDACTED`."""

    def __init__(self, patterns: Iterable[re.Pattern[str]]) -> None:
        """Keep the patterns.

        Args:
            patterns: The patterns to redact, applied in order.
        """
        self._patterns = tuple(patterns)

    def redact(self, text: str) -> str:
        """Return the text with every known pattern replaced.

        Args:
            text: Any text that leaves the process.

        Returns:
            The redacted text.
        """
        for pattern in self._patterns:
            text = pattern.sub(REDACTED, text)
        return text


class JsonLogFormatter(logging.Formatter):
    """Format a record as one JSON line with the fields of LOG-09."""

    def __init__(self, redactor: Redactor) -> None:
        """Keep the redactor.

        Args:
            redactor: The redactor applied to every string of the line.
        """
        super().__init__()
        self._redactor = redactor
        # A library can log outside every request, as uvicorn does at startup. These IDs keep
        # such lines searchable, per process (LOG-06).
        self._process_trace: dict[str, EventAttributeValue] = {
            "trace_id": secrets.token_hex(_TRACE_ID_BYTES),
            "span_id": secrets.token_hex(_SPAN_ID_BYTES),
        }

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as one JSON line.

        Args:
            record: The record to format.

        Returns:
            The JSON line, without a line break.
        """
        event = record.__dict__.get(_EVENT_KEY)
        line: dict[str, EventAttributeValue] = {
            "timestamp": _format_timestamp(record.created),
            "level": _level_name(record.levelno),
            "service": SERVICE_NAME,
        }
        if isinstance(event, EventName):
            line["event"] = event.value
            line["message"] = EVENT_DESCRIPTIONS[event].message
        else:
            line["event"] = EventName.LOG_FORWARDED.value
            line["message"] = self._redactor.redact(record.getMessage())
            line["logger_name"] = record.name
        line.update(_trace_fields(self._process_trace))
        line.update(self._allowed_attributes(record))
        if record.exc_info is not None and record.exc_info[0] is not None:
            line["error_type"] = record.exc_info[0].__qualname__
        return json.dumps(line, ensure_ascii=False, separators=(",", ":"))

    def _allowed_attributes(self, record: logging.LogRecord) -> dict[str, EventAttributeValue]:
        attributes = record.__dict__.get(_ATTRIBUTES_KEY)
        if not isinstance(attributes, _EventAttributes):
            return {}
        return {
            name: self._redactor.redact(value) if isinstance(value, str) else value
            for name, value in attributes.values
            if name in ALLOWED_ATTRIBUTES
        }


class StandardLibraryEventRecorder:
    """Implement the `EventRecorder` port with the standard `logging` module."""

    def __init__(self, logger: logging.Logger) -> None:
        """Keep the logger.

        Args:
            logger: The logger from `configure_logging`.
        """
        self._logger = logger

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Log one event of the catalog with its fixed level and message.

        Args:
            event: The event from the catalog.
            **attributes: Scalar attributes. The formatter drops those not allow-listed.
        """
        description = EVENT_DESCRIPTIONS[event]
        self._logger.log(
            _level_number(description.level),
            description.message,
            extra={
                _EVENT_KEY: event,
                _ATTRIBUTES_KEY: _EventAttributes(tuple(sorted(attributes.items()))),
            },
        )


def configure_logging(stream: TextIO, redactor: Redactor) -> logging.Logger:
    """Send every log record of the process to the stream as JSON lines (LOG-02, LOG-03).

    Library records below `warning` are dropped. Records of ai-service from `info` up are
    kept. `debug` is off, as LOG-15 requires in shared environments.

    Args:
        stream: Where the lines go, standard output in production.
        redactor: The redactor applied to every string.

    Returns:
        The logger of ai-service, for `StandardLibraryEventRecorder`.
    """
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter(redactor))
    root = logging.getLogger()
    for existing in tuple(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    service_logger = logging.getLogger(AI_SERVICE_LOGGER_NAME)
    service_logger.setLevel(logging.INFO)
    # Uvicorn's access log holds the raw path and query. Request logs come from the request
    # logging middleware instead, with the route template only.
    logging.getLogger("uvicorn.access").disabled = True
    return service_logger


def _format_timestamp(created: float) -> str:
    moment = datetime.fromtimestamp(created, UTC)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _trace_fields(process_trace: dict[str, EventAttributeValue]) -> dict[str, EventAttributeValue]:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return process_trace
    return {
        "trace_id": format(span_context.trace_id, TRACE_ID_FORMAT),
        "span_id": format(span_context.span_id, _SPAN_ID_FORMAT),
    }


def _level_name(level_number: int) -> str:
    if level_number >= logging.ERROR:
        return EventLevel.ERROR.value
    if level_number >= logging.WARNING:
        return EventLevel.WARNING.value
    if level_number >= logging.INFO:
        return EventLevel.INFO.value
    return EventLevel.DEBUG.value


def _level_number(level: EventLevel) -> int:
    match level:
        case EventLevel.DEBUG:
            return logging.DEBUG
        case EventLevel.INFO:
            return logging.INFO
        case EventLevel.WARNING:
            return logging.WARNING
        case EventLevel.ERROR:
            return logging.ERROR
        case _:
            assert_never(level)

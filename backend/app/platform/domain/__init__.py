"""Domain types of platform: ports and errors that every feature shares (ARCH-19)."""

from app.platform.domain.clock import MILLISECONDS_PER_SECOND, Clock
from app.platform.domain.errors import (
    BackendError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    ErrorCode,
    InvalidCursorError,
    InvalidLimitError,
    InvalidParameterError,
    InvalidRequestError,
    RequestContractError,
    ResourceNotFoundError,
    UnexpectedFailureError,
)
from app.platform.domain.events import (
    EVENT_DESCRIPTIONS,
    SERVICE_NAME,
    EventAttributeValue,
    EventDescription,
    EventLevel,
    EventName,
    EventRecorder,
)
from app.platform.domain.identity import (
    TRACE_ID_FORMAT,
    IdGenerator,
    SpanName,
    StepTracer,
    TraceContext,
    TraceId,
)
from app.platform.domain.operations import OperationId
from app.platform.domain.readiness import ReadinessProbe
from app.platform.domain.text import is_storable_text
from app.platform.domain.timestamps import (
    UTC_OFFSET,
    NonUtcTimestampError,
    format_timestamp,
    parse_timestamp,
)
from app.platform.domain.transactions import Transaction, TransactionRunner

__all__ = [
    "EVENT_DESCRIPTIONS",
    "MILLISECONDS_PER_SECOND",
    "SERVICE_NAME",
    "TRACE_ID_FORMAT",
    "UTC_OFFSET",
    "BackendError",
    "Clock",
    "DatabaseOperationError",
    "DatabaseUnavailableError",
    "ErrorCode",
    "EventAttributeValue",
    "EventDescription",
    "EventLevel",
    "EventName",
    "EventRecorder",
    "IdGenerator",
    "InvalidCursorError",
    "InvalidLimitError",
    "InvalidParameterError",
    "InvalidRequestError",
    "NonUtcTimestampError",
    "OperationId",
    "ReadinessProbe",
    "RequestContractError",
    "ResourceNotFoundError",
    "SpanName",
    "StepTracer",
    "TraceContext",
    "TraceId",
    "Transaction",
    "TransactionRunner",
    "UnexpectedFailureError",
    "format_timestamp",
    "is_storable_text",
    "parse_timestamp",
]

"""Domain types of platform: ports and errors that every feature shares (ARCH-19)."""

from supportiq_backend.platform.domain.clock import MILLISECONDS_PER_SECOND, Clock
from supportiq_backend.platform.domain.errors import (
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
from supportiq_backend.platform.domain.events import (
    EVENT_DESCRIPTIONS,
    SERVICE_NAME,
    EventAttributeValue,
    EventDescription,
    EventLevel,
    EventName,
    EventRecorder,
)
from supportiq_backend.platform.domain.identity import (
    TRACE_ID_FORMAT,
    IdGenerator,
    SpanName,
    StepTracer,
    TraceContext,
    TraceId,
)
from supportiq_backend.platform.domain.operations import OperationId
from supportiq_backend.platform.domain.readiness import ReadinessProbe
from supportiq_backend.platform.domain.text import is_storable_text
from supportiq_backend.platform.domain.transactions import Transaction, TransactionRunner

__all__ = [
    "EVENT_DESCRIPTIONS",
    "MILLISECONDS_PER_SECOND",
    "SERVICE_NAME",
    "TRACE_ID_FORMAT",
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
    "is_storable_text",
]

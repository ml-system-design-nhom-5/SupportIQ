"""Domain types of platform: ports and errors that every feature shares (ARCH-19)."""

from supportiq_ai_service.platform.domain.clock import (
    MILLISECONDS_PER_SECOND,
    TIMESTAMP_PATTERN,
    Clock,
)
from supportiq_ai_service.platform.domain.errors import (
    AiServiceError,
    ErrorCode,
    InvalidRequestError,
    RequestContractError,
    ResourceNotFoundError,
    ServiceTokenRejectedError,
    UnexpectedFailureError,
)
from supportiq_ai_service.platform.domain.events import (
    EVENT_DESCRIPTIONS,
    SERVICE_NAME,
    EventAttributeValue,
    EventDescription,
    EventLevel,
    EventName,
    EventRecorder,
)
from supportiq_ai_service.platform.domain.identity import TRACE_ID_FORMAT, TraceContext, TraceId
from supportiq_ai_service.platform.domain.readiness import ReadinessProbe

__all__ = [
    "EVENT_DESCRIPTIONS",
    "MILLISECONDS_PER_SECOND",
    "SERVICE_NAME",
    "TIMESTAMP_PATTERN",
    "TRACE_ID_FORMAT",
    "AiServiceError",
    "Clock",
    "ErrorCode",
    "EventAttributeValue",
    "EventDescription",
    "EventLevel",
    "EventName",
    "EventRecorder",
    "InvalidRequestError",
    "ReadinessProbe",
    "RequestContractError",
    "ResourceNotFoundError",
    "ServiceTokenRejectedError",
    "TraceContext",
    "TraceId",
    "UnexpectedFailureError",
]

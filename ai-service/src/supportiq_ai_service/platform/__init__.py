"""Public API of platform for every layer: ports, errors, and the event catalog (ARCH-17).

It holds only standard-library names, so domain code can import it. Interface code that
several features share is in `supportiq_ai_service.platform.web`, the second public entry
point of platform, which only interface layers and the composition root import.
"""

from supportiq_ai_service.platform.application import CheckReadiness
from supportiq_ai_service.platform.domain import (
    EVENT_DESCRIPTIONS,
    MILLISECONDS_PER_SECOND,
    SERVICE_NAME,
    TIMESTAMP_PATTERN,
    AiServiceError,
    Clock,
    ErrorCode,
    EventAttributeValue,
    EventDescription,
    EventLevel,
    EventName,
    EventRecorder,
    InvalidRequestError,
    ReadinessProbe,
    RequestContractError,
    ResourceNotFoundError,
    ServiceTokenRejectedError,
    TraceContext,
    TraceId,
    UnexpectedFailureError,
)

__all__ = [
    "EVENT_DESCRIPTIONS",
    "MILLISECONDS_PER_SECOND",
    "SERVICE_NAME",
    "TIMESTAMP_PATTERN",
    "AiServiceError",
    "CheckReadiness",
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

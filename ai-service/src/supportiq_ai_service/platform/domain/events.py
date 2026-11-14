"""The event catalog of ai-service and the port that records events (LOG-11, LOG-12).

Every log event of ai-service has its stable name, its level, and its fixed message here and
nowhere else. The ai-service README lists the same events.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

# The `service` field of every log record (LOG-09).
SERVICE_NAME = "ai-service"


class EventName(StrEnum):
    """The stable name of a log event: `<area>.<past_tense_verb>` (LOG-11)."""

    STARTUP_COMPLETED = "startup.completed"
    SETTINGS_LOADED = "settings.loaded"
    SETTINGS_INVALID = "settings.invalid"
    SHUTDOWN_STARTED = "shutdown.started"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"
    REQUEST_REFUSED = "request.refused"
    SERVICE_TOKEN_REJECTED = "service_token.rejected"  # noqa: S105  # an event name
    LOG_FORWARDED = "log.forwarded"


class EventLevel(StrEnum):
    """The severity of an event, with the meanings of LOG-15."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EventDescription:
    """The fixed level and message of one event.

    Attributes:
        level: The severity of the event (LOG-15).
        message: One sentence without variable data and without a trailing period (LOG-14).
    """

    level: EventLevel
    message: str


EVENT_DESCRIPTIONS: Mapping[EventName, EventDescription] = MappingProxyType(
    {
        EventName.STARTUP_COMPLETED: EventDescription(EventLevel.INFO, "ai-service started"),
        EventName.SETTINGS_LOADED: EventDescription(EventLevel.INFO, "Settings loaded"),
        EventName.SETTINGS_INVALID: EventDescription(
            EventLevel.ERROR, "Settings are missing or invalid, so ai-service stops"
        ),
        EventName.SHUTDOWN_STARTED: EventDescription(
            EventLevel.INFO, "ai-service is shutting down"
        ),
        EventName.REQUEST_COMPLETED: EventDescription(EventLevel.INFO, "Request completed"),
        EventName.REQUEST_FAILED: EventDescription(
            EventLevel.ERROR, "Request failed with an unexpected error"
        ),
        EventName.REQUEST_REFUSED: EventDescription(
            EventLevel.WARNING, "Request refused because ai-service is not ready"
        ),
        EventName.SERVICE_TOKEN_REJECTED: EventDescription(
            EventLevel.WARNING, "Request refused because it has no valid service token"
        ),
        EventName.LOG_FORWARDED: EventDescription(EventLevel.INFO, "Library log record"),
    }
)

type EventAttributeValue = str | int | bool


class EventRecorder(Protocol):
    """Record a log event with scalar attributes (LOG-07, LOG-10)."""

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Record one event.

        Args:
            event: The event from the catalog.
            **attributes: Internal values only, such as `release_id` (LOG-29). The logging
                setup drops every attribute that is not allow-listed.
        """
        ...

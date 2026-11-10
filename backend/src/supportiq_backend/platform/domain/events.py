"""The event catalog of backend and the port that records events (LOG-11, LOG-12).

Every log event of backend has its stable name, its level, and its fixed message here and
nowhere else. The backend README lists the same events.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

# The `service` field of every log record and the `service.name` of every span (LOG-09).
SERVICE_NAME = "backend"


class EventName(StrEnum):
    """The stable name of a log event: `<area>.<past_tense_verb>` (LOG-11)."""

    STARTUP_COMPLETED = "startup.completed"
    SETTINGS_LOADED = "settings.loaded"
    SETTINGS_INVALID = "settings.invalid"
    SHUTDOWN_STARTED = "shutdown.started"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"
    DATABASE_CALL_FAILED = "database.call_failed"
    LOG_FORWARDED = "log.forwarded"
    COMMAND_FAILED = "command.failed"
    DATABASE_MIGRATED = "database.migrated"
    DATABASE_ROLE_APPLIED = "database_role.applied"
    SEED_LOADED = "seed.loaded"
    SEED_RESET = "seed.reset"
    SEED_RESET_CANCELLED = "seed.reset_cancelled"
    SESSION_CREATED = "session.created"
    SIGN_IN_FAILED = "sign_in.failed"
    SIGN_IN_THROTTLED = "sign_in.throttled"
    PERMISSION_DENIED = "permission.denied"
    TICKET_CREATED = "ticket.created"
    ACCOUNT_ROLE_CHANGED = "account.role_changed"
    ACCOUNT_STATUS_CHANGED = "account.status_changed"


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
        EventName.STARTUP_COMPLETED: EventDescription(EventLevel.INFO, "Backend started"),
        EventName.SETTINGS_LOADED: EventDescription(EventLevel.INFO, "Settings loaded"),
        EventName.SETTINGS_INVALID: EventDescription(
            EventLevel.ERROR, "Settings are missing or invalid, so backend stops"
        ),
        EventName.SHUTDOWN_STARTED: EventDescription(EventLevel.INFO, "Backend is shutting down"),
        EventName.REQUEST_COMPLETED: EventDescription(EventLevel.INFO, "Request completed"),
        EventName.REQUEST_FAILED: EventDescription(
            EventLevel.ERROR, "Request failed with an unexpected error"
        ),
        EventName.DATABASE_CALL_FAILED: EventDescription(
            EventLevel.WARNING, "Request refused because the database is not available"
        ),
        EventName.LOG_FORWARDED: EventDescription(EventLevel.INFO, "Library log record"),
        EventName.COMMAND_FAILED: EventDescription(
            EventLevel.ERROR, "Command failed and changed nothing"
        ),
        EventName.DATABASE_MIGRATED: EventDescription(
            EventLevel.INFO, "Database migrated to the latest revision"
        ),
        EventName.DATABASE_ROLE_APPLIED: EventDescription(
            EventLevel.INFO, "Application database role created or updated"
        ),
        EventName.SEED_LOADED: EventDescription(EventLevel.INFO, "Seed data loaded"),
        EventName.SEED_RESET: EventDescription(EventLevel.INFO, "Backend tables reset to the seed"),
        EventName.SEED_RESET_CANCELLED: EventDescription(
            EventLevel.INFO, "Reset cancelled without changes"
        ),
        EventName.SESSION_CREATED: EventDescription(EventLevel.INFO, "Session created"),
        EventName.SIGN_IN_FAILED: EventDescription(
            EventLevel.INFO, "Sign-in refused because the credentials were not accepted"
        ),
        EventName.SIGN_IN_THROTTLED: EventDescription(
            EventLevel.WARNING, "Sign-in refused because the login name reached the failure limit"
        ),
        EventName.PERMISSION_DENIED: EventDescription(
            EventLevel.WARNING, "Request refused because the role may not call the operation"
        ),
        EventName.TICKET_CREATED: EventDescription(EventLevel.INFO, "Ticket created"),
        EventName.ACCOUNT_ROLE_CHANGED: EventDescription(EventLevel.INFO, "Account role changed"),
        EventName.ACCOUNT_STATUS_CHANGED: EventDescription(
            EventLevel.INFO, "Account status changed"
        ),
    }
)

type EventAttributeValue = str | int | bool


class EventRecorder(Protocol):
    """Record a log event with scalar attributes (LOG-07, LOG-10)."""

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Record one event.

        Args:
            event: The event from the catalog.
            **attributes: Internal values only, such as `ticket_id` or `role` (LOG-29). The
                logging setup drops every attribute that is not allow-listed.
        """
        ...

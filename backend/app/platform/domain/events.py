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
    SEED_SKIPPED = "seed.skipped"
    SEED_RESET = "seed.reset"
    SEED_RESET_CANCELLED = "seed.reset_cancelled"
    SESSION_CREATED = "session.created"
    SIGN_IN_FAILED = "sign_in.failed"
    SIGN_IN_THROTTLED = "sign_in.throttled"
    PERMISSION_DENIED = "permission.denied"
    TICKET_CREATED = "ticket.created"
    SUGGESTION_REQUESTED = "suggestion.requested"
    SUGGESTION_SUPERSEDED = "suggestion.superseded"
    SUGGESTION_PART_CANCELLED = "suggestion.part_cancelled"
    SUGGESTION_COMPLETED = "suggestion.completed"
    SUGGESTION_JOB_CLAIMED = "suggestion_job.claimed"
    SUGGESTION_JOB_LEASE_EXPIRED = "suggestion_job.lease_expired"
    SUGGESTION_JOB_FAILED = "suggestion_job.failed"
    SUGGESTION_STREAM_ENDED = "suggestion_stream.ended"
    SUGGESTION_STREAM_FAILED = "suggestion_stream.failed"
    PSEUDONYMIZATION_FAILED = "pseudonymization.failed"
    PSEUDONYM_RESTORE_FAILED = "pseudonym.restore_failed"
    AI_SERVICE_CALLED = "ai_service.called"
    AI_SERVICE_CALL_FAILED = "ai_service.call_failed"
    AI_SERVICE_CONTRACT_VIOLATED = "ai_service.contract_violated"
    TICKET_VIEWED = "ticket.viewed"
    TICKET_MANUAL_HANDLING_STARTED = "ticket.manual_handling_started"
    INTENT_OVERRIDDEN = "intent.overridden"
    REPLY_PROPOSAL_SUBMITTED = "reply_proposal.submitted"
    DECISION_RECORDED = "decision.recorded"
    REPLY_SENT = "reply.sent"
    TICKET_ESCALATED = "ticket.escalated"
    REPORT_BUILT = "report.built"
    DECISIONS_EXPORTED = "decisions.exported"
    ACCOUNT_ROLE_CHANGED = "account.role_changed"
    ACCOUNT_STATUS_CHANGED = "account.status_changed"
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_PASSWORD_CHANGED = "account.password_changed"  # noqa: S105  # an event name
    ACCOUNT_PASSWORD_RESET = "account.password_reset"  # noqa: S105  # an event name
    PASSWORD_CHANGE_FAILED = "password_change.failed"  # noqa: S105  # an event name
    PASSWORD_CHANGE_THROTTLED = "password_change.throttled"  # noqa: S105  # an event name


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
        handled_input_level: The severity when the event comes from input that backend
            handles as designed instead of from a defect, for the few events that a design
            gives two levels, such as `pseudonymization.failed` (ADR-0010, Failure handling).
            Absent for every other event.
    """

    level: EventLevel
    message: str
    handled_input_level: EventLevel | None = None


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
        EventName.SEED_SKIPPED: EventDescription(
            EventLevel.INFO, "Seed skipped because the database already holds seed rows"
        ),
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
        EventName.SUGGESTION_REQUESTED: EventDescription(
            EventLevel.INFO, "Suggestion created and its job queued"
        ),
        EventName.SUGGESTION_SUPERSEDED: EventDescription(
            EventLevel.INFO, "Suggestion superseded by a newer one of the ticket"
        ),
        EventName.SUGGESTION_PART_CANCELLED: EventDescription(
            EventLevel.INFO, "Running call cancelled because its suggestion was superseded"
        ),
        EventName.SUGGESTION_COMPLETED: EventDescription(
            EventLevel.INFO, "Suggestion completed with no part pending"
        ),
        EventName.SUGGESTION_JOB_CLAIMED: EventDescription(
            EventLevel.INFO, "Suggestion job claimed under a lease"
        ),
        EventName.SUGGESTION_JOB_LEASE_EXPIRED: EventDescription(
            EventLevel.WARNING,
            "Suggestion job ran out of attempts, so its pending parts are unavailable",
        ),
        EventName.SUGGESTION_JOB_FAILED: EventDescription(
            EventLevel.ERROR, "Suggestion job failed and waits for its lease to expire"
        ),
        EventName.SUGGESTION_STREAM_ENDED: EventDescription(
            EventLevel.INFO, "Suggestion progress stream ended"
        ),
        EventName.SUGGESTION_STREAM_FAILED: EventDescription(
            EventLevel.WARNING, "Suggestion progress stream ended because a re-read failed"
        ),
        EventName.PSEUDONYMIZATION_FAILED: EventDescription(
            EventLevel.ERROR,
            "Pseudonymization failed, so nothing was sent to ai-service",
            handled_input_level=EventLevel.WARNING,
        ),
        EventName.PSEUDONYM_RESTORE_FAILED: EventDescription(
            EventLevel.ERROR, "A pseudonym in stored AI text is missing from the map"
        ),
        EventName.AI_SERVICE_CALLED: EventDescription(
            EventLevel.INFO, "Call to ai-service answered with a result"
        ),
        EventName.AI_SERVICE_CALL_FAILED: EventDescription(
            EventLevel.WARNING, "Call to ai-service timed out, was unreachable, or failed"
        ),
        EventName.AI_SERVICE_CONTRACT_VIOLATED: EventDescription(
            EventLevel.ERROR, "Call to ai-service was refused or answered outside its contract"
        ),
        EventName.TICKET_VIEWED: EventDescription(EventLevel.INFO, "Ticket view recorded"),
        EventName.TICKET_MANUAL_HANDLING_STARTED: EventDescription(
            EventLevel.WARNING, "The AI could not run, so the ticket is handled manually"
        ),
        EventName.INTENT_OVERRIDDEN: EventDescription(
            EventLevel.INFO, "Intent confirmed or corrected by staff"
        ),
        EventName.REPLY_PROPOSAL_SUBMITTED: EventDescription(
            EventLevel.INFO, "Reply proposal submitted for a manager to send"
        ),
        EventName.DECISION_RECORDED: EventDescription(EventLevel.INFO, "Staff decision recorded"),
        EventName.REPLY_SENT: EventDescription(EventLevel.INFO, "Reply sent to the customer"),
        EventName.TICKET_ESCALATED: EventDescription(
            EventLevel.INFO, "Ticket escalated to the manager queue"
        ),
        EventName.REPORT_BUILT: EventDescription(
            EventLevel.INFO, "Report of a period built for a manager"
        ),
        EventName.DECISIONS_EXPORTED: EventDescription(
            EventLevel.INFO, "Decision records of a period written to the export file"
        ),
        EventName.ACCOUNT_ROLE_CHANGED: EventDescription(EventLevel.INFO, "Account role changed"),
        EventName.ACCOUNT_STATUS_CHANGED: EventDescription(
            EventLevel.INFO, "Account status changed"
        ),
        EventName.ACCOUNT_CREATED: EventDescription(EventLevel.INFO, "Account created"),
        EventName.ACCOUNT_PASSWORD_CHANGED: EventDescription(
            EventLevel.INFO, "Password changed by the owner of the account"
        ),
        EventName.ACCOUNT_PASSWORD_RESET: EventDescription(
            EventLevel.INFO, "Password reset by an admin"
        ),
        EventName.PASSWORD_CHANGE_FAILED: EventDescription(
            EventLevel.INFO, "Password change refused because the current password was not correct"
        ),
        EventName.PASSWORD_CHANGE_THROTTLED: EventDescription(
            EventLevel.WARNING,
            "Password change refused because the login name reached the failure limit",
        ),
    }
)

type EventAttributeValue = str | int | bool


class EventRecorder(Protocol):
    """Record a log event with scalar attributes (LOG-07, LOG-10)."""

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Record one event at the level of the catalog.

        Args:
            event: The event from the catalog.
            **attributes: Internal values only, such as `ticket_id` or `role` (LOG-29). The
                logging setup drops every attribute that is not allow-listed.
        """
        ...

    def record_handled_input(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Record one event that handled input caused, at its `handled_input_level`.

        Args:
            event: An event of the catalog that has a `handled_input_level`; any other event
                keeps its level.
            **attributes: As for `record`.
        """
        ...

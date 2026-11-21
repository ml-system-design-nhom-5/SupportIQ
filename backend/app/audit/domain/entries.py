"""Audit log entries and the port that appends them (SEC-39, contracts v1 design, Audit log)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType, Protocol
from uuid import UUID

from app.platform import TraceId

AuditEntryId = NewType("AuditEntryId", UUID)
# The account that acted, in the form `accounts` gives it: a canonical UUID text. Internal.
ActorAccountId = NewType("ActorAccountId", str)
# The ticket an entry is about, such as `TCK-1042`. Internal.
AuditTicketId = NewType("AuditTicketId", str)
# The values of `data`: identifiers, statuses, reason codes, versions, and numbers only, never
# a text that a person wrote and never an order ID (SEC-39).
type AuditValue = str | int | bool


class AuditEventType(StrEnum):
    """The event types of the audit log, exactly those of the contracts v1 design."""

    MESSAGE_PSEUDONYMIZED = "message.pseudonymized"
    SUGGESTION_PART_COMPLETED = "suggestion.part_completed"
    INTENT_OVERRIDDEN = "intent.overridden"
    REPLY_PROPOSAL_SUBMITTED = "reply_proposal.submitted"
    REPLY_SENT = "reply.sent"
    DECISION_RECORDED = "decision.recorded"
    TICKET_ESCALATED = "ticket.escalated"
    ACCOUNT_ROLE_CHANGED = "account.role_changed"
    ACCOUNT_STATUS_CHANGED = "account.status_changed"
    ACCOUNT_CREATED = "account.created"
    ACCOUNT_PASSWORD_CHANGED = "account.password_changed"  # noqa: S105  # an event type
    ACCOUNT_PASSWORD_RESET = "account.password_reset"  # noqa: S105  # an event type


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One entry of the insert-only audit log, written in the transaction of its change.

    Attributes:
        entry_id: The identifier of the entry.
        occurred_at: When the change happened, in UTC.
        event_type: What happened.
        actor_account_id: Who acted; absent for system events.
        ticket_id: The ticket concerned, when there is one.
        trace_id: The trace of the request that made the change.
        data: The recorded data of the event type.
    """

    entry_id: AuditEntryId
    occurred_at: datetime
    event_type: AuditEventType
    actor_account_id: ActorAccountId | None
    ticket_id: AuditTicketId | None
    trace_id: TraceId
    data: Mapping[str, AuditValue]


class AuditLog(Protocol):
    """Append entries to the audit log, inside the caller's transaction."""

    async def append(self, entry: AuditEntry) -> None:
        """Append one entry; it is committed or rolled back with the change it records.

        Args:
            entry: The entry.
        """
        ...

"""The decision records of `backend export-decisions`, for the evaluation and the study (SEC-33).

One record per ticket closed or escalated in the period: the ticket's times and handling mode,
the snapshot of its current suggestion, and the staff decisions with their reason codes
(backend ticket workflow design, The decision-record export). Message and draft text appear only
in pseudonymized form, as `backend` sent and received them. A record never holds the sent reply
body, a note, the AI's staff note, or a value of the pseudonym map (SEC-37).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from supportiq_backend.suggestions import (
    AiReasonCode,
    IntentLabel,
    PartStatus,
    SuggestionId,
    SuggestionTrigger,
)
from supportiq_backend.tickets import DecisionType, HandlingMode, StaffReasonCode, TicketId

# A value of a JSON document as stored: the fields of an ai-service response that the export
# passes on without reading them.
type JsonValue = str | int | float | bool | Sequence[JsonValue] | Mapping[str, JsonValue] | None


@dataclass(frozen=True, slots=True, repr=False)
class ExportedPart:
    """One part of a suggestion, as stored.

    Attributes:
        status: The stored status.
        reason_codes: The stored AI reason codes.
        completed_at: When the part left `pending`; None while it is pending.
        result_fields: The fields of the stored ai-service response that the evaluation needs,
            with placeholders in its text; None for a part without a result. Confidential.
    """

    status: PartStatus
    reason_codes: tuple[AiReasonCode, ...]
    completed_at: datetime | None
    result_fields: Mapping[str, JsonValue] | None


@dataclass(frozen=True, slots=True, repr=False)
class SuggestionSnapshot:
    """The current suggestion of a ticket: what the AI produced and staff saw (ADR-0006).

    Attributes:
        suggestion_id: The suggestion.
        trigger: Why it was created.
        intent_override: The intent that staff chose, when they chose one.
        created_at: When it was created.
        pseudonymized_message: The message as sent to ai-service; None when pseudonymization
            did not succeed, so nothing was sent. Confidential.
        analysis: The analysis part.
        draft: The draft part.
    """

    suggestion_id: SuggestionId
    trigger: SuggestionTrigger
    intent_override: IntentLabel | None
    created_at: datetime
    pseudonymized_message: str | None
    analysis: ExportedPart
    draft: ExportedPart


@dataclass(frozen=True, slots=True)
class ExportedDecision:
    """One staff decision about a ticket; it holds no text (ADR-0006).

    Attributes:
        decision_type: Approve, edit, reject, or escalate.
        staff_reason_codes: The staff reason codes.
        change_ratio: How much the sent body differs from the draft, from 0 to 1, for an edit
            or an approval; None otherwise.
        final_intent: The intent of the suggestion the decision was about, when known.
        is_proposal_changed: Whether the manager changed a reply proposal, for a reply from a
            proposal; None otherwise.
        decided_at: When it was recorded.
    """

    decision_type: DecisionType
    staff_reason_codes: tuple[StaffReasonCode, ...]
    change_ratio: float | None
    final_intent: IntentLabel | None
    is_proposal_changed: bool | None
    decided_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class DecisionRecord:
    """The record of one ticket closed or escalated in the period.

    Attributes:
        ticket_id: The ticket.
        handling_mode: `assisted` or `manual`.
        study_pair_id: The study pair of an imported ticket, when it has one.
        study_batch: The study batch of an imported ticket, when it has one.
        created_at: When the ticket was created.
        handling_started_at: The first view, when there was one.
        escalated_at: When the ticket was escalated, when it was.
        closed_at: When the reply was sent, when it was.
        handling_time_ms: From the first view to the reply, in whole milliseconds; None for a
            ticket that is not closed, was never viewed, or was first viewed after its reply.
        suggestion: The current suggestion; None for a ticket without one, such as a ticket in
            manual mode.
        decisions: The staff decisions, oldest first.
    """

    ticket_id: TicketId
    handling_mode: HandlingMode
    study_pair_id: str | None
    study_batch: str | None
    created_at: datetime
    handling_started_at: datetime | None
    escalated_at: datetime | None
    closed_at: datetime | None
    handling_time_ms: int | None
    suggestion: SuggestionSnapshot | None
    decisions: tuple[ExportedDecision, ...]

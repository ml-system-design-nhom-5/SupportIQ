"""Builders of suggestions with their two parts and their job (TEST-05)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, null, update

from supportiq_backend.suggestions.adapters.tables import (
    SuggestionJobRow,
    SuggestionPartRow,
    SuggestionRow,
)
from supportiq_backend.tickets.adapters.tables import TicketRow
from tests.integration.builders.rows import RowWriter


@dataclass(frozen=True, slots=True)
class SuggestionPartSpec:
    """One part of a suggestion with a state of its own, as stored.

    Attributes:
        status: The status.
        completed_at: When it left `pending`; None exactly for a pending part.
        reason_codes: The AI reason codes.
        llm_cost_micro_usd: The LLM cost, if the LLM answered.
        result: The ai-service response, if the part has one.
    """

    status: str = "pending"
    completed_at: datetime | None = None
    reason_codes: tuple[str, ...] = ()
    llm_cost_micro_usd: int | None = None
    result: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SuggestionSpec:
    """A current suggestion of a ticket whose two parts share one state, and its job.

    Attributes:
        part_status: The status of both parts: `pending`, or `unavailable` with a reason.
        reason_code: The reason code of both parts; set exactly when they are not pending.
        job_state: The state of its job.
        created_at: When it was created; the next time of the builder when None.
        trigger: Why it was created.
        intent_override: The intent that staff chose, for the trigger `intent_override`.
        requested_by_account_id: The staff account that asked for it; set exactly when the
            trigger is not `ticket_created`.
        request: The `SuggestionRequest` as sent; None before pseudonymization succeeded.
        analysis: The analysis part with a state of its own, in place of the shared one.
        draft: The draft part with a state of its own, in place of the shared one.
    """

    part_status: str = "pending"
    reason_code: str | None = None
    job_state: str = "queued"
    created_at: datetime | None = None
    trigger: str = "ticket_created"
    intent_override: str | None = None
    requested_by_account_id: UUID | None = None
    request: dict[str, object] | None = None
    analysis: SuggestionPartSpec | None = None
    draft: SuggestionPartSpec | None = None


# A suggestion whose calls to ai-service failed, so a retry is valid (contract
# `createSuggestion`).
FAILED_SUGGESTION = SuggestionSpec("unavailable", "ai_service_unavailable", "done")
SUGGESTION_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


class SuggestionRows:
    """Insert suggestions."""

    def __init__(self, writer: RowWriter) -> None:
        """Keep the writer that every area shares.

        Args:
            writer: Writes the rows and gives their deterministic values.
        """
        self._writer = writer

    async def suggestion(self, ticket_id: str, spec: SuggestionSpec) -> UUID:
        """Insert a suggestion with its two parts and its job, and make it the current one.

        Args:
            ticket_id: The ticket.
            spec: The suggestion, its parts, and its job.

        Returns:
            The suggestion ID.
        """
        suggestion_id = self._writer.next_uuid()
        moment = spec.created_at or self._writer.next_time()
        shared = _shared_part(spec, moment)
        parts = {"analysis": spec.analysis or shared, "draft": spec.draft or shared}
        await self._writer.execute(
            insert(SuggestionRow).values(
                suggestion_id=suggestion_id,
                ticket_id=ticket_id,
                trigger=spec.trigger,
                intent_override=spec.intent_override,
                requested_by_account_id=spec.requested_by_account_id,
                created_at=moment,
                trace_id=SUGGESTION_TRACE_ID,
                request=null() if spec.request is None else spec.request,
            ),
            insert(SuggestionPartRow).values(
                [_part_values(suggestion_id, name, part) for name, part in parts.items()]
            ),
            insert(SuggestionJobRow).values(
                suggestion_id=suggestion_id,
                state=spec.job_state,
                attempt_number=0 if spec.job_state == "queued" else 1,
                created_at=moment,
                updated_at=moment,
            ),
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(current_suggestion_id=suggestion_id),
        )
        return suggestion_id


def _shared_part(spec: SuggestionSpec, moment: datetime) -> SuggestionPartSpec:
    # The state of both parts, unless the spec gives a part a state of its own.
    return SuggestionPartSpec(
        status=spec.part_status,
        completed_at=None if spec.part_status == "pending" else moment,
        reason_codes=() if spec.reason_code is None else (spec.reason_code,),
    )


def _part_values(suggestion_id: UUID, part: str, spec: SuggestionPartSpec) -> dict[str, object]:
    return {
        "suggestion_id": suggestion_id,
        "part": part,
        "status": spec.status,
        "reason_codes": list(spec.reason_codes),
        "llm_cost_micro_usd": spec.llm_cost_micro_usd,
        "completed_at": spec.completed_at,
        "result": null() if spec.result is None else spec.result,
    }

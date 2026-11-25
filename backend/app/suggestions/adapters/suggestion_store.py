"""The suggestion ports on `suggestions`, `suggestion_parts`, and `suggestion_jobs`.

A trigger rejects every update of a part whose status is no longer `pending`, and every
second write of `suggestions.request`, so every statement here changes only pending parts and
absent requests (backend ticket workflow design, Tables).
"""

import json
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import ScalarSelect, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.accounts import AccountId
from app.platform import TraceId, UnexpectedFailureError
from app.platform.persistence import (
    parse_optional_stored_enum,
    parse_stored_enum,
)
from app.suggestions.adapters.ai_service_payloads import (
    parse_stored_analysis,
    parse_stored_draft_outcome,
    parse_stored_order_context,
    to_request_body,
)
from app.suggestions.adapters.tables import (
    SuggestionJobRow,
    SuggestionPartRow,
    SuggestionRow,
)
from app.suggestions.domain import (
    AiReasonCode,
    AiServiceContractError,
    AnalysisState,
    CancelledPart,
    ClaimedJob,
    DraftState,
    IntentLabel,
    JobState,
    LockedJob,
    NewSuggestion,
    PartCompletion,
    PartStatus,
    PendingPart,
    Suggestion,
    SuggestionId,
    SuggestionPart,
    SuggestionProgress,
    SuggestionRequest,
    SuggestionTicketId,
    SuggestionTrigger,
    UnavailablePart,
)

_PENDING = PartStatus.PENDING.value


class PostgresSuggestionStore:
    """Implement the `SuggestionStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def cancel_pending_suggestions(
        self, ticket_id: SuggestionTicketId, completed_at: datetime
    ) -> tuple[SuggestionId, ...]:
        """Cancel every pending part of the ticket's suggestions and end their jobs.

        Args:
            ticket_id: The ticket, locked by the transaction.
            completed_at: When the parts were cancelled.

        Returns:
            The suggestions that had a pending part.
        """
        of_ticket = select(SuggestionRow.suggestion_id).where(SuggestionRow.ticket_id == ticket_id)
        cancelled = await self._session.scalars(
            update(SuggestionPartRow)
            .where(
                SuggestionPartRow.suggestion_id.in_(of_ticket),
                SuggestionPartRow.status == _PENDING,
            )
            .values(status=PartStatus.CANCELLED.value, completed_at=completed_at)
            .returning(SuggestionPartRow.suggestion_id)
        )
        cancelled_ids = sorted({str(suggestion_id) for suggestion_id in cancelled})
        await self._session.execute(
            update(SuggestionJobRow)
            .where(
                SuggestionJobRow.suggestion_id.in_(of_ticket),
                SuggestionJobRow.state != JobState.DONE.value,
            )
            .values(state=JobState.DONE.value, updated_at=completed_at)
        )
        return tuple(SuggestionId(suggestion_id) for suggestion_id in cancelled_ids)

    async def insert_suggestion(self, suggestion: NewSuggestion) -> None:
        """Insert a suggestion, its two pending parts, and its queued job.

        Args:
            suggestion: The suggestion.
        """
        suggestion_id = UUID(suggestion.suggestion_id)
        self._session.add(
            SuggestionRow(
                suggestion_id=suggestion_id,
                ticket_id=suggestion.ticket_id,
                trigger=suggestion.trigger.value,
                intent_override=_optional_value(suggestion.intent_override),
                requested_by_account_id=_optional_uuid(suggestion.requested_by),
                created_at=suggestion.created_at,
                trace_id=suggestion.trace_id,
                request=None,
            )
        )
        await self._session.flush()
        self._session.add_all(
            [
                SuggestionPartRow(
                    suggestion_id=suggestion_id,
                    part=part.value,
                    status=_PENDING,
                    reason_codes=[],
                )
                for part in SuggestionPart
            ]
        )
        self._session.add(
            SuggestionJobRow(
                suggestion_id=suggestion_id,
                state=JobState.QUEUED.value,
                attempt_number=0,
                lease_expires_at=None,
                created_at=suggestion.created_at,
                updated_at=suggestion.created_at,
            )
        )
        await self._session.flush()

    async def load_suggestion(self, suggestion_id: SuggestionId) -> Suggestion | None:
        """Load one suggestion with both parts.

        Args:
            suggestion_id: The suggestion.

        Returns:
            The suggestion, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored part breaks an invariant, a stored text is no value
                of its enum, or a stored result no longer matches the contract: a defect.
        """
        suggestions = await self.load_suggestions(frozenset({suggestion_id}))
        return suggestions.get(suggestion_id)

    async def load_progress(self, suggestion_id: SuggestionId) -> SuggestionProgress | None:
        """Load the part statuses of one suggestion, and nothing else.

        Args:
            suggestion_id: The suggestion.

        Returns:
            The statuses, or None when the suggestion is unknown. Both parts are inserted
            together and never deleted.

        Raises:
            UnexpectedFailureError: A stored status is no value of `PartStatus`: a defect.
        """
        rows = (
            await self._session.execute(
                select(SuggestionPartRow.part, SuggestionPartRow.status).where(
                    SuggestionPartRow.suggestion_id == UUID(suggestion_id)
                )
            )
        ).all()
        status_of_part = {row.part: parse_stored_enum(PartStatus, row.status) for row in rows}
        if not status_of_part:
            return None
        return SuggestionProgress(
            suggestion_id,
            status_of_part[SuggestionPart.ANALYSIS.value],
            status_of_part[SuggestionPart.DRAFT.value],
        )

    async def load_suggestions(
        self, suggestion_ids: frozenset[SuggestionId]
    ) -> Mapping[SuggestionId, Suggestion]:
        """Load several suggestions in two queries.

        Args:
            suggestion_ids: The suggestions.

        Returns:
            Each known suggestion by its ID.

        Raises:
            UnexpectedFailureError: A stored part breaks an invariant, a stored text is no value
                of its enum, or a stored result no longer matches the contract: a defect.
        """
        if not suggestion_ids:
            return {}
        keys = [UUID(suggestion_id) for suggestion_id in suggestion_ids]
        rows = (
            await self._session.scalars(
                select(SuggestionRow).where(SuggestionRow.suggestion_id.in_(keys))
            )
        ).all()
        parts = (
            await self._session.scalars(
                select(SuggestionPartRow).where(SuggestionPartRow.suggestion_id.in_(keys))
            )
        ).all()
        part_by_key = {(part.suggestion_id, part.part): part for part in parts}
        try:
            return {
                SuggestionId(str(row.suggestion_id)): _to_suggestion(row, part_by_key)
                for row in rows
            }
        except AiServiceContractError as error:
            # Backend stored only values that matched the contract, so one that no longer parses
            # is a defect of backend, not a failure of ai-service: `500`, logged once (ERR-05).
            raise UnexpectedFailureError from error


class PostgresSuggestionJobStore:
    """Implement the `SuggestionJobStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the claim or of one result.
        """
        self._session = session

    async def claim_next(self, now: datetime, lease_expires_at: datetime) -> ClaimedJob | None:
        """Claim the oldest claimable job in one statement, with `FOR UPDATE SKIP LOCKED`.

        Args:
            now: The current time.
            lease_expires_at: When the new lease expires.

        Returns:
            The claimed job, or None when nothing is claimable.
        """
        claimed = (
            await self._session.execute(
                update(SuggestionJobRow)
                .where(SuggestionJobRow.suggestion_id == _oldest_claimable_job(now))
                .values(
                    state=JobState.RUNNING.value,
                    attempt_number=SuggestionJobRow.attempt_number + 1,
                    lease_expires_at=lease_expires_at,
                    updated_at=now,
                )
                .returning(SuggestionJobRow.suggestion_id, SuggestionJobRow.attempt_number)
            )
        ).one_or_none()
        if claimed is None:
            return None
        ticket_id = await self._session.scalar(
            select(SuggestionRow.ticket_id).where(
                SuggestionRow.suggestion_id == claimed.suggestion_id
            )
        )
        return ClaimedJob(
            SuggestionId(str(claimed.suggestion_id)),
            SuggestionTicketId(str(ticket_id)),
            claimed.attempt_number,
        )

    async def lock_job(self, suggestion_id: SuggestionId) -> LockedJob | None:
        """Lock a job row for the rest of the transaction.

        Args:
            suggestion_id: The suggestion of the job.

        Returns:
            The job, or None when it is unknown.

        Raises:
            UnexpectedFailureError: The stored state is no value of `JobState`: a defect.
        """
        row = (
            await self._session.execute(
                select(SuggestionJobRow.state, SuggestionJobRow.attempt_number)
                .where(SuggestionJobRow.suggestion_id == UUID(suggestion_id))
                .with_for_update()
            )
        ).one_or_none()
        if row is None:
            return None
        return LockedJob(parse_stored_enum(JobState, row.state), row.attempt_number)

    async def save_request(self, suggestion_id: SuggestionId, request: SuggestionRequest) -> None:
        """Write the request of a suggestion when it is still absent.

        Args:
            suggestion_id: The suggestion.
            request: The request.
        """
        body: object = json.loads(to_request_body(request))
        await self._session.execute(
            update(SuggestionRow)
            .where(
                SuggestionRow.suggestion_id == UUID(suggestion_id),
                SuggestionRow.request.is_(None),
            )
            .values(request=body)
        )

    async def complete_part(self, suggestion_id: SuggestionId, completion: PartCompletion) -> bool:
        """Write the final state of a part that is still `pending`.

        Args:
            suggestion_id: The suggestion.
            completion: What to write.

        Returns:
            True when the part was pending and is now final.
        """
        usage = completion.llm_usage
        versions = completion.versions
        written = await self._session.scalars(
            update(SuggestionPartRow)
            .where(
                SuggestionPartRow.suggestion_id == UUID(suggestion_id),
                SuggestionPartRow.part == completion.part.value,
                SuggestionPartRow.status == _PENDING,
            )
            .values(
                status=completion.status.value,
                reason_codes=[code.value for code in completion.reason_codes],
                release_id=None if versions is None else versions.release_id,
                versions=None if versions is None else asdict(versions),
                latency_ms=completion.latency_ms,
                llm_input_token_count=None if usage is None else usage.input_token_count,
                llm_output_token_count=None if usage is None else usage.output_token_count,
                llm_cost_micro_usd=None if usage is None else usage.cost_micro_usd,
                mask_count_by_type=(
                    None if completion.mask_counts is None else asdict(completion.mask_counts)
                ),
                completed_at=completion.completed_at,
                result=None
                if completion.result_body is None
                else json.loads(completion.result_body),
            )
            .returning(SuggestionPartRow.part)
        )
        return written.first() is not None

    async def finish_job(self, suggestion_id: SuggestionId, now: datetime) -> None:
        """Set a job `done`.

        Args:
            suggestion_id: The suggestion of the job.
            now: The current time.
        """
        await self._session.execute(
            update(SuggestionJobRow)
            .where(SuggestionJobRow.suggestion_id == UUID(suggestion_id))
            .values(state=JobState.DONE.value, updated_at=now)
        )


def _to_suggestion(
    row: SuggestionRow, part_by_key: Mapping[tuple[UUID, str], SuggestionPartRow]
) -> Suggestion:
    analysis = part_by_key[(row.suggestion_id, SuggestionPart.ANALYSIS.value)]
    draft = part_by_key[(row.suggestion_id, SuggestionPart.DRAFT.value)]
    return Suggestion(
        suggestion_id=SuggestionId(str(row.suggestion_id)),
        ticket_id=SuggestionTicketId(row.ticket_id),
        trigger=parse_stored_enum(SuggestionTrigger, row.trigger),
        intent_override=parse_optional_stored_enum(IntentLabel, row.intent_override),
        requested_by=(
            None
            if row.requested_by_account_id is None
            else AccountId(str(row.requested_by_account_id))
        ),
        created_at=row.created_at,
        trace_id=TraceId(row.trace_id),
        analysis=_to_analysis_state(analysis),
        draft=_to_draft_state(draft),
        sent_order_context=None if row.request is None else parse_stored_order_context(row.request),
    )


def _to_analysis_state(row: SuggestionPartRow) -> AnalysisState:
    common = _to_common_state(row)
    if common is not None:
        return common
    if parse_stored_enum(PartStatus, row.status) is not PartStatus.READY:
        raise UnexpectedFailureError
    return parse_stored_analysis(row.result)


def _to_draft_state(row: SuggestionPartRow) -> DraftState:
    common = _to_common_state(row)
    if common is not None:
        return common
    if parse_stored_enum(PartStatus, row.status) is PartStatus.READY:
        raise UnexpectedFailureError
    return parse_stored_draft_outcome(row.result)


def _to_common_state(
    row: SuggestionPartRow,
) -> PendingPart | CancelledPart | UnavailablePart | None:
    # The states without a result; the check constraint of `r0003` allows no other status.
    status = parse_stored_enum(PartStatus, row.status)
    if status is PartStatus.PENDING:
        return PendingPart()
    if status is PartStatus.CANCELLED:
        return CancelledPart()
    if status is PartStatus.UNAVAILABLE:
        return UnavailablePart(parse_stored_enum(AiReasonCode, row.reason_codes[0]))
    return None


def _optional_value(label: IntentLabel | None) -> str | None:
    return None if label is None else label.value


def _optional_uuid(account_id: AccountId | None) -> UUID | None:
    return None if account_id is None else UUID(account_id)


def _oldest_claimable_job(now: datetime) -> ScalarSelect[UUID]:
    # The oldest job that is queued, or running with an expired lease; a job that another
    # claim holds is skipped instead of waited for (ADR-0011, Suggestion job queue, item 2).
    candidate = aliased(SuggestionJobRow)
    return (
        select(candidate.suggestion_id)
        .where(
            or_(
                candidate.state == JobState.QUEUED.value,
                and_(
                    candidate.state == JobState.RUNNING.value,
                    candidate.lease_expires_at <= now,
                ),
            )
        )
        .order_by(candidate.created_at, candidate.suggestion_id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )

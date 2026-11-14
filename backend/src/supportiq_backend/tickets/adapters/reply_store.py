"""The reply port of tickets on `replies` and `staff_decisions` (ERR-16, ADR-0006).

A ticket has one reply: the unique `ticket_id` of `replies` refuses a second one. This is the
only statement that inserts a reply, and only `SendReply` calls it (FR-04).
"""

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts import AccountId
from supportiq_backend.tickets.adapters.identifiers import (
    to_optional_suggestion_id,
    to_optional_uuid,
)
from supportiq_backend.tickets.adapters.tables import ReplyRow, StaffDecisionRow
from supportiq_backend.tickets.domain import (
    ProposalId,
    RecordedDecision,
    ReplyBasis,
    ReplyId,
    SentReply,
    StaffReasonCode,
    TicketId,
)


class PostgresReplyStore:
    """Implement the `ReplyStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def insert_reply(self, reply: SentReply) -> None:
        """Insert the one reply of a ticket; the unique `ticket_id` refuses a second one.

        Args:
            reply: The reply.
        """
        await self._session.execute(
            insert(ReplyRow).values(
                reply_id=reply.reply_id,
                ticket_id=reply.ticket_id,
                basis=reply.basis.value,
                suggestion_id=to_optional_uuid(reply.suggestion_id),
                proposal_id=reply.proposal_id,
                acknowledged_warning_ids=list(reply.acknowledged_warning_ids),
                staff_reason_codes=[code.value for code in reply.staff_reason_codes],
                sent_by_account_id=UUID(reply.sent_by),
                sent_at=reply.sent_at,
                body=reply.body,
                note=reply.note,
            )
        )

    async def load_reply(self, ticket_id: TicketId) -> SentReply | None:
        """Load the reply of a ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The reply, or None before it is sent.
        """
        row = await self._session.scalar(select(ReplyRow).where(ReplyRow.ticket_id == ticket_id))
        if row is None:
            return None
        return SentReply(
            reply_id=ReplyId(row.reply_id),
            ticket_id=TicketId(row.ticket_id),
            basis=ReplyBasis(row.basis),
            body=row.body,
            suggestion_id=to_optional_suggestion_id(row.suggestion_id),
            proposal_id=None if row.proposal_id is None else ProposalId(row.proposal_id),
            acknowledged_warning_ids=tuple(row.acknowledged_warning_ids),
            staff_reason_codes=tuple(StaffReasonCode(code) for code in row.staff_reason_codes),
            note=row.note,
            sent_by=AccountId(str(row.sent_by_account_id)),
            sent_at=row.sent_at,
        )

    async def insert_decision(self, decision: RecordedDecision) -> None:
        """Insert a staff decision; it holds no text (ADR-0006).

        Args:
            decision: The decision.
        """
        staff_decision = decision.decision
        await self._session.execute(
            insert(StaffDecisionRow).values(
                decision_id=decision.decision_id,
                ticket_id=decision.ticket_id,
                suggestion_id=to_optional_uuid(staff_decision.suggestion_id),
                decision_type=staff_decision.decision_type.value,
                staff_reason_codes=[code.value for code in staff_decision.staff_reason_codes],
                change_ratio=staff_decision.change_ratio,
                final_intent=(
                    None
                    if staff_decision.final_intent is None
                    else staff_decision.final_intent.value
                ),
                decided_by_account_id=UUID(decision.decided_by),
                proposed_by_account_id=to_optional_uuid(decision.proposed_by),
                is_proposal_changed=decision.is_proposal_changed,
                decided_at=decision.decided_at,
            )
        )

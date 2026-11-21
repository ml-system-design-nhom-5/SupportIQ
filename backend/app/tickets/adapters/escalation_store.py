"""The escalation port of tickets on `escalations` (contracts v1 design).

A ticket has at most one escalation: the unique `ticket_id` of `escalations` refuses a second
one, and the state machine moves a ticket from `open` to `escalated` once.
"""

from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import AccountId
from app.platform.persistence import parse_stored_enum
from app.tickets.adapters.identifiers import (
    to_optional_suggestion_id,
    to_optional_uuid,
)
from app.tickets.adapters.tables import EscalationRow
from app.tickets.domain import (
    Escalation,
    EscalationId,
    EscalationRequest,
    StaffReasonCode,
    TicketId,
)


class PostgresEscalationStore:
    """Implement the `EscalationStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def insert_escalation(self, escalation: Escalation) -> None:
        """Insert the one escalation of a ticket; the unique `ticket_id` refuses a second one.

        Args:
            escalation: The escalation.
        """
        request = escalation.request
        await self._session.execute(
            insert(EscalationRow).values(
                escalation_id=escalation.escalation_id,
                ticket_id=escalation.ticket_id,
                suggestion_id=to_optional_uuid(request.suggestion_id),
                staff_reason_codes=[code.value for code in request.staff_reason_codes],
                escalated_by_account_id=UUID(escalation.escalated_by),
                escalated_at=escalation.escalated_at,
                note=request.note,
            )
        )

    async def load_escalation(self, ticket_id: TicketId) -> Escalation | None:
        """Load the escalation of a ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The escalation, or None before staff escalate.

        Raises:
            UnexpectedFailureError: A stored reason code is no value of its enum: a defect.
        """
        row = await self._session.scalar(
            select(EscalationRow).where(EscalationRow.ticket_id == ticket_id)
        )
        if row is None:
            return None
        return Escalation(
            escalation_id=EscalationId(row.escalation_id),
            ticket_id=TicketId(row.ticket_id),
            request=EscalationRequest(
                staff_reason_codes=tuple(
                    parse_stored_enum(StaffReasonCode, code) for code in row.staff_reason_codes
                ),
                note=row.note,
                suggestion_id=to_optional_suggestion_id(row.suggestion_id),
            ),
            escalated_by=AccountId(str(row.escalated_by_account_id)),
            escalated_at=row.escalated_at,
        )

"""The ticket state port of tickets on `tickets`: the handling clock, the queue, and closing.

Each write changes a ticket row that the action's transaction locked first, and a trigger
keeps every status change to the state machine (backend ticket workflow design, Ticket state
machine and check order).
"""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.tickets.adapters.tables import TicketRow
from app.tickets.domain import ManagerQueue, TicketId, TicketStatus


class PostgresTicketStateStore:
    """Implement the `TicketStateStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def start_handling(self, ticket_id: TicketId, started_at: datetime) -> None:
        """Set `handling_started_at`, which starts the handling clock (NFR-11).

        Args:
            ticket_id: The ticket, locked, whose clock has not started.
            started_at: The time of the first view.
        """
        await self._session.execute(
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id, TicketRow.handling_started_at.is_(None))
            .values(handling_started_at=started_at)
        )

    async def move_to_manager_queue(self, ticket_id: TicketId, queue: ManagerQueue) -> None:
        """Move an `open` ticket to a manager's queue; a trigger keeps to the state machine.

        Args:
            ticket_id: The ticket, locked and `open`.
            queue: `awaiting_approval` or `escalated`.
        """
        await self._session.execute(
            update(TicketRow).where(TicketRow.ticket_id == ticket_id).values(status=queue.value)
        )

    async def close_ticket(self, ticket_id: TicketId, closed_at: datetime) -> None:
        """Set the ticket `closed`, when its reply is sent.

        Args:
            ticket_id: The ticket, locked.
            closed_at: When the reply was sent.
        """
        await self._session.execute(
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(status=TicketStatus.CLOSED.value, closed_at=closed_at)
        )

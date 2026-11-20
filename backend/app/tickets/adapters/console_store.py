"""The console ports of tickets on `tickets` and `customer_messages`, and its links for suggestions.

Every action locks the ticket row first with `SELECT ... FOR UPDATE`, so two actions on one
ticket run one after the other, whatever replica answers (backend ticket workflow design).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, Select, and_, collate, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import CustomerId
from app.commerce import OrderId
from app.platform import is_storable_text
from app.platform.persistence import BYTE_ORDER_COLLATION, parse_stored_enum
from app.suggestions import (
    SuggestionId,
    SuggestionTicketId,
    TicketForSuggestion,
    TicketMessage,
)
from app.tickets.adapters.identifiers import to_optional_suggestion_id
from app.tickets.adapters.tables import CustomerMessageRow, TicketRow
from app.tickets.domain import (
    ConsoleTicket,
    ConsoleTicketPosition,
    HandlingMode,
    TicketId,
    TicketStatus,
)

type _ConsoleColumns = tuple[
    str,
    str,
    str,
    bool,
    datetime,
    datetime | None,
    datetime | None,
    UUID,
    str | None,
    UUID | None,
    str,
]


class PostgresConsoleTicketStore:
    """Implement the `ConsoleTicketStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def lock_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Lock a ticket row with `SELECT ... FOR UPDATE` and load it with its message.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        if not is_storable_text(ticket_id):
            return None
        statement = (
            _select_console_tickets()
            .where(TicketRow.ticket_id == ticket_id)
            .with_for_update(of=TicketRow)
        )
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else _to_console_ticket(row)

    async def load_console_ticket(self, ticket_id: TicketId) -> ConsoleTicket | None:
        """Load a ticket with its message, without a lock.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        if not is_storable_text(ticket_id):
            return None
        statement = _select_console_tickets().where(TicketRow.ticket_id == ticket_id)
        row = (await self._session.execute(statement)).one_or_none()
        return None if row is None else _to_console_ticket(row)

    async def load_console_tickets(
        self, status: TicketStatus, *, after: ConsoleTicketPosition | None, limit: int
    ) -> tuple[ConsoleTicket, ...]:
        """Load the tickets in one status, in the order of their queue.

        Args:
            status: The queue.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The tickets.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        ticket_order = collate(TicketRow.ticket_id, BYTE_ORDER_COLLATION)
        statement = _select_console_tickets().where(TicketRow.status == status.value)
        if status is TicketStatus.CLOSED:
            moment = TicketRow.closed_at
            ordered = statement.order_by(moment.desc(), ticket_order)
            if after is not None:
                ordered = ordered.where(
                    or_(
                        moment < after.moment,
                        and_(moment == after.moment, ticket_order > after.ticket_id),
                    )
                )
        else:
            moment = TicketRow.created_at
            ordered = statement.order_by(moment, ticket_order)
            if after is not None:
                ordered = ordered.where(
                    or_(
                        moment > after.moment,
                        and_(moment == after.moment, ticket_order > after.ticket_id),
                    )
                )
        rows = await self._session.execute(ordered.limit(limit))
        return tuple(_to_console_ticket(row) for row in rows)


class PostgresTicketLinks:
    """Implement the `SuggestionTickets` and `TicketAuthority` ports of suggestions."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the links to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def lock_ticket(self, ticket_id: SuggestionTicketId) -> TicketForSuggestion | None:
        """Lock a ticket row for the rest of the transaction.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        return await self._read_ticket(ticket_id, is_locked=True)

    async def read_ticket(self, ticket_id: SuggestionTicketId) -> TicketForSuggestion | None:
        """Read a ticket row without a lock, for the re-reads of a stream.

        Args:
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown.

        Raises:
            UnexpectedFailureError: A stored text is no value of its enum: a defect.
        """
        return await self._read_ticket(ticket_id, is_locked=False)

    async def _read_ticket(
        self, ticket_id: SuggestionTicketId, *, is_locked: bool
    ) -> TicketForSuggestion | None:
        if not is_storable_text(ticket_id):
            return None
        query = select(
            TicketRow.current_suggestion_id, TicketRow.status, TicketRow.handling_mode
        ).where(TicketRow.ticket_id == ticket_id)
        row = (
            await self._session.execute(query.with_for_update() if is_locked else query)
        ).one_or_none()
        if row is None:
            return None
        return TicketForSuggestion(
            current_suggestion_id=to_optional_suggestion_id(row.current_suggestion_id),
            is_open=parse_stored_enum(TicketStatus, row.status) is TicketStatus.OPEN,
            is_assisted=parse_stored_enum(HandlingMode, row.handling_mode) is HandlingMode.ASSISTED,
            status_name=row.status,
        )

    async def set_current_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Make a suggestion the ticket's current one.

        Args:
            ticket_id: The ticket, locked by the transaction.
            suggestion_id: The new suggestion.
        """
        await self._session.execute(
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(current_suggestion_id=UUID(suggestion_id))
        )

    async def load_ticket_message(self, ticket_id: SuggestionTicketId) -> TicketMessage | None:
        """Load what a job needs of its ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The message and its context, or None when the ticket is unknown.
        """
        row = (
            await self._session.execute(
                select(
                    CustomerMessageRow.body,
                    TicketRow.created_at,
                    TicketRow.customer_id,
                    TicketRow.order_id,
                )
                .join(CustomerMessageRow, CustomerMessageRow.ticket_id == TicketRow.ticket_id)
                .where(TicketRow.ticket_id == ticket_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return TicketMessage(
            ticket_id=ticket_id,
            message=row.body,
            created_at=row.created_at,
            customer_id=CustomerId(str(row.customer_id)),
            order_id=None if row.order_id is None else OrderId(row.order_id),
        )

    async def set_authority_required(self, ticket_id: SuggestionTicketId) -> None:
        """Set `is_authority_required`; a trigger keeps it from going back to false.

        Args:
            ticket_id: The ticket, locked by the transaction.
        """
        await self._session.execute(
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id, TicketRow.is_authority_required.is_(False))
            .values(is_authority_required=True)
        )


def _select_console_tickets() -> Select[_ConsoleColumns]:
    return select(
        TicketRow.ticket_id,
        TicketRow.status,
        TicketRow.handling_mode,
        TicketRow.is_authority_required,
        TicketRow.created_at,
        TicketRow.handling_started_at,
        TicketRow.closed_at,
        TicketRow.customer_id,
        TicketRow.order_id,
        TicketRow.current_suggestion_id,
        CustomerMessageRow.body,
    ).join(CustomerMessageRow, CustomerMessageRow.ticket_id == TicketRow.ticket_id)


def _to_console_ticket(row: Row[_ConsoleColumns]) -> ConsoleTicket:
    return ConsoleTicket(
        ticket_id=TicketId(row.ticket_id),
        status=parse_stored_enum(TicketStatus, row.status),
        handling_mode=parse_stored_enum(HandlingMode, row.handling_mode),
        is_authority_required=row.is_authority_required,
        created_at=row.created_at,
        handling_started_at=row.handling_started_at,
        closed_at=row.closed_at,
        customer_id=CustomerId(str(row.customer_id)),
        order_id=None if row.order_id is None else OrderId(row.order_id),
        current_suggestion_id=to_optional_suggestion_id(row.current_suggestion_id),
        message=row.body,
    )

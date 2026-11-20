"""The `TicketStore` port on the `tickets` and `customer_messages` tables."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, Select, and_, collate, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import CustomerId
from app.commerce import OrderId
from app.platform import is_storable_text
from app.platform.persistence import BYTE_ORDER_COLLATION
from app.tickets.adapters.tables import CustomerMessageRow, ReplyRow, TicketRow
from app.tickets.domain import (
    ShopReply,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPosition,
    TicketSource,
    TicketStatus,
)

type _ShopTicketColumns = tuple[str, str | None, str, datetime]


class PostgresTicketStore:
    """The tickets of the shop, in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Keep the session.

        Args:
            session: The session of the transaction.
        """
        self._session = session

    async def insert_shop_ticket(self, record: ShopTicketRecord) -> TicketId:
        """Insert an `open` ticket from the shop and its customer message.

        Args:
            record: What the ticket holds.

        Returns:
            The identifier that the database gave the ticket.
        """
        result = await self._session.execute(
            insert(TicketRow)
            .values(
                customer_id=UUID(record.customer_id),
                order_id=record.ticket.order_id,
                status=TicketStatus.OPEN.value,
                handling_mode=record.handling_mode.value,
                source=TicketSource.SHOP.value,
                created_at=record.created_at,
            )
            .returning(TicketRow.ticket_id)
        )
        ticket_id = result.scalar_one()
        await self._session.execute(
            insert(CustomerMessageRow).values(
                message_id=record.message_id,
                ticket_id=ticket_id,
                body=record.ticket.message,
                created_at=record.created_at,
            )
        )
        return TicketId(ticket_id)

    async def load_shop_ticket(
        self, customer_id: CustomerId, ticket_id: TicketId
    ) -> ShopTicket | None:
        """Load one ticket that the customer created through the shop.

        Args:
            customer_id: The customer.
            ticket_id: The ticket, as a request sent it.

        Returns:
            The ticket, or None when it is unknown, imported, or another customer's.
        """
        if not is_storable_text(ticket_id):
            return None
        result = await self._session.execute(
            _select_shop_tickets(customer_id).where(TicketRow.ticket_id == ticket_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return _to_shop_ticket(row, await self._load_replies((row.ticket_id,)))

    async def load_shop_tickets(
        self,
        customer_id: CustomerId,
        *,
        order_id: OrderId | None,
        after: TicketPosition | None,
        limit: int,
    ) -> tuple[ShopTicket, ...]:
        """Load the customer's shop tickets, newest first, then by ticket ID by code point.

        Args:
            customer_id: The customer.
            order_id: Only the tickets about this order, or None for every ticket.
            after: The last ticket of the previous page, or None for the first page.
            limit: The maximum number of tickets.

        Returns:
            The tickets.
        """
        ticket_order = collate(TicketRow.ticket_id, BYTE_ORDER_COLLATION)
        statement = _select_shop_tickets(customer_id)
        if order_id is not None:
            statement = statement.where(TicketRow.order_id == order_id)
        if after is not None:
            statement = statement.where(
                or_(
                    TicketRow.created_at < after.created_at,
                    and_(TicketRow.created_at == after.created_at, ticket_order > after.ticket_id),
                )
            )
        rows = (
            await self._session.execute(
                statement.order_by(TicketRow.created_at.desc(), ticket_order).limit(limit)
            )
        ).all()
        replies = await self._load_replies(tuple(row.ticket_id for row in rows))
        return tuple(_to_shop_ticket(row, replies) for row in rows)

    async def _load_replies(self, ticket_ids: tuple[str, ...]) -> Mapping[str, ShopReply]:
        if not ticket_ids:
            return {}
        rows = await self._session.execute(
            select(ReplyRow.ticket_id, ReplyRow.body, ReplyRow.sent_at).where(
                ReplyRow.ticket_id.in_(ticket_ids)
            )
        )
        return {row.ticket_id: ShopReply(row.body, row.sent_at) for row in rows}


def _select_shop_tickets(customer_id: CustomerId) -> Select[_ShopTicketColumns]:
    # Every read of the shop starts here, so no query can forget the owner or the source.
    return (
        select(
            TicketRow.ticket_id,
            TicketRow.order_id,
            CustomerMessageRow.body,
            TicketRow.created_at,
        )
        .join(CustomerMessageRow, CustomerMessageRow.ticket_id == TicketRow.ticket_id)
        .where(
            TicketRow.customer_id == UUID(customer_id),
            TicketRow.source == TicketSource.SHOP.value,
        )
    )


def _to_shop_ticket(
    row: Row[_ShopTicketColumns], reply_by_ticket: Mapping[str, ShopReply]
) -> ShopTicket:
    # The constraint `tickets_shop_tickets_have_an_order` gives every shop ticket an order.
    return ShopTicket(
        TicketId(row.ticket_id),
        OrderId(row.order_id),
        row.body,
        row.created_at,
        reply_by_ticket.get(row.ticket_id),
    )

"""The port of the tickets tables (ARCH-13)."""

from typing import Protocol

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.tickets.domain.tickets import (
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPosition,
)


class TicketStore(Protocol):
    """Writes shop tickets and reads them back, always for one customer (SEC-17)."""

    async def insert_shop_ticket(self, record: ShopTicketRecord) -> TicketId:
        """Insert an `open` ticket from the shop and its customer message.

        Args:
            record: What the ticket holds.

        Returns:
            The identifier that the database gave the ticket.
        """
        ...

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
        ...

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
        ...

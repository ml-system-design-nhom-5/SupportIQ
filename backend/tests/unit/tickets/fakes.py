"""In-memory fake of the `TicketStore` port (ARCH-27)."""

from dataclasses import dataclass, field

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import BackendError
from supportiq_backend.tickets import ShopTicket, ShopTicketRecord, TicketId, TicketPosition

FIRST_TICKET_ID = TicketId("TCK-1001")


@dataclass(slots=True)
class FakeTicketStore:
    """Keep inserted records, and serve given tickets in the contract's order."""

    tickets: dict[CustomerId, tuple[ShopTicket, ...]] = field(
        default_factory=dict[CustomerId, tuple[ShopTicket, ...]]
    )
    inserted: list[ShopTicketRecord] = field(default_factory=list[ShopTicketRecord])
    insert_failure: BackendError | None = None
    load_failure: BackendError | None = None

    async def insert_shop_ticket(self, record: ShopTicketRecord) -> TicketId:
        """Keep the record and return the same ID each time, or raise the chosen failure."""
        if self.insert_failure is not None:
            raise self.insert_failure
        self.inserted.append(record)
        return FIRST_TICKET_ID

    async def load_shop_ticket(
        self, customer_id: CustomerId, ticket_id: TicketId
    ) -> ShopTicket | None:
        """Return the ticket of the customer, if any."""
        if self.load_failure is not None:
            raise self.load_failure
        tickets = self.tickets.get(customer_id, ())
        return next((ticket for ticket in tickets if ticket.ticket_id == ticket_id), None)

    async def load_shop_tickets(
        self,
        customer_id: CustomerId,
        *,
        order_id: OrderId | None,
        after: TicketPosition | None,
        limit: int,
    ) -> tuple[ShopTicket, ...]:
        """Return the tickets after the position, about the order when one is given."""
        if self.load_failure is not None:
            raise self.load_failure
        tickets = tuple(
            ticket
            for ticket in self.tickets.get(customer_id, ())
            if order_id is None or ticket.order_id == order_id
        )
        position = 0
        if after is not None:
            position = 1 + [ticket.ticket_id for ticket in tickets].index(after.ticket_id)
        return tickets[position : position + limit]

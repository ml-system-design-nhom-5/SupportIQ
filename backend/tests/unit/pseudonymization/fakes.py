"""In-memory fakes of the pseudonym map and of the customer records (ARCH-27)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import (
    AddressedOrder,
    CustomerContact,
    OrderId,
    OrderReferences,
)
from supportiq_backend.platform import BackendError
from supportiq_backend.pseudonymization.domain import MapTicketId, PseudonymEntry

CUSTOMER_ID = CustomerId("00000000-0000-4000-8000-0000000000c1")
CONTACT = CustomerContact("Lan Tran", "lan.tran@example.test", "+84 90 111 0001")
REFERENCES = OrderReferences(
    order_id=OrderId("ORD-20901"),
    tracking_code="TRK-0000020901",
    transaction_id="TXN-00020901",
    shipping_address="12 Example Street, Ba Dinh, Hanoi",
)


@dataclass(slots=True)
class FakePseudonymMapStore:
    """Keep the maps of tickets; an insert keeps rows that already exist."""

    entries_by_ticket: dict[MapTicketId, dict[str, PseudonymEntry]] = field(
        default_factory=dict[MapTicketId, dict[str, PseudonymEntry]]
    )
    insert_failure: BackendError | None = None

    async def insert_missing(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the entries that the map does not hold, or raise the chosen failure."""
        del created_at
        if self.insert_failure is not None:
            raise self.insert_failure
        stored = self.entries_by_ticket.setdefault(ticket_id, {})
        for entry in entries:
            stored.setdefault(entry.pseudonym, entry)

    async def load_entries(self, ticket_id: MapTicketId) -> tuple[PseudonymEntry, ...]:
        """Return the map of the ticket, ordered by pseudonym."""
        stored = self.entries_by_ticket.get(ticket_id, {})
        return tuple(stored[pseudonym] for pseudonym in sorted(stored))


@dataclass(slots=True)
class FakeCustomerRecords:
    """Answer with one customer and one order."""

    contact: CustomerContact | None = CONTACT
    references: OrderReferences | None = REFERENCES
    orders: tuple[AddressedOrder, ...] = ()
    names: Mapping[CustomerId, str] = field(
        default_factory=lambda: {CUSTOMER_ID: CONTACT.display_name}
    )

    async def load_contact(self, customer_id: CustomerId) -> CustomerContact | None:
        """Return the contact of the one customer."""
        return self.contact if customer_id == CUSTOMER_ID else None

    async def load_order_references(
        self, customer_id: CustomerId, order_id: OrderId
    ) -> OrderReferences | None:
        """Return the references of the one order."""
        if customer_id != CUSTOMER_ID or self.references is None:
            return None
        return self.references if order_id == self.references.order_id else None

    async def load_display_names(
        self, customer_ids: frozenset[CustomerId]
    ) -> Mapping[CustomerId, str]:
        """Return the names of the known customers."""
        return {key: name for key, name in self.names.items() if key in customer_ids}

    async def load_addressed_orders(self, customer_id: CustomerId) -> tuple[AddressedOrder, ...]:
        """Return the orders of the one customer."""
        return self.orders if customer_id == CUSTOMER_ID else ()

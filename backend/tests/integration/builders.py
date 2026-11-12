"""Builders of integration test data, inserted as the owner with sensible defaults (TEST-05).

`supportiq_app` cannot insert admin accounts, customer accounts, or commerce data, so the
builders connect as the owner.
IDs and times come from a counter, so a test run is deterministic (TEST-14). A test overrides
only the fields that matter to it. Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import count
from uuid import UUID

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import Executable

from supportiq_backend.accounts import SessionToken, hash_session_token
from supportiq_backend.accounts.adapters.tables import AccountRow, SessionRow
from supportiq_backend.commerce.adapters.tables import (
    CustomerRow,
    OrderLineRow,
    OrderRow,
    ProductRow,
    RefundRow,
    ShipmentRow,
)
from supportiq_backend.tickets.adapters.tables import CustomerMessageRow, TicketRow
from tests.unit.platform.fakes import FAKE_CLOCK_START

# Not a real Argon2id hash: rows built with it cannot sign in. Sign-in tests set their own.
UNUSABLE_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$not-a-real-salt$not-a-real-hash"
CURRENCY = "USD"


@dataclass(frozen=True, slots=True)
class LineSpec:
    """One order line to build.

    Attributes:
        product_id: The catalog product.
        quantity: The number of units.
    """

    product_id: str
    quantity: int = 1


@dataclass(frozen=True, slots=True)
class ShipmentSpec:
    """The shipment of an order to build.

    Attributes:
        shipment_status: The status.
        estimated_delivery_at: The estimate, if any.
        delivered_at: The delivery time; set exactly when the status is `delivered`.
    """

    shipment_status: str = "in_transit"
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RefundSpec:
    """The refund of an order to build.

    Attributes:
        refund_status: The status.
        refund_amount_minor: The amount in minor units.
    """

    refund_status: str = "requested"
    refund_amount_minor: int = 1_000


@dataclass(frozen=True, slots=True)
class AccountSpec:
    """An account to build.

    Attributes:
        role: The role.
        is_active: Whether the account can sign in.
        customer_id: The customer of a customer account.
        display_name: The display name; a name from the role and a number when None.
        password_hash: The Argon2id hash; unusable by default.
        login_name: The login name; the role and a number when None.
    """

    role: str
    is_active: bool = True
    customer_id: UUID | None = None
    display_name: str | None = None
    password_hash: str = UNUSABLE_PASSWORD_HASH
    login_name: str | None = None


@dataclass(frozen=True, slots=True)
class OrderSpec:
    """An order to build.

    Attributes:
        lines: Its lines, at least one.
        order_status: The status.
        placed_at: When it was placed; the next time of the builder when None.
        shipment: Its shipment record, or None for an order without one.
        refund: Its refund, or None.
    """

    lines: tuple[LineSpec, ...]
    order_status: str = "shipped"
    placed_at: datetime | None = None
    shipment: ShipmentSpec | None = None
    refund: RefundSpec | None = None


@dataclass(frozen=True, slots=True)
class TicketSpec:
    """A ticket to build, with its customer message.

    Attributes:
        message: The customer message.
        status: The ticket state.
        source: `shop` or `import`.
        is_authority_required: The authority flag.
        created_at: When it was created; the next time of the builder when None.
    """

    message: str = "Where is my parcel?"
    status: str = "open"
    source: str = "shop"
    is_authority_required: bool = False
    created_at: datetime | None = None


class DatabaseBuilder:
    """Insert rows of every backend table, each call in its own committed transaction."""

    def __init__(self, owner_engine: AsyncEngine) -> None:
        """Keep the owner engine and start the counter of IDs and times.

        Args:
            owner_engine: An engine that connects as the owner.
        """
        self._engine = owner_engine
        self._counter = count(1)

    def next_number(self) -> int:
        """Return the next number of this builder, for unique test values."""
        return next(self._counter)

    def next_uuid(self) -> UUID:
        """Return the next deterministic UUID of this builder."""
        return UUID(int=self.next_number())

    def next_time(self) -> datetime:
        """Return a time one minute after the previous one, in UTC."""
        return FAKE_CLOCK_START + timedelta(minutes=self.next_number())

    async def customer(self, *, display_name: str = "Lan Tran") -> UUID:
        """Insert a customer and return its ID."""
        customer_id = self.next_uuid()
        number = self.next_number()
        await self._insert(
            insert(CustomerRow).values(
                customer_id=customer_id,
                display_name=display_name,
                email=f"customer{number}@example.test",
                phone=f"+84 90 000 {number:04d}",
            )
        )
        return customer_id

    async def account(self, spec: AccountSpec) -> UUID:
        """Insert an account and return its ID; a customer account needs `customer_id`."""
        account_id = self.next_uuid()
        number = self.next_number()
        await self._insert(
            insert(AccountRow).values(
                account_id=account_id,
                login_name=spec.login_name or f"{spec.role}-{number}",
                display_name=spec.display_name or f"{spec.role.title()} {number}",
                role=spec.role,
                is_active=spec.is_active,
                customer_id=spec.customer_id,
                password_hash=spec.password_hash,
                created_at=self.next_time(),
            )
        )
        return account_id

    async def customer_account(self, *, display_name: str = "Lan Tran") -> tuple[UUID, UUID]:
        """Insert a customer and its account; return the account ID and the customer ID."""
        customer_id = await self.customer(display_name=display_name)
        account_id = await self.account(AccountSpec("customer", customer_id=customer_id))
        return account_id, customer_id

    async def product(
        self, *, name: str = "Desk lamp", product_id: str | None = None, price_minor: int = 2_450
    ) -> str:
        """Insert a catalog product and return its ID."""
        identifier = product_id or f"PRD-{self.next_number():04d}"
        await self._insert(
            insert(ProductRow).values(
                product_id=identifier,
                name=name,
                description=f"The description of {name}.",
                category="Home office",
                price_amount_minor=price_minor,
                price_currency=CURRENCY,
            )
        )
        return identifier

    async def order(self, customer_id: UUID, spec: OrderSpec) -> str:
        """Insert an order with its lines, and its shipment and refund when given."""
        number = self.next_number()
        order_id = f"ORD-{number:05d}"
        await self._insert(
            insert(OrderRow).values(
                order_id=order_id,
                customer_id=customer_id,
                order_status=spec.order_status,
                placed_at=spec.placed_at or self.next_time(),
                order_total_amount_minor=4_250,
                order_total_currency=CURRENCY,
                shipping_cost_amount_minor=0,
                shipping_cost_currency=CURRENCY,
                shipping_address=f"{number} Example Street, Hanoi",
                transaction_id=f"TXN-{number:08d}",
            ),
            *(
                insert(OrderLineRow).values(
                    order_id=order_id,
                    line_number=line_number,
                    product_id=line.product_id,
                    quantity=line.quantity,
                )
                for line_number, line in enumerate(spec.lines, start=1)
            ),
        )
        await self._insert_shipment(order_id, number, spec.shipment)
        await self._insert_refund(order_id, spec.refund)
        return order_id

    async def order_of_one_product(self, customer_id: UUID) -> str:
        """Insert a product and an order of it for the customer; return the order ID."""
        product_id = await self.product()
        return await self.order(customer_id, OrderSpec(lines=(LineSpec(product_id),)))

    async def ticket(
        self, customer_id: UUID, order_id: str | None, spec: TicketSpec | None = None
    ) -> str:
        """Insert a ticket with its customer message and return the ticket ID."""
        ticket = spec or TicketSpec()
        moment = ticket.created_at or self.next_time()
        async with self._engine.begin() as connection:
            ticket_id = await connection.scalar(
                insert(TicketRow)
                .values(
                    customer_id=customer_id,
                    order_id=order_id,
                    status=ticket.status,
                    handling_mode="assisted",
                    is_authority_required=ticket.is_authority_required,
                    source=ticket.source,
                    created_at=moment,
                )
                .returning(TicketRow.ticket_id)
            )
            await connection.execute(
                insert(CustomerMessageRow).values(
                    message_id=self.next_uuid(),
                    ticket_id=ticket_id,
                    body=ticket.message,
                    created_at=moment,
                )
            )
        return str(ticket_id)

    async def session(
        self,
        account_id: UUID,
        role: str,
        *,
        last_seen_at: datetime = FAKE_CLOCK_START,
        expires_at: datetime = FAKE_CLOCK_START + timedelta(hours=8),
    ) -> str:
        """Insert a session of the account and return the raw identifier, for the cookie."""
        token = f"test-session-{self.next_number()}"
        await self._insert(
            insert(SessionRow).values(
                session_id_hash=hash_session_token(SessionToken(token)),
                account_id=account_id,
                role=role,
                created_at=FAKE_CLOCK_START,
                last_seen_at=last_seen_at,
                expires_at=expires_at,
            )
        )
        return token

    async def scalar(self, statement: str, **parameters: object) -> object:
        """Run one read statement as the owner and return its first value.

        Args:
            statement: The SQL text with bound parameters.
            **parameters: The parameters.
        """
        async with self._engine.connect() as connection:
            return await connection.scalar(text(statement), parameters)

    async def _insert_shipment(
        self, order_id: str, number: int, shipment: ShipmentSpec | None
    ) -> None:
        if shipment is None:
            return
        await self._insert(
            insert(ShipmentRow).values(
                shipment_id=self.next_uuid(),
                order_id=order_id,
                shipment_status=shipment.shipment_status,
                tracking_code=f"TRK-{number:010d}",
                estimated_delivery_at=shipment.estimated_delivery_at,
                delivered_at=shipment.delivered_at,
            )
        )

    async def _insert_refund(self, order_id: str, refund: RefundSpec | None) -> None:
        if refund is None:
            return
        moment = self.next_time()
        await self._insert(
            insert(RefundRow).values(
                refund_id=self.next_uuid(),
                order_id=order_id,
                refund_status=refund.refund_status,
                refund_amount_minor=refund.refund_amount_minor,
                refund_currency=CURRENCY,
                refund_requested_at=moment,
                updated_at=moment,
            )
        )

    async def _insert(self, *statements: Executable) -> None:
        async with self._engine.begin() as connection:
            for statement in statements:
                await connection.execute(statement)

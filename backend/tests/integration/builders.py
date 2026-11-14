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

from sqlalchemy import insert, null, text, update
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
from supportiq_backend.suggestions.adapters.tables import (
    SuggestionJobRow,
    SuggestionPartRow,
    SuggestionRow,
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
        handling_mode: `assisted` or `manual`.
        handling_started_at: Its first view, if any.
        closed_at: When its reply was sent, if it was.
        study_pair_id: Its study pair, if any.
        study_batch: Its study batch, if any.
    """

    message: str = "Where is my parcel?"
    status: str = "open"
    source: str = "shop"
    is_authority_required: bool = False
    created_at: datetime | None = None
    handling_mode: str = "assisted"
    handling_started_at: datetime | None = None
    closed_at: datetime | None = None
    study_pair_id: str | None = None
    study_batch: str | None = None


@dataclass(frozen=True, slots=True)
class SuggestionPartSpec:
    """One part of a suggestion with a state of its own, as stored.

    Attributes:
        status: The status.
        completed_at: When it left `pending`; None exactly for a pending part.
        reason_codes: The AI reason codes.
        llm_cost_micro_usd: The LLM cost, if the LLM answered.
        result: The ai-service response, if the part has one.
    """

    status: str = "pending"
    completed_at: datetime | None = None
    reason_codes: tuple[str, ...] = ()
    llm_cost_micro_usd: int | None = None
    result: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SuggestionSpec:
    """A current suggestion of a ticket whose two parts share one state, and its job.

    Attributes:
        part_status: The status of both parts: `pending`, or `unavailable` with a reason.
        reason_code: The reason code of both parts; set exactly when they are not pending.
        job_state: The state of its job.
        created_at: When it was created; the next time of the builder when None.
        trigger: Why it was created.
        intent_override: The intent that staff chose, for the trigger `intent_override`.
        requested_by_account_id: The staff account that asked for it; set exactly when the
            trigger is not `ticket_created`.
        request: The `SuggestionRequest` as sent; None before pseudonymization succeeded.
        analysis: The analysis part with a state of its own, in place of the shared one.
        draft: The draft part with a state of its own, in place of the shared one.
    """

    part_status: str = "pending"
    reason_code: str | None = None
    job_state: str = "queued"
    created_at: datetime | None = None
    trigger: str = "ticket_created"
    intent_override: str | None = None
    requested_by_account_id: UUID | None = None
    request: dict[str, object] | None = None
    analysis: SuggestionPartSpec | None = None
    draft: SuggestionPartSpec | None = None


# A suggestion whose calls to ai-service failed, so a retry is valid (contract
# `createSuggestion`).
FAILED_SUGGESTION = SuggestionSpec("unavailable", "ai_service_unavailable", "done")
SUGGESTION_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


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
                    handling_mode=ticket.handling_mode,
                    is_authority_required=ticket.is_authority_required,
                    source=ticket.source,
                    created_at=moment,
                    handling_started_at=ticket.handling_started_at,
                    closed_at=ticket.closed_at,
                    study_pair_id=ticket.study_pair_id,
                    study_batch=ticket.study_batch,
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

    async def suggestion(self, ticket_id: str, spec: SuggestionSpec | None = None) -> UUID:
        """Insert a suggestion with its two parts and its job, and make it the current one.

        Args:
            ticket_id: The ticket.
            spec: The suggestion, its parts, and its job; pending parts and a queued job when
                None.

        Returns:
            The suggestion ID.
        """
        suggestion = spec or SuggestionSpec()
        suggestion_id = self.next_uuid()
        moment = suggestion.created_at or self.next_time()
        shared = _shared_part(suggestion, moment)
        parts = {"analysis": suggestion.analysis or shared, "draft": suggestion.draft or shared}
        await self._insert(
            insert(SuggestionRow).values(
                suggestion_id=suggestion_id,
                ticket_id=ticket_id,
                trigger=suggestion.trigger,
                intent_override=suggestion.intent_override,
                requested_by_account_id=suggestion.requested_by_account_id,
                created_at=moment,
                trace_id=SUGGESTION_TRACE_ID,
                request=null() if suggestion.request is None else suggestion.request,
            ),
            insert(SuggestionPartRow).values(
                [_part_values(suggestion_id, name, part) for name, part in parts.items()]
            ),
            insert(SuggestionJobRow).values(
                suggestion_id=suggestion_id,
                state=suggestion.job_state,
                attempt_number=0 if suggestion.job_state == "queued" else 1,
                created_at=moment,
                updated_at=moment,
            ),
            update(TicketRow)
            .where(TicketRow.ticket_id == ticket_id)
            .values(current_suggestion_id=suggestion_id),
        )
        return suggestion_id

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

    async def execute(self, *statements: Executable) -> None:
        """Run write statements as the owner in one transaction, for rows no method builds."""
        await self._insert(*statements)

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


def _shared_part(spec: SuggestionSpec, moment: datetime) -> SuggestionPartSpec:
    # The state of both parts, unless the spec gives a part a state of its own.
    return SuggestionPartSpec(
        status=spec.part_status,
        completed_at=None if spec.part_status == "pending" else moment,
        reason_codes=() if spec.reason_code is None else (spec.reason_code,),
    )


def _part_values(suggestion_id: UUID, part: str, spec: SuggestionPartSpec) -> dict[str, object]:
    return {
        "suggestion_id": suggestion_id,
        "part": part,
        "status": spec.status,
        "reason_codes": list(spec.reason_codes),
        "llm_cost_micro_usd": spec.llm_cost_micro_usd,
        "completed_at": spec.completed_at,
        "result": null() if spec.result is None else spec.result,
    }

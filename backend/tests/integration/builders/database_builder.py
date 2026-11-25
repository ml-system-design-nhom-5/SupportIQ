"""The one builder that the integration tests use, made of the builders of each area (TEST-05).

Each area module inserts its own rows; this class keeps one writer for all of them, so IDs and
times come from one counter, and it gives each test the defaults that it does not override.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import Executable

from tests.integration.builders.accounts import AccountRows, AccountSpec
from tests.integration.builders.commerce import CommerceRows, LineSpec, OrderSpec
from tests.integration.builders.rows import RowWriter
from tests.integration.builders.suggestions import SuggestionRows, SuggestionSpec
from tests.integration.builders.tickets import TicketRows, TicketSpec
from tests.unit.platform.fakes import FAKE_CLOCK_START


class DatabaseBuilder:
    """Insert rows of every backend table, each call in its own committed transaction."""

    def __init__(self, owner_engine: AsyncEngine) -> None:
        """Keep one writer for every area, which starts the counter of IDs and times.

        Args:
            owner_engine: An engine that connects as the owner.
        """
        self._writer = RowWriter(owner_engine)
        self._accounts = AccountRows(self._writer)
        self._commerce = CommerceRows(self._writer)
        self._tickets = TicketRows(self._writer)
        self._suggestions = SuggestionRows(self._writer)

    def next_number(self) -> int:
        """Return the next number of this builder, for unique test values."""
        return self._writer.next_number()

    def next_uuid(self) -> UUID:
        """Return the next deterministic UUID of this builder."""
        return self._writer.next_uuid()

    def next_time(self) -> datetime:
        """Return a time one minute after the previous one, in UTC."""
        return self._writer.next_time()

    async def customer(self, *, display_name: str = "Lan Tran") -> UUID:
        """Insert a customer and return its ID."""
        return await self._commerce.customer(display_name)

    async def account(self, spec: AccountSpec) -> UUID:
        """Insert an account and return its ID; a customer account needs `customer_id`."""
        return await self._accounts.account(spec)

    async def customer_account(self, *, display_name: str = "Lan Tran") -> tuple[UUID, UUID]:
        """Insert a customer and its account; return the account ID and the customer ID."""
        customer_id = await self.customer(display_name=display_name)
        account_id = await self.account(AccountSpec("customer", customer_id=customer_id))
        return account_id, customer_id

    async def product(
        self, *, name: str = "Desk lamp", product_id: str | None = None, price_minor: int = 2_450
    ) -> str:
        """Insert a catalog product and return its ID."""
        return await self._commerce.product(name, product_id, price_minor)

    async def order(self, customer_id: UUID, spec: OrderSpec) -> str:
        """Insert an order with its lines, and its shipment and refund when given."""
        return await self._commerce.order(customer_id, spec)

    async def order_of_one_product(self, customer_id: UUID) -> str:
        """Insert a product and an order of it for the customer; return the order ID."""
        product_id = await self.product()
        return await self.order(customer_id, OrderSpec(lines=(LineSpec(product_id),)))

    async def ticket(
        self, customer_id: UUID, order_id: str | None, spec: TicketSpec | None = None
    ) -> str:
        """Insert a ticket with its customer message and return the ticket ID."""
        return await self._tickets.ticket(customer_id, order_id, spec or TicketSpec())

    async def suggestion(self, ticket_id: str, spec: SuggestionSpec | None = None) -> UUID:
        """Insert a suggestion with its two parts and its job, and make it the current one.

        Args:
            ticket_id: The ticket.
            spec: The suggestion, its parts, and its job; pending parts and a queued job when
                None.

        Returns:
            The suggestion ID.
        """
        return await self._suggestions.suggestion(ticket_id, spec or SuggestionSpec())

    async def session(
        self,
        account_id: UUID,
        role: str,
        *,
        last_seen_at: datetime = FAKE_CLOCK_START,
        expires_at: datetime = FAKE_CLOCK_START + timedelta(hours=8),
    ) -> str:
        """Insert a session of the account and return the raw identifier, for the cookie."""
        return await self._accounts.session(account_id, role, last_seen_at, expires_at)

    async def execute(self, *statements: Executable) -> None:
        """Run write statements as the owner in one transaction, for rows no method builds."""
        await self._writer.execute(*statements)

    async def scalar(self, statement: str, **parameters: object) -> object:
        """Run one read statement as the owner and return its first value.

        Args:
            statement: The SQL text with bound parameters.
            **parameters: The parameters.
        """
        return await self._writer.scalar(statement, **parameters)

"""The `CustomerRecords` port on the commerce tables, for pseudonymization and the console.

`supportiq_app` may only read these tables. Every query filters by the customer, so a ticket
of one customer never reaches another customer's records (SEC-17).
"""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import case, collate, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import CustomerId
from app.commerce.adapters.order_rows import load_order_details
from app.commerce.adapters.tables import (
    CustomerRow,
    OrderRow,
    ProductRow,
    ShipmentRow,
)
from app.commerce.domain import (
    AddressedOrder,
    CustomerContact,
    OrderId,
    OrderReferences,
)
from app.platform import is_storable_text
from app.platform.persistence import BYTE_ORDER_COLLATION


class PostgresCustomerRecords:
    """Implement the `CustomerRecords` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the records to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_contact(self, customer_id: CustomerId) -> CustomerContact | None:
        """Load the personal values of a customer.

        Args:
            customer_id: The customer.

        Returns:
            The values, or None when the customer is unknown.
        """
        row = await self._session.get(CustomerRow, UUID(customer_id))
        if row is None:
            return None
        return CustomerContact(row.display_name, row.email, row.phone)

    async def load_order_references(
        self, customer_id: CustomerId, order_id: OrderId
    ) -> OrderReferences | None:
        """Load the identifying values of one of the customer's orders.

        Args:
            customer_id: The customer.
            order_id: The order.

        Returns:
            The values, or None when the order is unknown or another customer's.
        """
        if not is_storable_text(order_id):
            return None
        result = await self._session.execute(
            select(OrderRow.order_id, OrderRow.transaction_id, OrderRow.shipping_address)
            .add_columns(ShipmentRow.tracking_code)
            .outerjoin(ShipmentRow, ShipmentRow.order_id == OrderRow.order_id)
            .where(OrderRow.order_id == order_id, OrderRow.customer_id == UUID(customer_id))
        )
        row = result.one_or_none()
        if row is None:
            return None
        return OrderReferences(
            order_id=OrderId(row.order_id),
            tracking_code=row.tracking_code,
            transaction_id=row.transaction_id,
            shipping_address=row.shipping_address,
        )

    async def load_product_names(self) -> tuple[str, ...]:
        """Load the name of every product of the catalog, which is no personal data.

        Returns:
            The names.
        """
        return tuple(await self._session.scalars(select(ProductRow.name)))

    async def load_display_names(
        self, customer_ids: frozenset[CustomerId]
    ) -> Mapping[CustomerId, str]:
        """Load the display names of several customers in one query.

        Args:
            customer_ids: The customers.

        Returns:
            The display name of each known customer.
        """
        if not customer_ids:
            return {}
        rows = await self._session.execute(
            select(CustomerRow.customer_id, CustomerRow.display_name).where(
                CustomerRow.customer_id.in_([UUID(customer_id) for customer_id in customer_ids])
            )
        )
        return {CustomerId(str(row.customer_id)): row.display_name for row in rows}

    async def load_addressed_orders(
        self, customer_id: CustomerId, ticket_order_id: OrderId | None, other_order_limit: int
    ) -> tuple[AddressedOrder, ...]:
        """Load a ticket's order and the customer's newest other orders, with their addresses.

        Args:
            customer_id: The customer.
            ticket_order_id: The ticket's order, always loaded when it is the customer's.
            other_order_limit: The most other orders to load.

        Returns:
            The ticket's order first, then the other orders by `placed_at` descending, then by
            order ID by code point.

        Raises:
            UnexpectedFailureError: A stored order, shipment, or refund status is no value of its
                enum: a defect.
        """
        is_other_order = case((OrderRow.order_id == ticket_order_id, 0), else_=1)
        rows = (
            await self._session.scalars(
                select(OrderRow)
                .where(OrderRow.customer_id == UUID(customer_id))
                .order_by(
                    is_other_order,
                    OrderRow.placed_at.desc(),
                    collate(OrderRow.order_id, BYTE_ORDER_COLLATION),
                )
                .limit(other_order_limit + 1)
            )
        ).all()
        orders = await load_order_details(self._session, rows)
        addressed = tuple(
            AddressedOrder(order, row.shipping_address)
            for order, row in zip(orders, rows, strict=True)
        )
        # One row more than the limit leaves room for the ticket's order; without it among
        # the rows, the extra one is cut.
        ticket_orders = tuple(item for item in addressed if item.order.order_id == ticket_order_id)
        others = tuple(item for item in addressed if item.order.order_id != ticket_order_id)
        return (*ticket_orders, *others[:other_order_limit])

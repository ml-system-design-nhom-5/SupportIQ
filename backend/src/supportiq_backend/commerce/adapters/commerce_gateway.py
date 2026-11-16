"""The commerce data in PostgreSQL: the only reader of its tables (ADR-0001, ADR-0013).

`supportiq_app` may only read these tables, so a write here could not succeed anyway. Rows of
an order are loaded with one query per table, never one per order, and they are matched in
memory, so no relationship and no lazy load exists.
"""

from uuid import UUID

from sqlalchemy import and_, collate, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce.adapters.order_rows import load_order_details
from supportiq_backend.commerce.adapters.tables import OrderRow, ProductRow
from supportiq_backend.commerce.domain import (
    Money,
    Order,
    OrderId,
    Product,
    ProductId,
    ProductPosition,
)
from supportiq_backend.platform import is_storable_text
from supportiq_backend.platform.persistence import BYTE_ORDER_COLLATION


class PostgresCommerceGateway:
    """Implement the `CommerceGateway` port. Every order query filters by the customer."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the gateway to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def load_products(self, after: ProductPosition | None, limit: int) -> tuple[Product, ...]:
        """Load products by name, then product ID, by code point.

        Args:
            after: The last product of the previous page, or None for the first page.
            limit: The maximum number of products.

        Returns:
            The products.
        """
        name = collate(ProductRow.name, BYTE_ORDER_COLLATION)
        product_id = collate(ProductRow.product_id, BYTE_ORDER_COLLATION)
        statement = select(ProductRow).order_by(name, product_id).limit(limit)
        if after is not None:
            statement = statement.where(
                or_(
                    name > after.name,
                    and_(ProductRow.name == after.name, product_id > after.product_id),
                )
            )
        rows = await self._session.scalars(statement)
        return tuple(_to_product(row) for row in rows)

    async def load_product(self, product_id: ProductId) -> Product | None:
        """Load one product.

        Args:
            product_id: The identifier, as a request sent it.

        Returns:
            The product, or None when it is unknown.
        """
        if not is_storable_text(product_id):
            return None
        row = await self._session.scalar(
            select(ProductRow).where(ProductRow.product_id == product_id)
        )
        return None if row is None else _to_product(row)

    async def load_orders(
        self, customer_id: CustomerId, *, position: int, limit: int
    ) -> tuple[Order, ...]:
        """Load the orders of one customer, newest first, then by order ID by code point.

        Args:
            customer_id: The customer.
            position: The position of the first order to load, from 0.
            limit: The maximum number of orders.

        Returns:
            The orders.

        Raises:
            UnexpectedFailureError: A stored order, shipment, or refund status is no value of its
                enum: a defect.
        """
        rows = await self._session.scalars(
            select(OrderRow)
            .where(OrderRow.customer_id == UUID(customer_id))
            .order_by(OrderRow.placed_at.desc(), collate(OrderRow.order_id, BYTE_ORDER_COLLATION))
            .offset(position)
            .limit(limit)
        )
        return await load_order_details(self._session, rows.all())

    async def load_order(self, customer_id: CustomerId, order_id: OrderId) -> Order | None:
        """Load one order of one customer.

        Args:
            customer_id: The customer.
            order_id: The order, as a request sent it.

        Returns:
            The order, or None when it is unknown or belongs to another customer.

        Raises:
            UnexpectedFailureError: A stored order, shipment, or refund status is no value of its
                enum: a defect.
        """
        if not is_storable_text(order_id):
            return None
        row = await self._session.scalar(
            select(OrderRow).where(
                OrderRow.order_id == order_id, OrderRow.customer_id == UUID(customer_id)
            )
        )
        if row is None:
            return None
        (order,) = await load_order_details(self._session, [row])
        return order

    async def is_order_of_customer(self, customer_id: CustomerId, order_id: OrderId) -> bool:
        """Tell whether an order exists and belongs to a customer.

        Args:
            customer_id: The customer.
            order_id: The order, as a request sent it.

        Returns:
            True for an order of the customer.
        """
        if not is_storable_text(order_id):
            return False
        found = await self._session.scalar(
            select(
                exists().where(
                    OrderRow.order_id == order_id, OrderRow.customer_id == UUID(customer_id)
                )
            )
        )
        return bool(found)


def _to_product(row: ProductRow) -> Product:
    return Product(
        product_id=ProductId(row.product_id),
        name=row.name,
        description=row.description,
        category=row.category,
        price=Money(row.price_amount_minor, row.price_currency),
    )

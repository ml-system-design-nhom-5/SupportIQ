"""The `CommerceGateway` port: every read of commerce data (ADR-0001, ADR-0013)."""

from typing import Protocol

from app.accounts import CustomerId
from app.commerce.domain.catalog import (
    Order,
    OrderId,
    Product,
    ProductId,
    ProductPosition,
)


class CommerceGateway(Protocol):
    """Read the simulated commerce data; no method writes, and none exists to write."""

    async def load_products(self, after: ProductPosition | None, limit: int) -> tuple[Product, ...]:
        """Load products by name, then product ID, by code point.

        Args:
            after: The last product of the previous page, or None for the first page.
            limit: The maximum number of products.

        Returns:
            The products.
        """
        ...

    async def load_product(self, product_id: ProductId) -> Product | None:
        """Load one product.

        Args:
            product_id: The identifier, as a request sent it.

        Returns:
            The product, or None when it is unknown.
        """
        ...

    async def load_orders(
        self, customer_id: CustomerId, *, position: int, limit: int
    ) -> tuple[Order, ...]:
        """Load the orders of one customer, newest first, then by order ID.

        Args:
            customer_id: The customer; no other customer's order is ever returned (SEC-17).
            position: The position of the first order to load, from 0.
            limit: The maximum number of orders.

        Returns:
            The orders.
        """
        ...

    async def load_order(self, customer_id: CustomerId, order_id: OrderId) -> Order | None:
        """Load one order of one customer.

        Args:
            customer_id: The customer.
            order_id: The order, as a request sent it.

        Returns:
            The order, or None when it is unknown or belongs to another customer.
        """
        ...

    async def is_order_of_customer(self, customer_id: CustomerId, order_id: OrderId) -> bool:
        """Tell whether an order exists and belongs to a customer.

        Args:
            customer_id: The customer.
            order_id: The order, as a request sent it.

        Returns:
            True for an order of the customer.
        """
        ...

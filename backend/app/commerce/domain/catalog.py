"""The simulated commerce data: products, orders, shipments, and refunds (ADR-0013).

Everything here is read-only: the seed writes it, and no operation changes it. Products are
Public. An order and everything about it is Confidential, so those classes have no generated
`repr`, and an order ID never reaches a log, a trace, or an error (LOG-29).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

ProductId = NewType("ProductId", str)
OrderId = NewType("OrderId", str)

# The `synthetic-dev-only` formats of the seed, which pseudonymization detects in free text
# (backend foundation design, Tables). The log redaction uses the same patterns.
ORDER_ID_PATTERN = re.compile(r"ORD-[0-9]{5}")
TRACKING_CODE_PATTERN = re.compile(r"TRK-[0-9]{10}")
TRANSACTION_ID_PATTERN = re.compile(r"TXN-[0-9]{8}")
PHONE_PATTERN = re.compile(r"\+84 [0-9]{2} [0-9]{3} [0-9]{4}")


class OrderStatus(StrEnum):
    """The status of an order, as the contract's `OrderStatus` defines it."""

    PLACED = "placed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ShipmentStatus(StrEnum):
    """The status of a shipment, as the contract's `ShipmentStatus` defines it."""

    NOT_SHIPPED = "not_shipped"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    LOST = "lost"


class RefundStatus(StrEnum):
    """The status of a refund, as the contract's `RefundStatus` defines it."""

    REQUESTED = "requested"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in minor units with its currency (CON-16).

    Attributes:
        amount_minor: The amount in the minor unit of the currency.
        currency: The ISO 4217 code.
    """

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True)
class Product:
    """A product of the read-only catalog. Public.

    Attributes:
        product_id: The identifier.
        name: The name.
        description: The description, as plain text.
        category: The name of its category.
        price: The price of one unit.
    """

    product_id: ProductId
    name: str
    description: str
    category: str
    price: Money


@dataclass(frozen=True, slots=True)
class ProductPosition:
    """The place of a product in the catalog order, from Public values only.

    Attributes:
        name: The name of the last product of a page.
        product_id: Its identifier.
    """

    name: str
    product_id: ProductId


@dataclass(frozen=True, slots=True)
class ProductPage:
    """One page of the catalog.

    Attributes:
        items: The products of the page.
        next_position: The last product of the page when more follow.
    """

    items: tuple[Product, ...]
    next_position: ProductPosition | None


@dataclass(frozen=True, slots=True, repr=False)
class OrderLine:
    """One line of an order.

    Attributes:
        product_id: The catalog product.
        product_name: Its name.
        quantity: The number of units.
    """

    product_id: ProductId
    product_name: str
    quantity: int


@dataclass(frozen=True, slots=True, repr=False)
class Shipment:
    """The shipment of an order.

    Attributes:
        status: The status.
        estimated_delivery_at: The estimate, when the commerce data holds one.
        delivered_at: The delivery time, exactly when the status is `delivered`.
    """

    status: ShipmentStatus
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None


@dataclass(frozen=True, slots=True, repr=False)
class Refund:
    """The refund of an order.

    Attributes:
        status: The status.
        amount: The amount requested.
        requested_at: When it was requested.
    """

    status: RefundStatus
    amount: Money
    requested_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class Order:
    """One of a customer's orders, as the shop shows it.

    It holds no shipping address and no transaction ID (contract `ShopOrderView`).

    Attributes:
        order_id: The identifier.
        status: The status.
        placed_at: When it was placed.
        order_total: The total paid, shipping included.
        shipping_cost: The shipping cost.
        lines: The lines, by line number.
        shipment: The shipment; `not_shipped` when no record exists yet.
        refund: The refund, when one was requested.
    """

    order_id: OrderId
    status: OrderStatus
    placed_at: datetime
    order_total: Money
    shipping_cost: Money
    lines: tuple[OrderLine, ...]
    shipment: Shipment
    refund: Refund | None


@dataclass(frozen=True, slots=True, repr=False)
class OrderPage:
    """One page of a customer's orders.

    Attributes:
        items: The orders of the page.
        next_position: The position of the next item when more follow. A position is exact,
            because orders are read-only and the seed is deterministic.
    """

    items: tuple[Order, ...]
    next_position: int | None

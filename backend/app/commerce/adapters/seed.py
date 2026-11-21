"""The commerce section of the seed file, and its insert as the owner (DATA-03, DATA-04).

The seed is the only writer of the commerce tables, and it runs as `supportiq_owner`, never as
`supportiq_app`. The models validate the file strictly, including the documented ID formats.
"""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.commerce.adapters.tables import (
    CustomerRow,
    OrderLineRow,
    OrderRow,
    ProductRow,
    RefundRow,
    ShipmentRow,
)
from app.commerce.domain import (
    ORDER_ID_PATTERN,
    PHONE_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
    OrderStatus,
    RefundStatus,
    ShipmentStatus,
)

type SeedRow = dict[str, str | int | datetime | UUID | None]


class SeedFormatError(ValueError):
    """A value of the seed file does not follow its documented format."""

    def __init__(self, pattern: str) -> None:
        """Build the error from the format; the value itself is not repeated.

        Args:
            pattern: The regular expression of the format.
        """
        super().__init__(f"The value does not match {pattern}")


def _matching(pattern: re.Pattern[str]) -> AfterValidator:
    def require_match(value: str) -> str:
        if pattern.fullmatch(value) is None:
            raise SeedFormatError(pattern.pattern)
        return value

    return AfterValidator(require_match)


class _SeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=False)


class SeedMoney(_SeedModel):
    """An amount of money in the seed file."""

    amount_minor: Annotated[int, Field(ge=0)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class SeedCustomer(_SeedModel):
    """A customer. Names, emails, and phones are invented (SEC-02)."""

    customer_id: UUID
    display_name: Annotated[str, Field(min_length=1)]
    email: Annotated[str, Field(min_length=1)]
    phone: Annotated[str, _matching(PHONE_PATTERN)]


class SeedProduct(_SeedModel):
    """A product of the catalog."""

    product_id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]
    category: Annotated[str, Field(min_length=1)]
    price: SeedMoney


class SeedOrderLine(_SeedModel):
    """One line of an order; its position in the file is its line number."""

    product_id: Annotated[str, Field(min_length=1)]
    quantity: Annotated[int, Field(ge=1)]


class SeedShipment(_SeedModel):
    """The shipment of an order."""

    shipment_id: UUID
    shipment_status: ShipmentStatus
    tracking_code: Annotated[str, _matching(TRACKING_CODE_PATTERN)]
    estimated_delivery_at: AwareDatetime | None
    delivered_at: AwareDatetime | None


class SeedRefund(_SeedModel):
    """The refund of an order."""

    refund_id: UUID
    refund_status: RefundStatus
    refund_amount: SeedMoney
    refund_requested_at: AwareDatetime
    updated_at: AwareDatetime


class SeedOrder(_SeedModel):
    """An order with its lines, its shipment, and its refund."""

    order_id: Annotated[str, _matching(ORDER_ID_PATTERN)]
    customer_id: UUID
    order_status: OrderStatus
    placed_at: AwareDatetime
    order_total: SeedMoney
    shipping_cost: SeedMoney
    shipping_address: Annotated[str, Field(min_length=1)]
    transaction_id: Annotated[str, _matching(TRANSACTION_ID_PATTERN)]
    lines: Annotated[tuple[SeedOrderLine, ...], Field(min_length=1)]
    shipment: SeedShipment | None
    refund: SeedRefund | None


class CommerceSeed(_SeedModel):
    """The commerce section of the seed file."""

    customers: tuple[SeedCustomer, ...]
    products: tuple[SeedProduct, ...]
    orders: tuple[SeedOrder, ...]


async def insert_customers(connection: AsyncConnection, seed: CommerceSeed) -> None:
    """Insert the customers, before the accounts that reference them.

    Args:
        connection: An owner connection in the transaction of the command.
        seed: The commerce section.
    """
    await connection.execute(
        insert(CustomerRow), [customer.model_dump() for customer in seed.customers]
    )


async def insert_catalog_and_orders(connection: AsyncConnection, seed: CommerceSeed) -> None:
    """Insert the products and the orders with their lines, shipments, and refunds.

    Args:
        connection: An owner connection in the transaction of the command.
        seed: The commerce section.
    """
    await connection.execute(insert(ProductRow), [_to_product_row(row) for row in seed.products])
    await connection.execute(insert(OrderRow), [_to_order_row(order) for order in seed.orders])
    await connection.execute(insert(OrderLineRow), _to_line_rows(seed))
    await connection.execute(insert(ShipmentRow), _to_shipment_rows(seed))
    await connection.execute(insert(RefundRow), _to_refund_rows(seed))


def _to_product_row(product: SeedProduct) -> SeedRow:
    return {
        "product_id": product.product_id,
        "name": product.name,
        "description": product.description,
        "category": product.category,
        "price_amount_minor": product.price.amount_minor,
        "price_currency": product.price.currency,
    }


def _to_order_row(order: SeedOrder) -> SeedRow:
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "order_status": order.order_status.value,
        "placed_at": order.placed_at,
        "order_total_amount_minor": order.order_total.amount_minor,
        "order_total_currency": order.order_total.currency,
        "shipping_cost_amount_minor": order.shipping_cost.amount_minor,
        "shipping_cost_currency": order.shipping_cost.currency,
        "shipping_address": order.shipping_address,
        "transaction_id": order.transaction_id,
    }


def _to_line_rows(seed: CommerceSeed) -> list[SeedRow]:
    return [
        {
            "order_id": order.order_id,
            "line_number": line_number,
            "product_id": line.product_id,
            "quantity": line.quantity,
        }
        for order in seed.orders
        for line_number, line in enumerate(order.lines, start=1)
    ]


def _to_shipment_rows(seed: CommerceSeed) -> list[SeedRow]:
    return [
        {
            "shipment_id": order.shipment.shipment_id,
            "order_id": order.order_id,
            "shipment_status": order.shipment.shipment_status.value,
            "tracking_code": order.shipment.tracking_code,
            "estimated_delivery_at": order.shipment.estimated_delivery_at,
            "delivered_at": order.shipment.delivered_at,
        }
        for order in seed.orders
        if order.shipment is not None
    ]


def _to_refund_rows(seed: CommerceSeed) -> list[SeedRow]:
    return [
        {
            "refund_id": order.refund.refund_id,
            "order_id": order.order_id,
            "refund_status": order.refund.refund_status.value,
            "refund_amount_minor": order.refund.refund_amount.amount_minor,
            "refund_currency": order.refund.refund_amount.currency,
            "refund_requested_at": order.refund.refund_requested_at,
            "updated_at": order.refund.updated_at,
        }
        for order in seed.orders
        if order.refund is not None
    ]

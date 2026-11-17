"""Builders of customers, catalog products, and orders, with shipments and refunds (TEST-05)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert

from supportiq_backend.commerce.adapters.tables import (
    CustomerRow,
    OrderLineRow,
    OrderRow,
    ProductRow,
    RefundRow,
    ShipmentRow,
)
from tests.integration.builders.rows import RowWriter

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


class CommerceRows:
    """Insert customers, catalog products, and orders."""

    def __init__(self, writer: RowWriter) -> None:
        """Keep the writer that every area shares.

        Args:
            writer: Writes the rows and gives their deterministic values.
        """
        self._writer = writer

    async def customer(self, display_name: str) -> UUID:
        """Insert a customer and return its ID."""
        customer_id = self._writer.next_uuid()
        number = self._writer.next_number()
        await self._writer.execute(
            insert(CustomerRow).values(
                customer_id=customer_id,
                display_name=display_name,
                email=f"customer{number}@example.test",
                phone=f"+84 90 000 {number:04d}",
            )
        )
        return customer_id

    async def product(self, name: str, product_id: str | None, price_minor: int) -> str:
        """Insert a catalog product and return its ID, numbered when `product_id` is None."""
        identifier = product_id or f"PRD-{self._writer.next_number():04d}"
        await self._writer.execute(
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
        number = self._writer.next_number()
        order_id = f"ORD-{number:05d}"
        await self._writer.execute(
            insert(OrderRow).values(
                order_id=order_id,
                customer_id=customer_id,
                order_status=spec.order_status,
                placed_at=spec.placed_at or self._writer.next_time(),
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

    async def _insert_shipment(
        self, order_id: str, number: int, shipment: ShipmentSpec | None
    ) -> None:
        if shipment is None:
            return
        await self._writer.execute(
            insert(ShipmentRow).values(
                shipment_id=self._writer.next_uuid(),
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
        moment = self._writer.next_time()
        await self._writer.execute(
            insert(RefundRow).values(
                refund_id=self._writer.next_uuid(),
                order_id=order_id,
                refund_status=refund.refund_status,
                refund_amount_minor=refund.refund_amount_minor,
                refund_currency=CURRENCY,
                refund_requested_at=moment,
                updated_at=moment,
            )
        )

"""Order rows with their lines, shipments, and refunds, read with one query per table.

Rows of an order are matched in memory, so no relationship and no lazy load exists. Both
commerce adapters build their orders here.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from supportiq_backend.commerce.adapters.tables import (
    OrderLineRow,
    OrderRow,
    ProductRow,
    RefundRow,
    ShipmentRow,
)
from supportiq_backend.commerce.domain import (
    Money,
    Order,
    OrderId,
    OrderLine,
    OrderStatus,
    ProductId,
    Refund,
    RefundStatus,
    Shipment,
    ShipmentStatus,
)

_NO_SHIPMENT_RECORD = Shipment(ShipmentStatus.NOT_SHIPPED)


async def load_order_details(session: AsyncSession, rows: Sequence[OrderRow]) -> tuple[Order, ...]:
    """Build the orders of some rows, with their lines, shipments, and refunds.

    Args:
        session: The session of the transaction.
        rows: The order rows, in the order of the result.

    Returns:
        The orders, in the order of the rows.
    """
    order_ids = [row.order_id for row in rows]
    lines = await _load_lines(session, order_ids)
    shipments = await session.scalars(
        select(ShipmentRow).where(ShipmentRow.order_id.in_(order_ids))
    )
    refunds = await session.scalars(select(RefundRow).where(RefundRow.order_id.in_(order_ids)))
    shipment_by_order = {row.order_id: _to_shipment(row) for row in shipments}
    refund_by_order = {row.order_id: _to_refund(row) for row in refunds}
    return tuple(
        Order(
            order_id=OrderId(row.order_id),
            status=OrderStatus(row.order_status),
            placed_at=row.placed_at,
            order_total=Money(row.order_total_amount_minor, row.order_total_currency),
            shipping_cost=Money(row.shipping_cost_amount_minor, row.shipping_cost_currency),
            lines=lines.get(row.order_id, ()),
            shipment=shipment_by_order.get(row.order_id, _NO_SHIPMENT_RECORD),
            refund=refund_by_order.get(row.order_id),
        )
        for row in rows
    )


async def _load_lines(
    session: AsyncSession, order_ids: Sequence[str]
) -> dict[str, tuple[OrderLine, ...]]:
    rows = await session.execute(
        select(OrderLineRow, ProductRow.name)
        .join(ProductRow, ProductRow.product_id == OrderLineRow.product_id)
        .where(OrderLineRow.order_id.in_(order_ids))
        .order_by(OrderLineRow.order_id, OrderLineRow.line_number)
    )
    lines: dict[str, tuple[OrderLine, ...]] = {}
    for line, product_name in rows:
        order_line = OrderLine(ProductId(line.product_id), product_name, line.quantity)
        lines[line.order_id] = (*lines.get(line.order_id, ()), order_line)
    return lines


def _to_shipment(row: ShipmentRow) -> Shipment:
    return Shipment(
        status=ShipmentStatus(row.shipment_status),
        estimated_delivery_at=row.estimated_delivery_at,
        delivered_at=row.delivered_at,
    )


def _to_refund(row: RefundRow) -> Refund:
    return Refund(
        status=RefundStatus(row.refund_status),
        amount=Money(row.refund_amount_minor, row.refund_currency),
        requested_at=row.refund_requested_at,
    )

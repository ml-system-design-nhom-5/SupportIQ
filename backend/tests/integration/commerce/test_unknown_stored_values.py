"""Adapter tests of stored statuses that no enum of backend has, against PostgreSQL 17 (PY-20).

Both commerce stores build their orders in `order_rows`, which reads an unknown order,
shipment, or refund status as an unexpected failure (ERR-05). Each status has a check
constraint, which the test drops (`session_without_check`).
"""

from collections.abc import Callable
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.sql import Executable

from app.accounts import CustomerId
from app.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from app.commerce.adapters.customer_records import PostgresCustomerRecords
from app.commerce.adapters.tables import OrderRow, RefundRow, ShipmentRow
from app.commerce.domain import OrderId
from app.platform import UnexpectedFailureError
from tests.integration.builders import (
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    RefundSpec,
    ShipmentSpec,
)
from tests.integration.database import WorkerDatabase
from tests.integration.stored_values import UNKNOWN_VALUE, session_without_check

pytestmark = pytest.mark.anyio

DROP_ORDER_STATUS_CHECK = "ALTER TABLE orders DROP CONSTRAINT orders_order_status_check"
DROP_SHIPMENT_STATUS_CHECK = "ALTER TABLE shipments DROP CONSTRAINT shipments_shipment_status_check"
DROP_REFUND_STATUS_CHECK = "ALTER TABLE refunds DROP CONSTRAINT refunds_refund_status_check"
OTHER_ORDER_LIMIT = 5
type UnknownStatus = Callable[[str], Executable]


def unknown_order_status(order_id: str) -> Executable:
    return update(OrderRow).where(OrderRow.order_id == order_id).values(order_status=UNKNOWN_VALUE)


def unknown_shipment_status(order_id: str) -> Executable:
    return (
        update(ShipmentRow)
        .where(ShipmentRow.order_id == order_id)
        .values(shipment_status=UNKNOWN_VALUE)
    )


def unknown_refund_status(order_id: str) -> Executable:
    return (
        update(RefundRow).where(RefundRow.order_id == order_id).values(refund_status=UNKNOWN_VALUE)
    )


async def order_with_shipment_and_refund(builder: DatabaseBuilder) -> tuple[UUID, str]:
    """Insert a customer's order with a shipment and a refund; return both IDs."""
    customer_id = await builder.customer()
    product_id = await builder.product()
    spec = OrderSpec(lines=(LineSpec(product_id),), shipment=ShipmentSpec(), refund=RefundSpec())
    return customer_id, await builder.order(customer_id, spec)


@pytest.mark.parametrize(
    ("drop_check", "unknown_status"),
    [
        (DROP_ORDER_STATUS_CHECK, unknown_order_status),
        (DROP_SHIPMENT_STATUS_CHECK, unknown_shipment_status),
        (DROP_REFUND_STATUS_CHECK, unknown_refund_status),
    ],
    ids=["order", "shipment", "refund"],
)
async def test_load_order_of_an_unknown_status_is_an_unexpected_failure(
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    drop_check: str,
    unknown_status: UnknownStatus,
) -> None:
    customer_id, order_id = await order_with_shipment_and_refund(builder)

    async with session_without_check(
        worker_database, drop_check, unknown_status(order_id)
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresCommerceGateway(session).load_order(
                CustomerId(str(customer_id)), OrderId(order_id)
            )

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_orders_of_an_unknown_order_status_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    customer_id, order_id = await order_with_shipment_and_refund(builder)

    async with session_without_check(
        worker_database, DROP_ORDER_STATUS_CHECK, unknown_order_status(order_id)
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresCommerceGateway(session).load_orders(
                CustomerId(str(customer_id)), position=0, limit=OTHER_ORDER_LIMIT
            )

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_addressed_orders_of_an_unknown_order_status_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    customer_id, order_id = await order_with_shipment_and_refund(builder)

    async with session_without_check(
        worker_database, DROP_ORDER_STATUS_CHECK, unknown_order_status(order_id)
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresCustomerRecords(session).load_addressed_orders(
                CustomerId(str(customer_id)), OrderId(order_id), OTHER_ORDER_LIMIT
            )

    assert isinstance(caught.value.__cause__, ValueError)

"""Adapter tests of `PostgresCustomerRecords` against PostgreSQL 17 (TEST-01).

Every read filters by the customer, so a ticket never reaches another customer's records
(SEC-17). The workspace shows the ticket's order and at most `OTHER_ORDERS_LIMIT` other orders
of the customer, newest first by `placed_at`, then by order ID by code point (`backend`
contract 1.2.0, `TicketWorkspace.other_orders`, `maxItems`).
"""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce import AddressedOrder, CustomerContact, OrderId, OrderReferences
from supportiq_backend.commerce.adapters.customer_records import PostgresCustomerRecords
from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.tickets.domain import OTHER_ORDERS_LIMIT
from tests.integration.builders import DatabaseBuilder, LineSpec, OrderSpec, ShipmentSpec
from tests.integration.workflow.workflow_rows import insert_orders
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

DISPLAY_NAME = "Lan Tran"
OTHER_DISPLAY_NAME = "Minh Pham"
UNKNOWN_CUSTOMER_ID = CustomerId("ffffffff-0000-4000-8000-000000000000")
UNKNOWN_ORDER_IDS = [OrderId("ORD-99999"), OrderId("ORD-\x00")]
OLDEST = FAKE_CLOCK_START
NEWEST = FAKE_CLOCK_START + timedelta(days=2)
# More other orders than the workspace shows, each one day newer than the previous one.
NEWER_TIMES = tuple(
    FAKE_CLOCK_START + timedelta(days=day) for day in range(1, OTHER_ORDERS_LIMIT + 3)
)
CONTACT = "SELECT ARRAY[display_name, email, phone] FROM customers"
REFERENCES = """
    SELECT ARRAY[orders.order_id, orders.transaction_id, orders.shipping_address,
        shipments.tracking_code]
    FROM orders LEFT JOIN shipments USING (order_id) WHERE orders.order_id = :order_id
"""
SHIPPING_ADDRESS = "SELECT shipping_address FROM orders WHERE order_id = :order_id"


async def load_contact(engine: AsyncEngine, customer_id: CustomerId) -> CustomerContact | None:
    async with create_session_factory(engine)() as session:
        return await PostgresCustomerRecords(session).load_contact(customer_id)


async def load_order_references(
    engine: AsyncEngine, customer_id: UUID, order_id: str
) -> OrderReferences | None:
    async with create_session_factory(engine)() as session:
        return await PostgresCustomerRecords(session).load_order_references(
            CustomerId(str(customer_id)), OrderId(order_id)
        )


async def load_display_names(
    engine: AsyncEngine, customer_ids: frozenset[CustomerId]
) -> Mapping[CustomerId, str]:
    async with create_session_factory(engine)() as session:
        return await PostgresCustomerRecords(session).load_display_names(customer_ids)


async def load_addressed_orders(
    engine: AsyncEngine, customer_id: UUID, ticket_order_id: str | None
) -> tuple[AddressedOrder, ...]:
    async with create_session_factory(engine)() as session:
        return await PostgresCustomerRecords(session).load_addressed_orders(
            CustomerId(str(customer_id)),
            None if ticket_order_id is None else OrderId(ticket_order_id),
            OTHER_ORDERS_LIMIT,
        )


def order_ids(orders: tuple[AddressedOrder, ...]) -> tuple[str, ...]:
    return tuple(item.order.order_id for item in orders)


def newest_first(order_ids_oldest_first: tuple[str, ...]) -> tuple[str, ...]:
    return order_ids_oldest_first[::-1][:OTHER_ORDERS_LIMIT]


def to_references(references: OrderReferences) -> list[str | None]:
    return [
        references.order_id,
        references.transaction_id,
        references.shipping_address,
        references.tracking_code,
    ]


async def test_load_contact_returns_the_personal_values_of_the_customer(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer(display_name=DISPLAY_NAME)

    contact = await load_contact(app_engine, CustomerId(str(customer_id)))

    assert contact is not None
    assert [contact.display_name, contact.email, contact.phone] == await builder.scalar(CONTACT)


async def test_load_contact_of_an_unknown_customer_is_none(app_engine: AsyncEngine) -> None:
    assert await load_contact(app_engine, UNKNOWN_CUSTOMER_ID) is None


async def test_load_order_references_returns_the_identifying_values_of_the_order(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    product_id = await builder.product()
    spec = OrderSpec(lines=(LineSpec(product_id),), shipment=ShipmentSpec())
    order_id = await builder.order(customer_id, spec)

    references = await load_order_references(app_engine, customer_id, order_id)

    assert references is not None
    assert references.tracking_code is not None
    assert to_references(references) == await builder.scalar(REFERENCES, order_id=order_id)


async def test_load_order_references_of_an_order_without_a_shipment_has_no_tracking_code(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)

    references = await load_order_references(app_engine, customer_id, order_id)

    assert references is not None
    assert references.tracking_code is None


async def test_load_order_references_of_another_customers_order_is_none(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    other_order_id = await builder.order_of_one_product(await builder.customer())

    assert await load_order_references(app_engine, customer_id, other_order_id) is None


@pytest.mark.parametrize("order_id", UNKNOWN_ORDER_IDS)
async def test_load_order_references_of_an_unknown_order_is_none(
    app_engine: AsyncEngine, builder: DatabaseBuilder, order_id: OrderId
) -> None:
    customer_id = await builder.customer()

    assert await load_order_references(app_engine, customer_id, order_id) is None


async def test_load_display_names_returns_the_name_of_each_known_customer(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = CustomerId(str(await builder.customer(display_name=DISPLAY_NAME)))
    other_id = CustomerId(str(await builder.customer(display_name=OTHER_DISPLAY_NAME)))

    names = await load_display_names(
        app_engine, frozenset({customer_id, other_id, UNKNOWN_CUSTOMER_ID})
    )

    assert names == {customer_id: DISPLAY_NAME, other_id: OTHER_DISPLAY_NAME}


async def test_load_display_names_of_no_customer_is_empty(app_engine: AsyncEngine) -> None:
    assert await load_display_names(app_engine, frozenset()) == {}


async def test_load_addressed_orders_returns_the_tickets_order_then_the_newest_others(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    oldest, ticket_order, newest = await insert_orders(
        builder, customer_id, (OLDEST, OLDEST + timedelta(days=1), NEWEST)
    )

    orders = await load_addressed_orders(app_engine, customer_id, ticket_order)

    assert order_ids(orders) == (ticket_order, newest, oldest)


async def test_load_addressed_orders_returns_each_order_with_its_shipping_address(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)

    (order,) = await load_addressed_orders(app_engine, customer_id, order_id)

    assert order.shipping_address == await builder.scalar(SHIPPING_ADDRESS, order_id=order_id)


async def test_load_addressed_orders_keeps_the_oldest_tickets_order_and_the_limit_of_others(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    (ticket_order,) = await insert_orders(builder, customer_id, (OLDEST,))
    others = await insert_orders(builder, customer_id, NEWER_TIMES)

    orders = await load_addressed_orders(app_engine, customer_id, ticket_order)

    assert order_ids(orders) == (ticket_order, *newest_first(others))


async def test_load_addressed_orders_without_a_tickets_order_returns_the_limit_of_others(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    others = await insert_orders(builder, customer_id, NEWER_TIMES)

    orders = await load_addressed_orders(app_engine, customer_id, None)

    assert order_ids(orders) == newest_first(others)


async def test_load_addressed_orders_orders_others_of_one_moment_by_order_id(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    (ticket_order,) = await insert_orders(builder, customer_id, (NEWEST,))
    lower, higher = await insert_orders(builder, customer_id, (OLDEST, OLDEST))

    orders = await load_addressed_orders(app_engine, customer_id, ticket_order)

    assert order_ids(orders) == (ticket_order, lower, higher)


async def test_load_addressed_orders_leaves_out_the_orders_of_other_customers(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    (own_order,) = await insert_orders(builder, customer_id, (OLDEST,))
    other_customers_order = await builder.order_of_one_product(await builder.customer())

    orders = await load_addressed_orders(app_engine, customer_id, other_customers_order)

    assert order_ids(orders) == (own_order,)

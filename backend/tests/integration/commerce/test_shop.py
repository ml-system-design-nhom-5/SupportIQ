"""The shop's read operations over HTTP against PostgreSQL (ADR-0013, SEC-17)."""

from datetime import timedelta
from http import HTTPStatus
from uuid import UUID

import pytest

from supportiq_backend.platform.web import encode_cursor
from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import (
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    RefundSpec,
    ShipmentSpec,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

PRODUCTS = "/v1/shop/products"
ORDERS = "/v1/shop/orders"
DELIVERED_AT = FAKE_CLOCK_START + timedelta(days=2)


@pytest.fixture
async def customer(builder: DatabaseBuilder) -> tuple[UUID, dict[str, str]]:
    account_id, customer_id = await builder.customer_account()
    token = await builder.session(account_id, "customer")
    return customer_id, session_headers(token)


@pytest.fixture
def headers(customer: tuple[UUID, dict[str, str]]) -> dict[str, str]:
    return customer[1]


@pytest.fixture
def customer_id(customer: tuple[UUID, dict[str, str]]) -> UUID:
    return customer[0]


async def test_catalog_lists_products_with_their_price(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    product_id = await builder.product(name="Desk lamp", price_minor=2_450)

    response = await backend.client.get(PRODUCTS, headers=headers)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "items": [
            {
                "product_id": product_id,
                "name": "Desk lamp",
                "description": "The description of Desk lamp.",
                "category": "Home office",
                "price": {"amount_minor": 2_450, "currency": "USD"},
            }
        ]
    }


async def test_empty_catalog_returns_an_empty_page(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(PRODUCTS, headers=headers)

    assert response.json() == {"items": []}


async def test_catalog_is_ordered_by_code_point_and_follows_the_cursor(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    await builder.product(name="apple")
    await builder.product(name="Zebra")
    await builder.product(name="Đèn")

    first = await backend.client.get(PRODUCTS, params={"limit": "2"}, headers=headers)
    second = await backend.client.get(
        PRODUCTS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["name"] for item in first.json()["items"]] == ["Zebra", "apple"]
    assert [item["name"] for item in second.json()["items"]] == ["Đèn"]
    assert "next_cursor" not in second.json()


async def test_products_with_one_name_are_ordered_by_product_id_across_pages(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    await builder.product(name="Same", product_id="PRD-2")
    await builder.product(name="Same", product_id="PRD-1")
    await builder.product(name="Same", product_id="PRD-3")

    first = await backend.client.get(PRODUCTS, params={"limit": "2"}, headers=headers)
    second = await backend.client.get(
        PRODUCTS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["product_id"] for item in first.json()["items"]] == ["PRD-1", "PRD-2"]
    assert [item["product_id"] for item in second.json()["items"]] == ["PRD-3"]


async def test_one_product_is_returned(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    product_id = await builder.product(name="Mug")

    response = await backend.client.get(f"{PRODUCTS}/{product_id}", headers=headers)

    assert response.json()["name"] == "Mug"


@pytest.mark.parametrize("product_id", ["PRD-9999", "%00", "x%00y"])
async def test_unknown_product_returns_404(
    backend: RunningBackend, headers: dict[str, str], product_id: str
) -> None:
    response = await backend.client.get(f"{PRODUCTS}/{product_id}", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_order_view_holds_lines_shipment_and_refund(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    product_id = await builder.product(name="Mug")
    order_id = await builder.order(
        customer_id,
        OrderSpec(
            lines=(LineSpec(product_id, 2),),
            order_status="delivered",
            placed_at=FAKE_CLOCK_START,
            shipment=ShipmentSpec("delivered", delivered_at=DELIVERED_AT),
            refund=RefundSpec("under_review", 1_000),
        ),
    )

    response = await backend.client.get(f"{ORDERS}/{order_id}", headers=headers)
    body = response.json()

    assert body["order_status"] == "delivered"
    assert body["placed_at"] == "2026-11-05T09:00:00Z"
    assert body["lines"] == [{"product_id": product_id, "product_name": "Mug", "quantity": 2}]
    assert body["shipment"] == {
        "shipment_status": "delivered",
        "delivered_at": "2026-11-07T09:00:00Z",
    }
    assert body["refund"]["refund_status"] == "under_review"
    assert body["refund"]["refund_amount"] == {"amount_minor": 1_000, "currency": "USD"}


async def test_order_without_a_shipment_record_is_not_shipped_and_has_no_refund(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    order_id = await builder.order_of_one_product(customer_id)

    response = await backend.client.get(f"{ORDERS}/{order_id}", headers=headers)

    assert response.json()["shipment"] == {"shipment_status": "not_shipped"}
    assert "refund" not in response.json()


async def test_order_view_has_no_shipping_address_and_no_transaction_id(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    order_id = await builder.order_of_one_product(customer_id)

    response = await backend.client.get(f"{ORDERS}/{order_id}", headers=headers)

    assert "shipping_address" not in response.json()
    assert "transaction_id" not in response.json()
    assert "Example Street" not in response.text
    assert "TXN-" not in response.text


async def test_order_of_another_customer_and_an_unknown_id_return_the_same_404(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str]
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)

    other = await backend.client.get(f"{ORDERS}/{other_order}", headers=headers)
    unknown = await backend.client.get(f"{ORDERS}/ORD-99999", headers=headers)

    assert other.status_code == unknown.status_code == HTTPStatus.NOT_FOUND
    assert other.json()["detail"] == unknown.json()["detail"]
    assert other.json()["title"] == unknown.json()["title"]


async def test_order_id_with_a_nul_character_is_an_unknown_order(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(f"{ORDERS}/ORD%00", headers=headers)

    assert response.status_code == HTTPStatus.NOT_FOUND


async def test_order_list_holds_only_the_orders_of_the_caller_on_every_page(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    other_customer = await builder.customer(display_name="Other Customer")
    other_order = await builder.order_of_one_product(other_customer)
    first_order = await builder.order_of_one_product(customer_id)
    second_order = await builder.order_of_one_product(customer_id)

    first = await backend.client.get(ORDERS, params={"limit": "1"}, headers=headers)
    second = await backend.client.get(
        ORDERS, params={"cursor": first.json()["next_cursor"]}, headers=headers
    )

    assert [item["order_id"] for item in first.json()["items"]] == [second_order]
    assert [item["order_id"] for item in second.json()["items"]] == [first_order]
    assert other_order not in first.text + second.text


async def test_orders_are_listed_newest_first_then_by_order_id(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    lines = (LineSpec(await builder.product()),)
    older = await builder.order(
        customer_id,
        OrderSpec(lines=lines, placed_at=FAKE_CLOCK_START - timedelta(days=1)),
    )
    first_of_tie = await builder.order(
        customer_id, OrderSpec(lines=lines, placed_at=FAKE_CLOCK_START)
    )
    second_of_tie = await builder.order(
        customer_id, OrderSpec(lines=lines, placed_at=FAKE_CLOCK_START)
    )

    response = await backend.client.get(ORDERS, headers=headers)

    assert [item["order_id"] for item in response.json()["items"]] == [
        first_of_tie,
        second_of_tie,
        older,
    ]


async def test_order_cursor_holds_a_position_and_no_order_id(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    customer_id: UUID,
) -> None:
    await builder.order_of_one_product(customer_id)
    await builder.order_of_one_product(customer_id)

    response = await backend.client.get(ORDERS, params={"limit": "1"}, headers=headers)

    assert response.json()["next_cursor"] == encode_cursor("listShopOrders", {"position": 1})


async def test_customer_without_orders_gets_an_empty_page(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    response = await backend.client.get(ORDERS, headers=headers)

    assert response.json() == {"items": []}


@pytest.mark.parametrize(
    ("path", "cursor"),
    [
        (PRODUCTS, ""),
        (PRODUCTS, "garbage!"),
        (PRODUCTS, encode_cursor("listShopOrders", {"position": 1})),
        (PRODUCTS, encode_cursor("listShopProducts", {"name": "a\x00b", "product_id": "PRD-1"})),
        (ORDERS, ""),
        (ORDERS, encode_cursor("listShopProducts", {"name": "a", "product_id": "PRD-1"})),
        (ORDERS, encode_cursor("listShopOrders", {"position": -1})),
        (ORDERS, encode_cursor("listShopOrders", {"position": 2**63})),
    ],
)
async def test_malformed_or_foreign_cursor_returns_422(
    backend: RunningBackend, headers: dict[str, str], path: str, cursor: str
) -> None:
    response = await backend.client.get(path, params={"cursor": cursor}, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize("path", [PRODUCTS, ORDERS])
@pytest.mark.parametrize("limit", ["0", "101", "x"])
async def test_limit_outside_the_range_returns_422(
    backend: RunningBackend, headers: dict[str, str], path: str, limit: str
) -> None:
    response = await backend.client.get(path, params={"limit": limit}, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_position_past_the_last_order_returns_an_empty_page(
    backend: RunningBackend, headers: dict[str, str]
) -> None:
    cursor = encode_cursor("listShopOrders", {"position": 2**63 - 1})

    response = await backend.client.get(ORDERS, params={"cursor": cursor}, headers=headers)

    assert response.json() == {"items": []}

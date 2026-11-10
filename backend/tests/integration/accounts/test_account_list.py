"""Listing the internal accounts over HTTP against PostgreSQL (SEC-41, CON-14)."""

from http import HTTPStatus

import pytest

from supportiq_backend.platform.web import encode_cursor
from tests.integration.accounts.admin_requests import (
    UNKNOWN_ACCOUNT,
)
from tests.integration.application import (
    RunningBackend,
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder

pytestmark = pytest.mark.anyio


async def test_customer_gets_403_on_the_list(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    account_id, _ = await builder.customer_account()
    token = await builder.session(account_id, "customer")

    response = await backend.client.get(
        "/v1/admin/accounts?cursor=malformed", headers=session_headers(token)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


async def test_list_holds_only_internal_accounts_with_only_the_contract_fields(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    await builder.customer_account(display_name="A customer who must not appear")

    response = await backend.client.get("/v1/admin/accounts", headers=session_headers(admin_token))

    (item,) = response.json()["items"]
    assert response.status_code == HTTPStatus.OK
    assert set(item) == {"account_id", "display_name", "role", "is_active"}
    assert "next_cursor" not in response.json()


async def test_list_follows_the_cursor_in_display_name_order_by_code_point(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    await builder.account(AccountSpec("staff", display_name="Zed"))
    await builder.account(AccountSpec("staff", display_name="an"))
    await builder.account(AccountSpec("manager", display_name="Đào"))
    admin_id = await builder.account(AccountSpec("admin", display_name="Binh"))
    token = await builder.session(admin_id, "admin")
    headers = session_headers(token)

    first = await backend.client.get("/v1/admin/accounts?limit=2", headers=headers)
    second = await backend.client.get(
        "/v1/admin/accounts",
        params={"limit": "2", "cursor": first.json()["next_cursor"]},
        headers=headers,
    )

    assert [item["display_name"] for item in first.json()["items"]] == ["Binh", "Zed"]
    assert [item["display_name"] for item in second.json()["items"]] == ["an", "Đào"]
    assert "next_cursor" not in second.json()


async def test_accounts_with_one_display_name_are_ordered_by_account_id(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    await builder.account(AccountSpec("staff", display_name="Same"))
    second = await builder.account(AccountSpec("staff", display_name="Same"))
    admin_id = await builder.account(AccountSpec("admin", display_name="Same"))
    token = await builder.session(admin_id, "admin")
    headers = session_headers(token)

    first_page = await backend.client.get("/v1/admin/accounts?limit=1", headers=headers)
    second_page = await backend.client.get(
        "/v1/admin/accounts",
        params={"limit": "1", "cursor": first_page.json()["next_cursor"]},
        headers=headers,
    )

    assert second_page.json()["items"][0]["account_id"] == str(second)


async def test_cursor_holds_no_confidential_value(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    await builder.account(AccountSpec("staff", display_name="Secret Name"))
    await builder.account(AccountSpec("staff", display_name="Tu Name"))

    response = await backend.client.get(
        "/v1/admin/accounts?limit=1", headers=session_headers(admin_token)
    )

    fields = encode_cursor(
        "listAdminAccounts", {"account_id": response.json()["items"][0]["account_id"]}
    )
    assert response.json()["next_cursor"] == fields


@pytest.mark.parametrize(
    "cursor",
    [
        "",
        "not-a-cursor!",
        encode_cursor("listShopOrders", {"position": 1}),
        encode_cursor("listAdminAccounts", {"account_id": UNKNOWN_ACCOUNT}),
        encode_cursor("listAdminAccounts", {"account_id": "not-a-uuid"}),
    ],
)
async def test_malformed_or_foreign_cursor_returns_422(
    backend: RunningBackend, admin_token: str, cursor: str
) -> None:
    response = await backend.client.get(
        "/v1/admin/accounts", params={"cursor": cursor}, headers=session_headers(admin_token)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == "The parameter cursor is not a cursor of this operation."


async def test_cursor_that_names_a_customer_account_returns_422(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    customer_account, _ = await builder.customer_account()
    cursor = encode_cursor("listAdminAccounts", {"account_id": str(customer_account)})

    response = await backend.client.get(
        "/v1/admin/accounts", params={"cursor": cursor}, headers=session_headers(admin_token)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


@pytest.mark.parametrize("limit", ["0", "101", "abc", ""])
async def test_limit_outside_the_range_returns_422(
    backend: RunningBackend, admin_token: str, limit: str
) -> None:
    response = await backend.client.get(
        "/v1/admin/accounts", params={"limit": limit}, headers=session_headers(admin_token)
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT

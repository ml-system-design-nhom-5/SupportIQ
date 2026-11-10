"""Guardrail: no admin operation returns or changes a customer account (TEST-26, SEC-41)."""

from http import HTTPStatus

import pytest

from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder

pytestmark = pytest.mark.anyio

CUSTOMER_NAME = "Customer Of The Shop"
KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"


@pytest.fixture
async def admin_headers(builder: DatabaseBuilder) -> dict[str, str]:
    admin = await builder.account(AccountSpec("admin"))
    return session_headers(await builder.session(admin, "admin"))


async def test_account_list_never_holds_a_customer_on_any_page(
    backend: RunningBackend, builder: DatabaseBuilder, admin_headers: dict[str, str]
) -> None:
    customer_account, _ = await builder.customer_account(display_name=CUSTOMER_NAME)
    await builder.account(AccountSpec("staff"))

    first = await backend.client.get(
        "/v1/admin/accounts", params={"limit": "1"}, headers=admin_headers
    )
    second = await backend.client.get(
        "/v1/admin/accounts",
        params={"cursor": first.json()["next_cursor"]},
        headers=admin_headers,
    )

    assert CUSTOMER_NAME not in first.text + second.text
    assert str(customer_account) not in first.text + second.text


async def test_changes_of_a_customer_account_return_404_and_change_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, admin_headers: dict[str, str]
) -> None:
    customer_account, _ = await builder.customer_account()
    token = await builder.session(customer_account, "customer")

    role = await backend.client.post(
        f"/v1/admin/accounts/{customer_account}/role-changes",
        json={"role": "manager"},
        headers={**admin_headers, "Idempotency-Key": KEY},
    )
    status = await backend.client.post(
        f"/v1/admin/accounts/{customer_account}/status-changes",
        json={"is_active": False},
        headers={**admin_headers, "Idempotency-Key": OTHER_KEY},
    )
    session = await backend.client.get("/v1/sessions/current", headers=session_headers(token))

    assert role.status_code == status.status_code == HTTPStatus.NOT_FOUND
    assert session.json()["role"] == "customer"
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0
    assert (
        await builder.scalar(
            "SELECT is_active FROM accounts WHERE account_id = :account_id",
            account_id=customer_account,
        )
        is True
    )

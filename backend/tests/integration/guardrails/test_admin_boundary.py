"""Guardrail: no admin operation returns or changes a customer account (TEST-26, SEC-41).

The versions in use hold versions only: no ticket, message, order, or customer.
"""

from http import HTTPStatus

import pytest

from tests.integration.ai_service_doubles import FakeAiService, serve_examples
from tests.integration.application import (
    RunningBackend,
    build_settings,
    running_client,
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

CUSTOMER_NAME = "Customer Of The Shop"
KEY = "00000000-0000-4000-8000-000000000001"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
RESET_PASSWORD = "reset-test-password"
CUSTOMER_MESSAGE = "My parcel to 12 Hang Bac street never arrived."


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


async def test_password_reset_of_a_customer_account_returns_404_and_changes_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, admin_headers: dict[str, str]
) -> None:
    customer_account, _ = await builder.customer_account()
    token = await builder.session(customer_account, "customer")
    password_hash = await builder.scalar(
        "SELECT password_hash FROM accounts WHERE account_id = :account_id",
        account_id=customer_account,
    )

    reset = await backend.client.post(
        f"/v1/admin/accounts/{customer_account}/password-resets",
        json={"password": RESET_PASSWORD, "is_signed_out_everywhere": True},
        headers={**admin_headers, "Idempotency-Key": KEY},
    )
    session = await backend.client.get("/v1/sessions/current", headers=session_headers(token))

    assert reset.status_code == HTTPStatus.NOT_FOUND
    assert session.status_code == HTTPStatus.OK
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0
    assert (
        await builder.scalar(
            "SELECT password_hash FROM accounts WHERE account_id = :account_id",
            account_id=customer_account,
        )
        == password_hash
    )


async def test_the_versions_in_use_hold_versions_only(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, admin_headers: dict[str, str]
) -> None:
    _, customer_id = await builder.customer_account(display_name=CUSTOMER_NAME)
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id, TicketSpec(message=CUSTOMER_MESSAGE))
    ai_service = FakeAiService(serve_examples)

    async with running_client(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        ai_service=ai_service,
    ) as client:
        response = await client.get("/v1/admin/versions", headers=admin_headers)

    customer_values = (CUSTOMER_NAME, CUSTOMER_MESSAGE, ticket_id, order_id, str(customer_id))
    assert response.status_code == HTTPStatus.OK
    assert set(response.json()) == {"backend_version", "ai_service_status", "ai_service_versions"}
    assert ai_service.paths() == ["/v1/asset-versions"]
    assert [value for value in customer_values if value in response.text] == []

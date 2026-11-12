"""Changing an internal account over HTTP against PostgreSQL, as the design's diagram says."""

from http import HTTPStatus
from uuid import UUID

import pytest

from supportiq_backend.platform import EventName
from tests.integration.accounts.admin_requests import (
    KEY,
    OTHER_KEY,
    UNKNOWN_ACCOUNT,
    UPPERCASE_KEY,
    ChangeKind,
    change_path,
    change_role,
    change_status,
)
from tests.integration.application import (
    ORIGIN_HEADERS,
    RunningBackend,
    session_headers,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder

pytestmark = pytest.mark.anyio


async def test_role_change_returns_the_account_after_the_change(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(
        AccountSpec("staff", display_name="Mai Nguyen", login_name="staff-7")
    )

    response = await change_role(backend.client, admin_token, target, "manager")

    assert response.status_code == HTTPStatus.CREATED
    assert response.json() == {
        "account_id": str(target),
        "login_name": "staff-7",
        "display_name": "Mai Nguyen",
        "role": "manager",
        "is_active": True,
    }


async def test_status_change_returns_the_account_after_the_change(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))

    response = await change_status(backend.client, admin_token, target, is_active=False)

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["is_active"] is False


async def test_role_change_deletes_every_session_of_the_account(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))
    target_token = await builder.session(target, "staff")
    await builder.session(target, "staff")

    await change_role(backend.client, admin_token, target, "manager")
    next_request = await backend.client.get(
        "/v1/sessions/current", headers=session_headers(target_token)
    )

    assert next_request.status_code == HTTPStatus.UNAUTHORIZED
    assert (
        await builder.scalar(
            "SELECT count(*) FROM sessions WHERE account_id = :target", target=target
        )
        == 0
    )


async def test_deactivation_deletes_every_session_of_the_account(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))
    await builder.session(target, "staff")

    await change_status(backend.client, admin_token, target, is_active=False)

    assert (
        await builder.scalar(
            "SELECT count(*) FROM sessions WHERE account_id = :target", target=target
        )
        == 0
    )


async def test_each_successful_change_writes_one_audit_entry_with_its_data(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    admin: tuple[UUID, str],
) -> None:
    admin_id, token = admin
    target = await builder.account(AccountSpec("staff"))

    await change_role(backend.client, token, target, "manager")

    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1
    assert await builder.scalar("SELECT event_type FROM audit_log_entries") == (
        "account.role_changed"
    )
    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") == admin_id
    assert await builder.scalar("SELECT data FROM audit_log_entries") == {
        "target_account_id": str(target),
        "old_role": "staff",
        "new_role": "manager",
    }


async def test_audit_entry_carries_the_trace_id_of_the_request(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"

    await backend.client.post(
        change_path(target, "status-changes"),
        json={"is_active": False},
        headers={
            **session_headers(admin_token),
            "Idempotency-Key": KEY,
            "traceparent": f"00-{trace_id}-00f067aa0ba902b7-01",
        },
    )

    assert await builder.scalar("SELECT trace_id FROM audit_log_entries") == trace_id


async def test_repeat_returns_the_same_body_and_changes_nothing_more(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))

    first = await change_role(backend.client, admin_token, target, "manager")
    await builder.session(target, "manager")
    repeated = await change_role(backend.client, admin_token, target, "manager")

    assert repeated.status_code == HTTPStatus.CREATED
    assert repeated.content == first.content
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 1
    assert await builder.scalar("SELECT count(*) FROM sessions WHERE role = 'manager'") == 1


async def test_same_key_with_another_body_returns_409(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))
    await change_role(backend.client, admin_token, target, "manager")

    response = await change_role(backend.client, admin_token, target, "staff")

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["type"] == "urn:supportiq:problem:idempotency-key-reused"


async def test_same_key_on_another_account_returns_409(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    first_target = await builder.account(AccountSpec("staff"))
    second_target = await builder.account(AccountSpec("staff"))
    await change_role(backend.client, admin_token, first_target, "manager")

    response = await change_role(backend.client, admin_token, second_target, "manager")

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["type"] == "urn:supportiq:problem:idempotency-key-reused"


async def test_refused_request_is_not_remembered_so_the_key_runs_again(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))
    await builder.account(AccountSpec("manager"))
    refused = await change_role(backend.client, admin_token, target, "staff")

    allowed = await change_role(backend.client, admin_token, target, "manager")

    assert refused.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert allowed.status_code == HTTPStatus.CREATED


@pytest.mark.parametrize(
    ("kind", "body"),
    [("role-changes", {"role": "manager"}), ("status-changes", {"is_active": False})],
)
async def test_customer_and_unknown_targets_return_the_same_404(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    admin_token: str,
    kind: ChangeKind,
    body: dict[str, object],
) -> None:
    customer_account, _ = await builder.customer_account()
    headers = {**session_headers(admin_token), "Idempotency-Key": KEY}

    customer = await backend.client.post(
        change_path(customer_account, kind), json=body, headers=headers
    )
    unknown = await backend.client.post(
        change_path(UNKNOWN_ACCOUNT, kind), json=body, headers=headers
    )
    not_a_uuid = await backend.client.post(change_path("x", kind), json=body, headers=headers)

    assert customer.status_code == HTTPStatus.NOT_FOUND
    assert unknown.status_code == HTTPStatus.NOT_FOUND
    assert not_a_uuid.status_code == HTTPStatus.NOT_FOUND
    assert customer.json()["detail"] == unknown.json()["detail"] == not_a_uuid.json()["detail"]
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0


async def test_own_account_is_refused_for_both_changes(
    backend: RunningBackend, admin: tuple[UUID, str]
) -> None:
    admin_id, token = admin

    role = await change_role(backend.client, token, admin_id, "manager", KEY)
    status = await change_status(backend.client, token, admin_id, is_active=False, key=OTHER_KEY)

    assert role.json()["violated_rule"] == "own_account"
    assert status.json()["violated_rule"] == "own_account"
    assert role.status_code == HTTPStatus.UNPROCESSABLE_CONTENT


async def test_admin_account_role_is_refused_and_its_status_is_allowed(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    other_admin = await builder.account(AccountSpec("admin"))

    role = await change_role(backend.client, admin_token, other_admin, "manager", KEY)
    status = await change_status(
        backend.client, admin_token, other_admin, is_active=False, key=OTHER_KEY
    )

    assert role.json()["violated_rule"] == "admin_role_unchangeable"
    assert status.status_code == HTTPStatus.CREATED


async def test_unchanged_values_are_refused(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    target = await builder.account(AccountSpec("staff"))

    role = await change_role(backend.client, admin_token, target, "staff", KEY)
    status = await change_status(backend.client, admin_token, target, is_active=True, key=OTHER_KEY)

    assert role.json()["violated_rule"] == "role_unchanged"
    assert status.json()["violated_rule"] == "status_unchanged"


async def test_last_active_manager_cannot_be_demoted_or_deactivated(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str
) -> None:
    manager = await builder.account(AccountSpec("manager"))
    await builder.account(AccountSpec("manager", is_active=False))

    role = await change_role(backend.client, admin_token, manager, "staff", KEY)
    status = await change_status(
        backend.client, admin_token, manager, is_active=False, key=OTHER_KEY
    )

    assert role.json()["violated_rule"] == "last_active_manager"
    assert status.json()["violated_rule"] == "last_active_manager"


@pytest.mark.parametrize(
    "body",
    [b"{}", b'{"role": "admin"}', b'{"role": "customer"}', b'{"role": "manager", "x": 1}', b"{"],
)
async def test_request_that_fails_validation_has_no_violated_rule(
    backend: RunningBackend, builder: DatabaseBuilder, admin_token: str, body: bytes
) -> None:
    target = await builder.account(AccountSpec("staff"))

    response = await backend.client.post(
        change_path(target, "role-changes"),
        content=body,
        headers={**session_headers(admin_token), "Idempotency-Key": KEY},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "violated_rule" not in response.json()


@pytest.mark.parametrize(
    "key_headers",
    [{}, {"Idempotency-Key": "not-a-key"}, {"Idempotency-Key": UPPERCASE_KEY}],
)
async def test_missing_or_malformed_key_returns_422_without_violated_rule(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    admin_token: str,
    key_headers: dict[str, str],
) -> None:
    target = await builder.account(AccountSpec("staff"))
    headers = session_headers(admin_token) | key_headers

    response = await backend.client.post(
        change_path(target, "role-changes"), json={"role": "manager"}, headers=headers
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert "violated_rule" not in response.json()


@pytest.mark.parametrize("role", ["staff", "manager"])
async def test_another_role_gets_403_whatever_it_sent(
    backend: RunningBackend, builder: DatabaseBuilder, role: str
) -> None:
    caller = await builder.account(AccountSpec(role))
    token = await builder.session(caller, role)

    response = await backend.client.post(
        change_path(UNKNOWN_ACCOUNT, "role-changes"),
        content=b"{not json",
        headers=session_headers(token),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert EventName.PERMISSION_DENIED in backend.events.names()


async def test_change_without_a_session_gets_401_and_without_an_origin_gets_403(
    backend: RunningBackend,
) -> None:
    path = change_path(UNKNOWN_ACCOUNT, "role-changes")

    no_session = await backend.client.post(path, json={"role": "manager"}, headers=ORIGIN_HEADERS)
    no_origin = await backend.client.post(path, json={"role": "manager"})

    assert no_session.status_code == HTTPStatus.UNAUTHORIZED
    assert no_origin.status_code == HTTPStatus.FORBIDDEN

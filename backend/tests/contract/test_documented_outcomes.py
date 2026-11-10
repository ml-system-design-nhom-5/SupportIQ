"""One test for each status that the contract documents on each operation (CON-27).

The table `OUTCOMES` lists them, and a test compares the table with the contract, so a status
added to the contract fails here until it has its test. `500` comes from a failure inside the
request, through the real exception handler, and `503` from a replica with no database.
"""

from collections.abc import Callable, MutableSequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from enum import StrEnum
from http import HTTPStatus
from typing import assert_never

import httpx
import pytest
from schemathesis import BaseSchema
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from supportiq_backend.accounts import PasswordHash
from supportiq_backend.composition_root import create_app
from tests.contract.calls import (
    KEY,
    ORDERS,
    Call,
    World,
    build_world,
    send,
    valid_calls,
)
from tests.contract.documented import list_operations, validate_response
from tests.integration.application import (
    RunningBackend,
    build_settings,
    running_app,
    running_client,
)
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

UNREACHABLE_URL = "postgresql+asyncpg://supportiq_app:x@127.0.0.1:1/supportiq"
OTHER_KEY = "00000000-0000-4000-8000-000000000002"
UNKNOWN_ACCOUNT = "99999999-9999-4999-8999-999999999999"
PROBLEM_MEDIA_TYPE = "application/problem+json"
FIRST_ERROR_STATUS = 400
TRACE_ID_LENGTH = 32


class Condition(StrEnum):
    """The state of the replica that answers."""

    HEALTHY = "healthy"
    REQUEST_FAILS = "request-fails"
    NO_DATABASE = "no-database"


type ChangeCall = Callable[[Call, World], Call]


@dataclass(frozen=True, slots=True)
class Outcome:
    """One documented status of one operation.

    Attributes:
        operation_id: The operation.
        status: The status.
        condition: The state of the replica.
        change: Turns the valid request into the one that gets this status.
        label: What makes this outcome differ from others with the same status.
    """

    operation_id: str
    status: HTTPStatus
    condition: Condition = Condition.HEALTHY
    change: ChangeCall = lambda call, _world: call
    label: str = ""

    def __str__(self) -> str:
        """Name the test after the operation and the status."""
        return f"{self.operation_id}-{self.status.value}{self.label}"


class FailingMiddleware:
    """Fail inside the request, where the exception handler of the application catches it."""

    def __init__(self, app: ASGIApp) -> None:
        """Keep the application, which is never called.

        Args:
            app: The inner application.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Fail on every request, and let the lifespan pass.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] == "http":
            raise RuntimeError
        await self.app(scope, receive, send)


def without_session(call: Call, _world: World) -> Call:
    return replace(call, role=None)


def without_origin(call: Call, _world: World) -> Call:
    return replace(call, has_origin=False)


def as_admin(call: Call, _world: World) -> Call:
    return replace(call, role="admin")


def as_customer(call: Call, _world: World) -> Call:
    return replace(call, role="customer")


def with_invalid_body(call: Call, _world: World) -> Call:
    return replace(call, body={"unknown": True})


def with_invalid_limit(call: Call, _world: World) -> Call:
    return replace(call, params={"limit": "0"})


def with_wrong_password(call: Call, _world: World) -> Call:
    return replace(call, body={"login_name": "staff-contract", "password": "wrong-password"})


def with_unknown_order(call: Call, _world: World) -> Call:
    return replace(call, body={"order_id": "ORD-99999", "message": "Hi"})


def with_unknown_order_filter(call: Call, _world: World) -> Call:
    return replace(call, params={"order_id": "ORD-99999"})


def with_unknown_path_id(call: Call, _world: World) -> Call:
    return replace(call, path=call.path.rsplit("/", 1)[0] + "/UNKNOWN-1")


def with_unknown_target(call: Call, world: World) -> Call:
    return replace(call, path=call.path.replace(str(world.target_account_id), UNKNOWN_ACCOUNT))


def with_unchanged_role(call: Call, _world: World) -> Call:
    return replace(call, body={"role": "staff"})


def with_unchanged_status(call: Call, _world: World) -> Call:
    return replace(call, body={"is_active": True})


def with_reused_key(new_body: object) -> ChangeCall:
    def change(call: Call, _world: World) -> Call:
        return replace(call, body=new_body, prior=call)

    return change


SHOP_OPERATIONS = (
    "listShopProducts",
    "getShopProduct",
    "listShopOrders",
    "getShopOrder",
    "listShopTickets",
    "createShopTicket",
    "getShopTicket",
)
ADMIN_OPERATIONS = ("listAdminAccounts", "changeAccountRole", "changeAccountStatus")
SESSION_OPERATIONS = ("getCurrentSession", "deleteCurrentSession")
HEALTH_OPERATIONS = ("checkLiveness", "checkReadiness")
OPERATIONS_WITH_A_SESSION = (*SESSION_OPERATIONS, *SHOP_OPERATIONS, *ADMIN_OPERATIONS)
ALL_OPERATIONS = ("createSession", *OPERATIONS_WITH_A_SESSION, *HEALTH_OPERATIONS)
OK_STATUSES = {
    "createSession": HTTPStatus.CREATED,
    "getCurrentSession": HTTPStatus.OK,
    "deleteCurrentSession": HTTPStatus.NO_CONTENT,
    "listShopProducts": HTTPStatus.OK,
    "getShopProduct": HTTPStatus.OK,
    "listShopOrders": HTTPStatus.OK,
    "getShopOrder": HTTPStatus.OK,
    "listShopTickets": HTTPStatus.OK,
    "createShopTicket": HTTPStatus.CREATED,
    "getShopTicket": HTTPStatus.OK,
    "listAdminAccounts": HTTPStatus.OK,
    "changeAccountRole": HTTPStatus.CREATED,
    "changeAccountStatus": HTTPStatus.CREATED,
    "checkLiveness": HTTPStatus.NO_CONTENT,
    "checkReadiness": HTTPStatus.NO_CONTENT,
}
UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_CONTENT
OUTCOMES: tuple[Outcome, ...] = (
    *(Outcome(operation, status) for operation, status in OK_STATUSES.items()),
    *(
        Outcome(operation, HTTPStatus.UNAUTHORIZED, change=without_session)
        for operation in OPERATIONS_WITH_A_SESSION
    ),
    Outcome("createSession", HTTPStatus.UNAUTHORIZED, change=with_wrong_password),
    *(Outcome(operation, HTTPStatus.FORBIDDEN, change=as_admin) for operation in SHOP_OPERATIONS),
    *(
        Outcome(operation, HTTPStatus.FORBIDDEN, change=as_customer)
        for operation in ADMIN_OPERATIONS
    ),
    *(
        Outcome(operation, HTTPStatus.FORBIDDEN, change=without_origin, label="-origin")
        for operation in (
            "createSession",
            "deleteCurrentSession",
            "createShopTicket",
            "changeAccountRole",
            "changeAccountStatus",
        )
    ),
    *(
        Outcome(operation, HTTPStatus.NOT_FOUND, change=with_unknown_path_id)
        for operation in ("getShopProduct", "getShopOrder", "getShopTicket")
    ),
    Outcome("listShopTickets", HTTPStatus.NOT_FOUND, change=with_unknown_order_filter),
    Outcome("createShopTicket", HTTPStatus.NOT_FOUND, change=with_unknown_order),
    Outcome("changeAccountRole", HTTPStatus.NOT_FOUND, change=with_unknown_target),
    Outcome("changeAccountStatus", HTTPStatus.NOT_FOUND, change=with_unknown_target),
    Outcome(
        "createShopTicket",
        HTTPStatus.CONFLICT,
        change=with_reused_key({"order_id": "ORD-99999", "message": "Another message"}),
    ),
    Outcome("changeAccountRole", HTTPStatus.CONFLICT, change=with_reused_key({"role": "staff"})),
    Outcome(
        "changeAccountStatus", HTTPStatus.CONFLICT, change=with_reused_key({"is_active": True})
    ),
    *(
        Outcome(operation, UNPROCESSABLE, change=with_invalid_limit)
        for operation in (
            "listShopProducts",
            "listShopOrders",
            "listShopTickets",
            "listAdminAccounts",
        )
    ),
    *(
        Outcome(operation, UNPROCESSABLE, change=with_invalid_body)
        for operation in (
            "createSession",
            "createShopTicket",
            "changeAccountRole",
            "changeAccountStatus",
        )
    ),
    Outcome("changeAccountRole", UNPROCESSABLE, change=with_unchanged_role, label="-refused"),
    Outcome("changeAccountStatus", UNPROCESSABLE, change=with_unchanged_status, label="-refused"),
    *(
        Outcome(operation, HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS)
        for operation in ALL_OPERATIONS
    ),
    *(
        Outcome(operation, HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_DATABASE)
        for operation in ALL_OPERATIONS
        if operation != "checkLiveness"
    ),
)


def client_under(
    condition: Condition, worker_database: WorkerDatabase
) -> AbstractAsyncContextManager[httpx.AsyncClient]:
    match condition:
        case Condition.REQUEST_FAILS:
            app = create_app(build_settings(worker_database), RecordingEventRecorder(), FakeClock())
            # Starlette runs this list in order, so the last entry is the innermost middleware.
            middleware: MutableSequence[Middleware] = app.user_middleware
            middleware.append(Middleware(FailingMiddleware))
            return running_app(app)
        case Condition.NO_DATABASE:
            settings = build_settings(worker_database, database_url_app=UNREACHABLE_URL)
            return running_client(settings, RecordingEventRecorder(), FakeClock())
        case Condition.HEALTHY:
            return running_client(
                build_settings(worker_database), RecordingEventRecorder(), FakeClock()
            )
        case _:
            assert_never(condition)


@pytest.fixture
async def world(builder: DatabaseBuilder, known_password_hash: PasswordHash) -> World:
    return await build_world(builder, known_password_hash)


def test_the_table_covers_every_status_of_every_operation(contract: BaseSchema) -> None:
    documented = {
        (operation.operation_id, status)
        for operation in list_operations(contract)
        for status in operation.statuses
    }

    assert {(outcome.operation_id, outcome.status.value) for outcome in OUTCOMES} == documented


@pytest.mark.parametrize("outcome", OUTCOMES, ids=str)
async def test_documented_outcome_matches_the_contract(
    contract: BaseSchema,
    worker_database: WorkerDatabase,
    world: World,
    outcome: Outcome,
) -> None:
    call = outcome.change(valid_calls(world)[outcome.operation_id], world)

    async with client_under(outcome.condition, worker_database) as client:
        response = await send(client, call, world)

    assert response.status_code == outcome.status
    validate_response(contract, outcome.operation_id, response)


@pytest.mark.parametrize(
    "outcome",
    [outcome for outcome in OUTCOMES if outcome.status >= FIRST_ERROR_STATUS],
    ids=str,
)
async def test_every_error_is_a_problem_with_a_trace_id(
    worker_database: WorkerDatabase, world: World, outcome: Outcome
) -> None:
    call = outcome.change(valid_calls(world)[outcome.operation_id], world)

    async with client_under(outcome.condition, worker_database) as client:
        response = await send(client, call, world)

    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert len(response.json()["trace_id"]) == TRACE_ID_LENGTH
    assert response.json()["status"] == outcome.status


async def test_refused_change_names_the_rule_and_a_rejected_body_does_not(
    backend: RunningBackend, world: World
) -> None:
    role_change = valid_calls(world)["changeAccountRole"]

    refused = await send(backend.client, replace(role_change, body={"role": "staff"}), world)
    rejected = await send(
        backend.client, replace(role_change, key=OTHER_KEY, body={"role": "admin"}), world
    )

    assert refused.json()["violated_rule"] == "role_unchanged"
    assert "violated_rule" not in rejected.json()


async def test_every_status_of_a_list_keeps_the_order_path_out_of_the_body(
    backend: RunningBackend, world: World
) -> None:
    call = Call("GET", f"{ORDERS}/ORD-99999", role="customer", key=KEY)

    response = await send(backend.client, call, world)

    assert "ORD-99999" not in response.text

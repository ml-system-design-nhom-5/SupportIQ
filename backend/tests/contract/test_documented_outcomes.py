"""One test for each status that the contract documents on each operation (CON-27).

The table `OUTCOMES` of `tests.contract.outcomes` lists them, and a test compares the table
with the contract, so a status added to the contract fails here until it has its test. `500`
comes from a failure inside the request, through the real exception handler, and `503` from a
replica with no database. The ai-service of every replica is an in-memory one that answers with
the examples of its contract, so no outcome depends on the network (TEST-16).
"""

from collections.abc import MutableSequence
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import assert_never

import httpx
import pytest
from schemathesis import BaseSchema
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from supportiq_backend.accounts import PasswordHash
from supportiq_backend.composition_root import BackgroundWork, create_app
from tests.contract.call_changes import OTHER_KEY
from tests.contract.calls import (
    KEY,
    NEW_ACCOUNT,
    ORDERS,
    Call,
    World,
    build_world,
    send,
    valid_calls,
)
from tests.contract.documented import list_operations, validate_response
from tests.contract.outcomes import OUTCOMES, UNPROCESSABLE, Condition, Outcome
from tests.integration.ai_service_doubles import (
    FakeAiService,
    refuse_connection,
    serve_examples,
)
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
PROBLEM_MEDIA_TYPE = "application/problem+json"
FIRST_ERROR_STATUS = 400
TRACE_ID_LENGTH = 32


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


def client_under(
    condition: Condition, worker_database: WorkerDatabase
) -> AbstractAsyncContextManager[httpx.AsyncClient]:
    ai_service = FakeAiService(serve_examples)
    match condition:
        case Condition.REQUEST_FAILS:
            app = create_app(
                build_settings(worker_database),
                RecordingEventRecorder(),
                FakeClock(),
                background=BackgroundWork.NONE,
                ai_service_transport=ai_service,
            )
            # Starlette runs this list in order, so the last entry is the innermost middleware.
            middleware: MutableSequence[Middleware] = app.user_middleware
            middleware.append(Middleware(FailingMiddleware))
            return running_app(app)
        case Condition.NO_DATABASE:
            settings = build_settings(worker_database, database_url_app=UNREACHABLE_URL)
            return running_client(
                settings, RecordingEventRecorder(), FakeClock(), ai_service=ai_service
            )
        case Condition.HEALTHY:
            return running_client(
                build_settings(worker_database),
                RecordingEventRecorder(),
                FakeClock(),
                ai_service=ai_service,
            )
        case Condition.NO_AI_SERVICE:
            return running_client(
                build_settings(worker_database),
                RecordingEventRecorder(),
                FakeClock(),
                ai_service=FakeAiService(refuse_connection),
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


@pytest.mark.parametrize("role", ["admin", "customer"])
async def test_creation_of_an_admin_or_customer_account_is_refused_by_the_contract(
    backend: RunningBackend, builder: DatabaseBuilder, world: World, role: str
) -> None:
    creation = valid_calls(world)["createAdminAccount"]

    response = await send(
        backend.client, replace(creation, body={**NEW_ACCOUNT, "role": role}), world
    )

    assert response.status_code == UNPROCESSABLE
    assert response.json()["type"] == "urn:supportiq:problem:invalid-request"
    assert (
        await builder.scalar(
            "SELECT count(*) FROM accounts WHERE display_name = :name",
            name=NEW_ACCOUNT["display_name"],
        )
        == 0
    )


async def test_every_status_of_a_list_keeps_the_order_path_out_of_the_body(
    backend: RunningBackend, world: World
) -> None:
    call = Call("GET", f"{ORDERS}/ORD-99999", role="customer", key=KEY)

    response = await send(backend.client, call, world)

    assert "ORD-99999" not in response.text

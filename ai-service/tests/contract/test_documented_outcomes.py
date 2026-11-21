"""One test for each status that the contract documents on each operation (CON-27).

The table `OUTCOMES` of `tests.contract.outcomes` lists them, and a test compares the table
with the contract, so a status added to the contract fails here until it has its test. `500`
comes from a failure inside the request, through the real exception handler, and `503` from a
replica without a loaded release.
"""

from collections.abc import MutableSequence
from contextlib import AbstractAsyncContextManager
from typing import assert_never

import httpx
import pytest
from schemathesis import BaseSchema
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Receive, Scope, Send

from tests.contract.documented import list_operations, validate_response
from tests.contract.outcomes import OUTCOMES, VALID_CALLS, Call, Condition, Outcome
from tests.integration.application import (
    SERVICE_TOKEN_HEADERS,
    build_app,
    build_ports,
    running_app,
)
from tests.unit.platform.fakes import RecordingEventRecorder
from tests.unit.release.fakes import StaticReleaseSource

pytestmark = pytest.mark.anyio

PROBLEM_MEDIA_TYPE = "application/problem+json"
FIRST_ERROR_STATUS = 400
TRACE_ID_LENGTH = 32


class FailingMiddleware:
    """Fail inside the request, where the exception handler of the application catches it."""

    def __init__(self, app: ASGIApp) -> None:
        """Keep the application, which is never called for a request.

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


def client_under(condition: Condition) -> AbstractAsyncContextManager[httpx.AsyncClient]:
    events = RecordingEventRecorder()
    match condition:
        case Condition.HEALTHY:
            return running_app(build_app(build_ports(), events))
        case Condition.NO_RELEASE:
            return running_app(build_app(build_ports(StaticReleaseSource(None)), events))
        case Condition.REQUEST_FAILS:
            app = build_app(build_ports(), events)
            # Starlette runs this list in order, so the last entry is the innermost middleware.
            middleware: MutableSequence[Middleware] = app.user_middleware
            middleware.append(Middleware(FailingMiddleware))
            return running_app(app)
        case _:
            assert_never(condition)


async def send(client: httpx.AsyncClient, call: Call) -> httpx.Response:
    headers = SERVICE_TOKEN_HEADERS if call.has_service_token else {}
    return await client.request(call.method, call.path, json=call.body, headers=headers)


def test_the_table_covers_every_status_of_every_operation(contract: BaseSchema) -> None:
    documented = {
        (operation.operation_id, status)
        for operation in list_operations(contract)
        for status in operation.statuses
    }

    assert {(outcome.operation_id, outcome.status.value) for outcome in OUTCOMES} == documented


@pytest.mark.parametrize("outcome", OUTCOMES, ids=str)
async def test_documented_outcome_matches_the_contract(
    contract: BaseSchema, outcome: Outcome
) -> None:
    async with client_under(outcome.condition) as client:
        response = await send(client, outcome.change(VALID_CALLS[outcome.operation_id]))

    assert response.status_code == outcome.status
    validate_response(contract, outcome.operation_id, response)


@pytest.mark.parametrize(
    "outcome",
    [outcome for outcome in OUTCOMES if outcome.status >= FIRST_ERROR_STATUS],
    ids=str,
)
async def test_every_error_is_a_problem_with_a_trace_id(outcome: Outcome) -> None:
    async with client_under(outcome.condition) as client:
        response = await send(client, outcome.change(VALID_CALLS[outcome.operation_id]))

    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert len(response.json()["trace_id"]) == TRACE_ID_LENGTH
    assert response.json()["status"] == outcome.status

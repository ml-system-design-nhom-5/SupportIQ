"""What the application serves is what the contract lists, and nothing writes commerce data.

TEST-26: no endpoint performs a refund, an order change, or any other transaction. A write
that the contract does not list fails the first test, and a write that it lists and this table
does not fails the second (ADR-0013, guardrail 1 of AGENTS.md).
"""

import re
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from schemathesis import BaseSchema

from supportiq_backend.composition_root import create_app
from tests.contract.documented import list_operations
from tests.integration.application import RunningBackend, build_settings
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

READ_METHOD = "GET"
EVERY_WRITE_OF_THE_CONTRACT = {
    ("POST", "/v1/sessions"),
    ("DELETE", "/v1/sessions/current"),
    ("POST", "/v1/shop/tickets"),
    ("POST", "/v1/admin/accounts/{account_id}/role-changes"),
    ("POST", "/v1/admin/accounts/{account_id}/status-changes"),
}
EVERY_READ_OF_THE_CONTRACT = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/v1/sessions/current"),
    ("GET", "/v1/shop/products"),
    ("GET", "/v1/shop/products/{product_id}"),
    ("GET", "/v1/shop/orders"),
    ("GET", "/v1/shop/orders/{order_id}"),
    ("GET", "/v1/shop/tickets"),
    ("GET", "/v1/shop/tickets/{ticket_id}"),
    ("GET", "/v1/admin/accounts"),
}
EVERY_OPERATION = sorted(EVERY_READ_OF_THE_CONTRACT | EVERY_WRITE_OF_THE_CONTRACT)
COMMERCE_PATHS = ("/v1/shop/products", "/v1/shop/orders")
PATH_PARAMETER = re.compile(r"\{[^}]+\}")
ANY_IDENTIFIER = "1"


def documented_operations(contract: BaseSchema) -> set[tuple[str, str]]:
    return {(operation.method, operation.path) for operation in list_operations(contract)}


def served_operations(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, str(route.path))
        for route in iter_route_contexts(app.routes)
        for method in route.methods or ()
    }


def test_the_application_serves_exactly_the_operations_of_the_contract(
    contract: BaseSchema, worker_database: WorkerDatabase
) -> None:
    app = create_app(build_settings(worker_database), RecordingEventRecorder(), FakeClock())

    assert served_operations(app) == documented_operations(contract)


def test_the_contract_lists_no_write_beyond_sessions_tickets_and_internal_accounts(
    contract: BaseSchema,
) -> None:
    writes = {
        operation for operation in documented_operations(contract) if operation[0] != READ_METHOD
    }

    assert writes == EVERY_WRITE_OF_THE_CONTRACT


def test_no_write_reaches_a_commerce_resource(contract: BaseSchema) -> None:
    commerce_writes = {
        path
        for method, path in documented_operations(contract)
        if method != READ_METHOD and path.startswith(COMMERCE_PATHS)
    }

    assert commerce_writes == set()


def test_no_console_route_exists_in_this_scope(worker_database: WorkerDatabase) -> None:
    app = create_app(build_settings(worker_database), RecordingEventRecorder(), FakeClock())

    assert {path for _, path in served_operations(app) if path.startswith("/v1/console/")} == set()


def test_the_table_of_operations_matches_the_contract(contract: BaseSchema) -> None:
    assert set(EVERY_OPERATION) == documented_operations(contract)


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path"), EVERY_OPERATION)
async def test_a_trailing_slash_gets_the_not_found_problem_and_no_redirect(
    backend: RunningBackend, method: str, path: str
) -> None:
    response = await backend.client.request(method, f"{PATH_PARAMETER.sub(ANY_IDENTIFIER, path)}/")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"
    assert "location" not in response.headers

"""What the application serves is what the contract lists, and nothing writes commerce data.

TEST-26: no endpoint performs a refund, an order change, or any other transaction. A write
that the contract does not list fails the first test, and a write that it lists and this table
does not fails the second (ADR-0013, guardrail 1 of AGENTS.md). No code path writes a reply
outside `sendReply` (FR-04): one route sends replies, and one statement inserts them.
"""

import re
from http import HTTPStatus
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from schemathesis import BaseSchema

from supportiq_backend.composition_root import BackgroundWork, create_app
from tests.contract.documented import list_operations
from tests.integration.ai_service_doubles import FakeAiService, serve_examples
from tests.integration.application import RunningBackend, build_settings
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

READ_METHOD = "GET"
EVERY_WRITE_OF_THE_CONTRACT = {
    ("POST", "/v1/sessions"),
    ("DELETE", "/v1/sessions/current"),
    ("POST", "/v1/sessions/current/password-changes"),
    ("POST", "/v1/shop/tickets"),
    ("POST", "/v1/console/tickets/{ticket_id}/views"),
    ("POST", "/v1/console/tickets/{ticket_id}/suggestions"),
    ("POST", "/v1/console/tickets/{ticket_id}/reply-proposals"),
    ("POST", "/v1/console/tickets/{ticket_id}/replies"),
    ("POST", "/v1/console/tickets/{ticket_id}/escalations"),
    ("POST", "/v1/admin/accounts"),
    ("POST", "/v1/admin/accounts/{account_id}/role-changes"),
    ("POST", "/v1/admin/accounts/{account_id}/status-changes"),
    ("POST", "/v1/admin/accounts/{account_id}/password-resets"),
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
    ("GET", "/v1/console/tickets"),
    ("GET", "/v1/console/tickets/{ticket_id}"),
    ("GET", "/v1/console/kb-documents/{document_id}/versions/{version}"),
    ("GET", "/v1/console/reports"),
    ("GET", "/v1/admin/accounts"),
    ("GET", "/v1/admin/versions"),
}
EVERY_OPERATION = sorted(EVERY_READ_OF_THE_CONTRACT | EVERY_WRITE_OF_THE_CONTRACT)
COMMERCE_PATHS = ("/v1/shop/products", "/v1/shop/orders")
REPLY_ROUTE = ("POST", "/v1/console/tickets/{ticket_id}/replies")
SOURCE_ROOT = Path(__file__).parents[2] / "src" / "supportiq_backend"
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
    app = create_app(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        background=BackgroundWork.NONE,
        ai_service_transport=FakeAiService(serve_examples),
    )

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


def test_only_send_reply_sends_a_reply(worker_database: WorkerDatabase) -> None:
    app = create_app(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        background=BackgroundWork.NONE,
        ai_service_transport=FakeAiService(serve_examples),
    )

    reply_routes = {
        operation for operation in served_operations(app) if operation[1].endswith("/replies")
    }

    assert reply_routes == {REPLY_ROUTE}


def test_one_statement_of_the_source_inserts_a_reply() -> None:
    sources = [path.read_text(encoding="utf-8") for path in SOURCE_ROOT.rglob("*.py")]

    inserts = sum(source.count("insert(ReplyRow)") for source in sources)
    callers = [source for source in sources if ".insert_reply(" in source]

    assert inserts == 1
    assert len(callers) == 1
    assert "class SendReply:" in callers[0]


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

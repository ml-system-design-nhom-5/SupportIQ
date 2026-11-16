"""Schemathesis over every operation and the health checks (CON-27, TEST-15).

Hypothesis runs derandomized, so each run sends the same requests. Each generated request
carries the session cookie of a role that may call the operation, because the contract's
`sessionCookie` scheme cannot say which role that is. Every response is checked against the
contract: status, media type, headers, and schema. The ai-service of the application is an
in-memory one that answers with the examples of its contract, so no request depends on the
network (TEST-16).
"""

import asyncio
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis import APIOperation, BaseSchema, Case
from schemathesis.core.adapter import OperationParameter, ResponsesContainer
from schemathesis.python.asgi import shutdown_lifespans

from supportiq_backend.composition_root import BackgroundWork, create_app
from supportiq_backend.composition_root.seed_commands import seed
from tests.contract.conftest import CONTRACT_FILE
from tests.contract.test_permissions import OPERATIONS_WITH_ROLES
from tests.integration.ai_service_doubles import FakeAiService, serve_examples
from tests.integration.application import ALLOWED_ORIGIN, build_settings
from tests.integration.builders import FAILED_SUGGESTION, DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

SEED_PATH = Path(__file__).parents[2] / "seed" / "synthetic-dev-only-v1.json"
SEED_PASSWORD = "contract-test-password"
EXAMPLES_PER_OPERATION = 25
SESSION_COOKIE = "supportiq_session"
LOGIN_NAME_OF_ROLE = {
    "customer": "customer-1",
    "staff": "staff-1",
    "manager": "manager-1",
    "admin": "admin-1",
}
ROLE_OF_OPERATION = {
    "getCurrentSession": "customer",
    "changeOwnPassword": "customer",
    "deleteCurrentSession": "customer",
    "listShopProducts": "customer",
    "getShopProduct": "customer",
    "listShopOrders": "customer",
    "getShopOrder": "customer",
    "listShopTickets": "customer",
    "createShopTicket": "customer",
    "getShopTicket": "customer",
    # A manager may list every queue; staff get `403` for every queue but `open`.
    "listConsoleTickets": "manager",
    "getConsoleTicket": "staff",
    "recordTicketView": "staff",
    "createSuggestion": "staff",
    "createReplyProposal": "staff",
    "sendReply": "staff",
    "createEscalation": "staff",
    "getSuggestionEvents": "staff",
    "getConsoleKbDocumentVersion": "staff",
    "getConsoleReport": "manager",
    "listAdminAccounts": "admin",
    "createAdminAccount": "admin",
    "changeAccountRole": "admin",
    "changeAccountStatus": "admin",
    "resetAccountPassword": "admin",
    "getAdminVersions": "admin",
}
# The contract: a value that is not a valid `traceparent` is ignored and never causes `422`, so
# no value of it can make a request invalid. A unit test covers that case, and generation
# leaves the header out, because negative testing would expect a rejection.
TRACEPARENT_REFERENCE = {"$ref": "#/components/parameters/Traceparent"}
# The contract: a cursor is any text of 1 to 512 characters, and one that is malformed, or from
# another operation, returns `422`; a change or a reset that breaks an admin limit returns `422`
# with `violated_rule`; a wrong current password returns `422` with
# `current_password_incorrect`; a retry with nothing to retry, or an intent correction while no
# intent is known, returns `422`; a reply or a reply proposal that breaks a rule of its basis,
# or holds a placeholder, returns `422`; an escalation with `other` and no note returns `422`;
# and a report period whose start is not earlier than its end returns `422`. So on these
# operations a request can match the schema and still get `422`. Every other operation keeps
# the strict default of the check.
OPERATIONS_WITH_A_DOCUMENTED_422_FOR_VALID_DATA = [
    "listShopProducts",
    "listShopOrders",
    "listShopTickets",
    "listConsoleTickets",
    "createSuggestion",
    "createReplyProposal",
    "sendReply",
    "createEscalation",
    "getConsoleReport",
    "listAdminAccounts",
    "changeAccountRole",
    "changeAccountStatus",
    "resetAccountPassword",
    "changeOwnPassword",
]
ACCEPTED_STATUSES_WITH_422 = ["2xx", "3xx", "401", "403", "404", "409", "422", "429", "5xx"]
SUPPRESSED_HEALTH_CHECKS = [
    HealthCheck.function_scoped_fixture,
    HealthCheck.too_slow,
    HealthCheck.filter_too_much,
]

type GeneratedOperation = APIOperation[
    OperationParameter, ResponsesContainer[object], object, BaseSchema
]
type GeneratedCase = Case[GeneratedOperation]


@dataclass(frozen=True, slots=True)
class ContractRun:
    """What the requests of one test need from the seeded database.

    Attributes:
        cookie_of_role: The raw session identifier of a signed-in account of each role.
        path_values: Identifiers that exist, by Schemathesis parameter name.
    """

    cookie_of_role: Mapping[str, str]
    path_values: Mapping[str, str]


async def prepare_database(worker_database: WorkerDatabase) -> ContractRun:
    await seed_database(worker_database)
    engine = create_owner_engine(worker_database)
    builder = DatabaseBuilder(engine)
    account_of_role = {
        role: await account_of(builder, login_name)
        for role, login_name in LOGIN_NAME_OF_ROLE.items()
    }
    customer_id = await builder.scalar(
        "SELECT customer_id FROM accounts WHERE account_id = :account_id",
        account_id=account_of_role["customer"],
    )
    order_id = await builder.scalar(
        "SELECT min(order_id) FROM orders WHERE customer_id = :customer_id",
        customer_id=customer_id,
    )
    ticket_id = await builder.ticket(UUID(str(customer_id)), str(order_id))
    # A suggestion that ended unavailable makes a retry valid and the workspace show it.
    await builder.suggestion(ticket_id, FAILED_SUGGESTION)
    run = ContractRun(
        cookie_of_role=await sign_in_every_role(builder, account_of_role),
        path_values={
            "path.product_id": str(await builder.scalar("SELECT min(product_id) FROM products")),
            "path.order_id": str(order_id),
            "query.order_id": str(order_id),
            "path.ticket_id": ticket_id,
            "path.account_id": str(account_of_role["staff"]),
        },
    )
    await engine.dispose()
    return run


async def seed_database(worker_database: WorkerDatabase) -> None:
    await seed(
        build_settings(
            worker_database,
            database_url_owner=worker_database.owner_url,
            seed_password_customer=SEED_PASSWORD,
            seed_password_staff=SEED_PASSWORD,
            seed_password_manager=SEED_PASSWORD,
            seed_password_admin=SEED_PASSWORD,
        ),
        RecordingEventRecorder(),
        seed_file=SEED_PATH,
    )


async def sign_in_every_role(
    builder: DatabaseBuilder, account_of_role: Mapping[str, UUID]
) -> Mapping[str, str]:
    cookie_of_role: dict[str, str] = {}
    for role, account_id in account_of_role.items():
        cookie_of_role[role] = await builder.session(account_id, role)
    return cookie_of_role


async def account_of(builder: DatabaseBuilder, login_name: str) -> UUID:
    account_id = await builder.scalar(
        "SELECT account_id FROM accounts WHERE login_name = :login_name", login_name=login_name
    )
    return UUID(str(account_id))


def load_contract(
    worker_database: WorkerDatabase, generation_mode: str, parameters: Mapping[str, str]
) -> BaseSchema:
    config = schemathesis.Config.from_dict(  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves its dict argument unparametrized, #3
        {
            "generation": {
                "mode": generation_mode,
                "max-examples": EXAMPLES_PER_OPERATION,
                "deterministic": True,
                # Each request carries the session cookie of its role, set below.
                "with-security-parameters": False,
            },
            "parameters": dict(parameters),
            "operations": [
                {
                    "include-operation-id": OPERATIONS_WITH_A_DOCUMENTED_422_FOR_VALID_DATA,
                    "checks": {
                        "positive_data_acceptance": {
                            "expected-statuses": ACCEPTED_STATUSES_WITH_422
                        }
                    },
                }
            ],
        }
    )
    schema = schemathesis.openapi.from_path(CONTRACT_FILE, config=config)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves PathLike unparametrized, #3
    leave_out_traceparent(schema)
    schema.app = create_app(
        build_settings(worker_database),
        RecordingEventRecorder(),
        FakeClock(),
        background=BackgroundWork.NONE,
        ai_service_transport=FakeAiService(serve_examples),
    )
    return schema


def leave_out_traceparent(schema: BaseSchema) -> None:
    for path_item in schema.raw_schema["paths"].values():
        for operation in path_item.values():
            operation["parameters"] = [
                parameter
                for parameter in operation["parameters"]
                if parameter != TRACEPARENT_REFERENCE
            ]


def call_and_validate(case: GeneratedCase, run: ContractRun) -> None:
    role = ROLE_OF_OPERATION.get(str(case.operation.definition.raw.get("operationId")))
    cookies = {} if role is None else {SESSION_COOKIE: run.cookie_of_role[role]}
    case.call_and_validate(headers={"Origin": ALLOWED_ORIGIN}, cookies=cookies)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves `Case` unparametrized in its checks, #3


@pytest.fixture
def contract_run(worker_database: WorkerDatabase) -> ContractRun:
    return asyncio.run(prepare_database(worker_database))


@pytest.fixture
def generated_identifiers_schema(
    worker_database: WorkerDatabase, contract_run: ContractRun
) -> Iterator[BaseSchema]:
    del contract_run
    yield load_contract(worker_database, "all", {})
    shutdown_lifespans()


@pytest.fixture
def seeded_identifiers_schema(
    worker_database: WorkerDatabase, contract_run: ContractRun
) -> Iterator[BaseSchema]:
    yield load_contract(worker_database, "positive", contract_run.path_values)
    shutdown_lifespans()


generated_identifiers = schemathesis.pytest.from_fixture("generated_identifiers_schema")
seeded_identifiers = schemathesis.pytest.from_fixture("seeded_identifiers_schema")


def test_every_operation_with_roles_is_sent_with_a_session_of_one_of_its_roles() -> None:
    # Without a session every request gets `401`, so an operation missing here would pass
    # without being checked.
    assert set(ROLE_OF_OPERATION) == set(OPERATIONS_WITH_ROLES)


@generated_identifiers.parametrize()  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]  # the decorator of Schemathesis is untyped, #3
@settings(max_examples=EXAMPLES_PER_OPERATION, suppress_health_check=SUPPRESSED_HEALTH_CHECKS)
def test_generated_requests_match_the_contract(
    case: GeneratedCase, contract_run: ContractRun
) -> None:
    call_and_validate(case, contract_run)


@seeded_identifiers.parametrize()  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]  # the decorator of Schemathesis is untyped, #3
@settings(max_examples=EXAMPLES_PER_OPERATION, suppress_health_check=SUPPRESSED_HEALTH_CHECKS)
def test_requests_about_seeded_records_match_the_contract(
    case: GeneratedCase, contract_run: ContractRun
) -> None:
    call_and_validate(case, contract_run)

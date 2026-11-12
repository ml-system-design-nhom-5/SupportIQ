"""Schemathesis over every operation and the health checks (CON-27, TEST-15).

Hypothesis runs derandomized, so each run sends the same requests. Each generated request
carries the session cookie of a role that may call the operation, because the contract's
`sessionCookie` scheme cannot say which role that is. Every response is checked against the
contract: status, media type, headers, and schema.
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

from supportiq_backend.composition_root import create_app
from supportiq_backend.composition_root.seed_commands import seed
from tests.contract.conftest import CONTRACT_FILE
from tests.integration.application import ALLOWED_ORIGIN, build_settings
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

SEED_PATH = Path(__file__).parents[2] / "seed" / "synthetic-dev-only-v1.json"
SEED_PASSWORD = "contract-test-password"
EXAMPLES_PER_OPERATION = 25
SESSION_COOKIE = "supportiq_session"
LOGIN_NAME_OF_ROLE = {"customer": "customer-1", "admin": "admin-1"}
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
    "listAdminAccounts": "admin",
    "createAdminAccount": "admin",
    "changeAccountRole": "admin",
    "changeAccountStatus": "admin",
    "resetAccountPassword": "admin",
}
# The contract: a value that is not a valid `traceparent` is ignored and never causes `422`, so
# no value of it can make a request invalid. A unit test covers that case, and generation
# leaves the header out, because negative testing would expect a rejection.
TRACEPARENT_REFERENCE = {"$ref": "#/components/parameters/Traceparent"}
# The contract: a cursor is any text of 1 to 512 characters, and one that is malformed, or from
# another operation, returns `422`; a change or a reset that breaks an admin limit returns `422`
# with `violated_rule`; and a wrong current password returns `422` with
# `current_password_incorrect`. So on these operations a request can match the schema and still
# get `422`. Every other operation keeps the strict default of the check.
OPERATIONS_WITH_A_DOCUMENTED_422_FOR_VALID_DATA = [
    "listShopProducts",
    "listShopOrders",
    "listShopTickets",
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
    engine = create_owner_engine(worker_database)
    builder = DatabaseBuilder(engine)
    customer_account = await account_of(builder, "customer-1")
    admin_account = await account_of(builder, "admin-1")
    customer_id = await builder.scalar(
        "SELECT customer_id FROM accounts WHERE account_id = :account_id",
        account_id=customer_account,
    )
    order_id = await builder.scalar(
        "SELECT min(order_id) FROM orders WHERE customer_id = :customer_id",
        customer_id=customer_id,
    )
    ticket_id = await builder.ticket(UUID(str(customer_id)), str(order_id))
    run = ContractRun(
        cookie_of_role={
            "customer": await builder.session(customer_account, "customer"),
            "admin": await builder.session(admin_account, "admin"),
        },
        path_values={
            "path.product_id": str(await builder.scalar("SELECT min(product_id) FROM products")),
            "path.order_id": str(order_id),
            "query.order_id": str(order_id),
            "path.ticket_id": ticket_id,
            "path.account_id": str(await account_of(builder, "staff-1")),
        },
    )
    await engine.dispose()
    return run


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
    schema.app = create_app(build_settings(worker_database), RecordingEventRecorder(), FakeClock())
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

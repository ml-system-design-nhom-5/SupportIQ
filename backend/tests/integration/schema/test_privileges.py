"""The privileges of `supportiq_app`: exactly the design's table, and nothing else.

Every statement runs as `supportiq_app`, the role of the replicas (backend foundation design,
Database roles and privileges; Errors and guardrails).
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import Text, literal_column, select, table
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_raw_app_engine
from tests.integration.schema.statements import (
    CHECK_VIOLATION,
    INSUFFICIENT_PRIVILEGE,
    run_statement,
    sqlstate_of_refusal,
)

pytestmark = pytest.mark.anyio

EVERY_TABLE = (
    "accounts",
    "sessions",
    "sign_in_failures",
    "idempotency_records",
    "customers",
    "products",
    "orders",
    "order_lines",
    "shipments",
    "refunds",
    "tickets",
    "customer_messages",
    "audit_log_entries",
)
WRITES_OF_COMMERCE_DATA = (
    "INSERT INTO customers DEFAULT VALUES",
    "UPDATE customers SET display_name = display_name",
    "DELETE FROM customers",
    "TRUNCATE customers",
    "INSERT INTO products DEFAULT VALUES",
    "UPDATE products SET name = name",
    "DELETE FROM products",
    "TRUNCATE products",
    "INSERT INTO orders DEFAULT VALUES",
    "UPDATE orders SET order_status = order_status",
    "DELETE FROM orders",
    "TRUNCATE orders",
    "INSERT INTO order_lines DEFAULT VALUES",
    "UPDATE order_lines SET quantity = quantity",
    "DELETE FROM order_lines",
    "TRUNCATE order_lines",
    "INSERT INTO shipments DEFAULT VALUES",
    "UPDATE shipments SET shipment_status = shipment_status",
    "DELETE FROM shipments",
    "TRUNCATE shipments",
    "INSERT INTO refunds DEFAULT VALUES",
    "UPDATE refunds SET refund_status = refund_status",
    "DELETE FROM refunds",
    "TRUNCATE refunds",
)
NEW_LOGIN_NAME = "new-account"
INSERT_ACCOUNT = (
    "INSERT INTO accounts (account_id, login_name, display_name, role, is_active,"
    " password_hash, created_at) VALUES (gen_random_uuid(), :login_name, 'Name', :role, true,"
    " 'hash', now())"
)
INSERT_ACCOUNT_WITH_A_CUSTOMER = (
    "INSERT INTO accounts (account_id, login_name, display_name, role, is_active, customer_id,"
    " password_hash, created_at) VALUES (gen_random_uuid(), :login_name, 'Name', :role, true,"
    " gen_random_uuid(), 'hash', now())"
)


@pytest.fixture
async def app_engine_raw(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_raw_app_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize("name", EVERY_TABLE)
async def test_app_can_read_every_table(app_engine_raw: AsyncEngine, name: str) -> None:
    read_all = select(literal_column("*", Text())).select_from(table(name))

    outcome = await sqlstate_of_refusal(app_engine_raw, str(read_all))

    assert outcome == "accepted"


@pytest.mark.parametrize("statement", WRITES_OF_COMMERCE_DATA)
async def test_app_cannot_write_commerce_data(app_engine_raw: AsyncEngine, statement: str) -> None:
    outcome = await sqlstate_of_refusal(app_engine_raw, statement)

    assert outcome == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "DELETE FROM accounts",
        "UPDATE accounts SET display_name = 'Mallory'",
        "UPDATE accounts SET login_name = 'admin-9'",
        "UPDATE accounts SET customer_id = NULL",
        "UPDATE accounts SET created_at = now()",
        "UPDATE customer_messages SET body = 'edited'",
        "DELETE FROM customer_messages",
        "UPDATE audit_log_entries SET event_type = 'reply.sent'",
        "DELETE FROM audit_log_entries",
        "TRUNCATE audit_log_entries",
        "DELETE FROM tickets",
        "UPDATE tickets SET customer_id = NULL",
        "UPDATE tickets SET order_id = NULL",
        "UPDATE tickets SET handling_mode = 'manual'",
        "UPDATE tickets SET source = 'import'",
        "UPDATE tickets SET created_at = now()",
        "TRUNCATE sessions",
        "SELECT * FROM alembic_version",
        "CREATE TABLE intruder (id integer)",
    ],
)
async def test_app_cannot_run_a_statement_outside_its_privileges(
    app_engine_raw: AsyncEngine, statement: str
) -> None:
    outcome = await sqlstate_of_refusal(app_engine_raw, statement)

    assert outcome == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE accounts SET role = role, is_active = is_active, password_hash = password_hash"
        " WHERE false",
        "UPDATE tickets SET status = status, is_authority_required = is_authority_required,"
        " handling_started_at = handling_started_at, closed_at = closed_at WHERE false",
        "UPDATE sessions SET last_seen_at = last_seen_at WHERE false",
        "DELETE FROM sessions WHERE false",
        "UPDATE sign_in_failures SET failed_at = failed_at WHERE false",
        "DELETE FROM sign_in_failures WHERE false",
        "UPDATE idempotency_records SET response_status = response_status WHERE false",
        "DELETE FROM idempotency_records WHERE false",
        "SELECT nextval('ticket_number_seq')",
    ],
)
async def test_app_can_run_the_statements_of_its_privileges(
    app_engine_raw: AsyncEngine, statement: str
) -> None:
    outcome = await sqlstate_of_refusal(app_engine_raw, statement)

    assert outcome == "accepted"


@pytest.mark.parametrize(
    ("statement", "role", "outcome"),
    [
        pytest.param(INSERT_ACCOUNT, "staff", "accepted", id="staff"),
        pytest.param(INSERT_ACCOUNT, "manager", "accepted", id="manager"),
        pytest.param(INSERT_ACCOUNT, "admin", INSUFFICIENT_PRIVILEGE, id="admin-by-the-trigger"),
        pytest.param(INSERT_ACCOUNT, "customer", CHECK_VIOLATION, id="customer-without-customer"),
        pytest.param(
            INSERT_ACCOUNT_WITH_A_CUSTOMER,
            "customer",
            INSUFFICIENT_PRIVILEGE,
            id="customer-with-customer",
        ),
    ],
)
async def test_app_inserts_staff_and_manager_accounts_and_never_an_admin_or_a_customer(
    app_engine_raw: AsyncEngine, statement: str, role: str, outcome: str
) -> None:
    result = await sqlstate_of_refusal(
        app_engine_raw, statement, login_name=NEW_LOGIN_NAME, role=role
    )

    assert result == outcome


async def test_app_can_insert_a_ticket_its_message_and_an_audit_entry(
    app_engine_raw: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)

    await run_statement(
        app_engine_raw,
        "WITH ticket AS ("
        " INSERT INTO tickets (customer_id, order_id, status, handling_mode, source, created_at)"
        " VALUES (:customer_id, :order_id, 'open', 'assisted', 'shop', now()) RETURNING ticket_id)"
        " INSERT INTO customer_messages (message_id, ticket_id, body, created_at)"
        " SELECT gen_random_uuid(), ticket_id, 'Where is my parcel?', now() FROM ticket",
        customer_id=customer_id,
        order_id=order_id,
    )
    await run_statement(
        app_engine_raw,
        "INSERT INTO audit_log_entries (entry_id, occurred_at, event_type, trace_id, data)"
        " VALUES (gen_random_uuid(), now(), 'account.role_changed', :trace_id, '{}')",
        trace_id="0" * 31 + "1",
    )

    message_count = await builder.scalar("SELECT count(*) FROM customer_messages")
    assert message_count == 1

"""Triggers and constraints: what the database refuses for every role (backend foundation design).

The audit log rejects UPDATE and DELETE (TEST-26, SEC-39); a role changes only between staff and
manager (ADR-0012, admin limit 3); the authority flag never goes back to false (contracts v1); a
product appears at most once in an order (backend contract 1.0.1).
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.builders import (
    AccountSpec,
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    ShipmentSpec,
    TicketSpec,
)
from tests.integration.database import (
    WorkerDatabase,
    create_owner_engine,
    create_raw_app_engine,
)
from tests.integration.schema.statements import (
    CHECK_VIOLATION,
    INSUFFICIENT_PRIVILEGE,
    UNIQUE_VIOLATION,
    run_statement,
    sqlstate_of_refusal,
)

pytestmark = pytest.mark.anyio

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
INSERT_AUDIT_ENTRY = (
    "INSERT INTO audit_log_entries (entry_id, occurred_at, event_type, trace_id, data)"
    " VALUES (gen_random_uuid(), now(), 'account.status_changed', :trace_id, '{}')"
)
CHANGE_ROLE = "UPDATE accounts SET role = :role WHERE account_id = :account_id"


@pytest.fixture
async def app_engine_raw(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_raw_app_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log_entries SET event_type = 'reply.sent'",
        "DELETE FROM audit_log_entries",
        "UPDATE audit_log_entries SET data = data WHERE false",
        "DELETE FROM audit_log_entries WHERE false",
    ],
)
async def test_audit_log_refuses_update_and_delete_even_from_the_owner(
    owner_engine: AsyncEngine, statement: str
) -> None:
    await run_statement(owner_engine, INSERT_AUDIT_ENTRY, trace_id=TRACE_ID)

    outcome = await sqlstate_of_refusal(owner_engine, statement)

    assert outcome == INSUFFICIENT_PRIVILEGE


async def test_audit_log_can_be_truncated_by_the_owner_only(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    await run_statement(owner_engine, INSERT_AUDIT_ENTRY, trace_id=TRACE_ID)

    await run_statement(owner_engine, "TRUNCATE audit_log_entries")

    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0


@pytest.mark.parametrize(("old_role", "new_role"), [("staff", "manager"), ("manager", "staff")])
async def test_role_changes_between_staff_and_manager(
    app_engine_raw: AsyncEngine, builder: DatabaseBuilder, old_role: str, new_role: str
) -> None:
    account_id = await builder.account(AccountSpec(old_role))

    await run_statement(app_engine_raw, CHANGE_ROLE, role=new_role, account_id=account_id)

    role = await builder.scalar(
        "SELECT role FROM accounts WHERE account_id = :account_id", account_id=account_id
    )
    assert role == new_role


@pytest.mark.parametrize(
    ("old_role", "new_role"),
    [
        ("staff", "admin"),
        ("manager", "admin"),
        ("admin", "staff"),
        ("admin", "manager"),
        ("staff", "customer"),
    ],
)
async def test_any_other_role_change_is_refused_for_every_role(
    app_engine_raw: AsyncEngine,
    owner_engine: AsyncEngine,
    builder: DatabaseBuilder,
    old_role: str,
    new_role: str,
) -> None:
    account_id = await builder.account(AccountSpec(old_role))

    app_outcome = await sqlstate_of_refusal(
        app_engine_raw, CHANGE_ROLE, role=new_role, account_id=account_id
    )
    owner_outcome = await sqlstate_of_refusal(
        owner_engine, CHANGE_ROLE, role=new_role, account_id=account_id
    )

    assert (app_outcome, owner_outcome) == (CHECK_VIOLATION, CHECK_VIOLATION)


async def test_customer_account_role_change_is_refused(
    app_engine_raw: AsyncEngine, builder: DatabaseBuilder
) -> None:
    account_id, _ = await builder.customer_account()

    outcome = await sqlstate_of_refusal(
        app_engine_raw, CHANGE_ROLE, role="staff", account_id=account_id
    )

    assert outcome == CHECK_VIOLATION


async def test_authority_flag_can_be_set(
    app_engine_raw: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id)

    await run_statement(
        app_engine_raw,
        "UPDATE tickets SET is_authority_required = true WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    )

    flag = await builder.scalar(
        "SELECT is_authority_required FROM tickets WHERE ticket_id = :ticket_id",
        ticket_id=ticket_id,
    )
    assert flag is True


async def test_authority_flag_never_goes_back_to_false_for_every_role(
    app_engine_raw: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id, TicketSpec(is_authority_required=True))
    clear_flag = "UPDATE tickets SET is_authority_required = false WHERE ticket_id = :ticket_id"

    app_outcome = await sqlstate_of_refusal(app_engine_raw, clear_flag, ticket_id=ticket_id)
    owner_outcome = await sqlstate_of_refusal(owner_engine, clear_flag, ticket_id=ticket_id)

    assert (app_outcome, owner_outcome) == (CHECK_VIOLATION, CHECK_VIOLATION)


async def test_ticket_ids_follow_the_ticket_number(builder: DatabaseBuilder) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)

    ticket_id = await builder.ticket(customer_id, order_id)

    assert ticket_id == "TCK-1001"


async def test_customer_id_is_required_exactly_for_customer_accounts(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    insert_account = (
        "INSERT INTO accounts (account_id, login_name, display_name, role, is_active,"
        " customer_id, password_hash, created_at) VALUES (gen_random_uuid(), :login_name,"
        " 'Name', :role, true, :customer_id, 'hash', now())"
    )

    staff_outcome = await sqlstate_of_refusal(
        owner_engine, insert_account, login_name="staff-x", role="staff", customer_id=customer_id
    )
    customer_outcome = await sqlstate_of_refusal(
        owner_engine, insert_account, login_name="customer-x", role="customer", customer_id=None
    )

    assert (staff_outcome, customer_outcome) == (CHECK_VIOLATION, CHECK_VIOLATION)


async def test_an_order_has_at_most_one_shipment(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order(
        customer_id, OrderSpec(lines=(LineSpec(await builder.product()),), shipment=ShipmentSpec())
    )

    outcome = await sqlstate_of_refusal(
        owner_engine,
        "INSERT INTO shipments (shipment_id, order_id, shipment_status, tracking_code)"
        " VALUES (gen_random_uuid(), :order_id, 'in_transit', 'TRK-0000000099')",
        order_id=order_id,
    )

    assert outcome == UNIQUE_VIOLATION


async def test_a_product_appears_at_most_once_in_an_order(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    product_id = await builder.product()
    order_id = await builder.order(customer_id, OrderSpec(lines=(LineSpec(product_id),)))

    outcome = await sqlstate_of_refusal(
        owner_engine,
        "INSERT INTO order_lines (order_id, line_number, product_id, quantity)"
        " VALUES (:order_id, 2, :product_id, 1)",
        order_id=order_id,
        product_id=product_id,
    )

    assert outcome == UNIQUE_VIOLATION


async def test_delivered_at_is_present_exactly_when_the_shipment_is_delivered(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_id = await builder.customer()
    order_id = await builder.order_of_one_product(customer_id)

    outcome = await sqlstate_of_refusal(
        owner_engine,
        "INSERT INTO shipments (shipment_id, order_id, shipment_status, tracking_code)"
        " VALUES (gen_random_uuid(), :order_id, 'delivered', 'TRK-0000000098')",
        order_id=order_id,
    )

    assert outcome == CHECK_VIOLATION

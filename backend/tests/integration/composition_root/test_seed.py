"""The seed and reset commands: deterministic, complete, and synthetic (DATA-03, DATA-04)."""

import json
import operator
from collections.abc import AsyncIterator
from functools import reduce
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Text, literal_column, select, table, text
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import Password, PasswordHash
from supportiq_backend.accounts.adapters.credentials import Argon2Passwords
from supportiq_backend.commerce import (
    ORDER_ID_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
    OrderStatus,
    RefundStatus,
    ShipmentStatus,
)
from supportiq_backend.composition_root.seed_commands import (
    SEED_FILE,
    SeedFileInvalidError,
    load_seed_document,
    reset,
    seed,
)
from supportiq_backend.composition_root.settings_loading import SettingRequiredError
from supportiq_backend.platform import DatabaseOperationError, EventName
from supportiq_backend.platform.settings import Settings
from tests.integration.application import build_settings
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import BACKEND_TABLE_NAMES, WorkerDatabase, create_owner_engine
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio

BACKEND_ROOT = Path(__file__).parents[3]
SEED_PATH = BACKEND_ROOT / SEED_FILE
CUSTOMER_PASSWORD = "seed-customer-test-password"
STAFF_PASSWORD = "seed-staff-test-password"
MANAGER_PASSWORD = "seed-manager-test-password"
ADMIN_PASSWORD = "seed-admin-test-password"
PASSWORD_BY_ROLE = {
    "customer": CUSTOMER_PASSWORD,
    "staff": STAFF_PASSWORD,
    "manager": MANAGER_PASSWORD,
    "admin": ADMIN_PASSWORD,
}
SEEDED_ORDER = "ORD-20901"
type TableRows = dict[str, list[tuple[object, ...]]]


def seed_settings(worker_database: WorkerDatabase) -> Settings:
    return build_settings(
        worker_database,
        database_url_owner=worker_database.owner_url,
        seed_password_customer=CUSTOMER_PASSWORD,
        seed_password_staff=STAFF_PASSWORD,
        seed_password_manager=MANAGER_PASSWORD,
        seed_password_admin=ADMIN_PASSWORD,
    )


async def read_every_table(engine: AsyncEngine) -> TableRows:
    rows: TableRows = {}
    async with engine.connect() as connection:
        for name in BACKEND_TABLE_NAMES:
            result = await connection.execute(
                select(literal_column("*", Text())).select_from(table(name))
            )
            columns = tuple(result.keys())
            rows[name] = sorted(
                (
                    tuple(
                        value
                        for column, value in zip(columns, row, strict=True)
                        if column != "password_hash"
                    )
                    for row in result
                ),
                key=repr,
            )
    return rows


async def customer_of_the_seed(builder: DatabaseBuilder) -> UUID:
    customer_id = await builder.scalar(
        "SELECT customer_id FROM accounts WHERE login_name = 'customer-1'"
    )
    return UUID(str(customer_id))


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def seeded(worker_database: WorkerDatabase) -> Settings:
    settings = seed_settings(worker_database)
    await seed(settings, RecordingEventRecorder(), seed_file=SEED_PATH)
    return settings


@pytest.mark.usefixtures("seeded")
async def test_seed_holds_at_least_one_account_per_role(builder: DatabaseBuilder) -> None:
    roles = await builder.scalar(
        "SELECT string_agg(DISTINCT role, ',' ORDER BY role) FROM accounts"
    )

    assert roles == ",".join(sorted(PASSWORD_BY_ROLE))


def test_seed_covers_every_order_shipment_and_refund_status() -> None:
    document = load_seed_document(SEED_PATH)
    orders = document.commerce.orders

    order_statuses = {order.order_status for order in orders}
    shipment_statuses = {order.shipment.shipment_status for order in orders if order.shipment}
    refund_statuses = {order.refund.refund_status for order in orders if order.refund}

    assert order_statuses == set(OrderStatus)
    assert shipment_statuses == set(ShipmentStatus)
    assert refund_statuses == set(RefundStatus)


def test_seed_is_labeled_and_follows_the_id_formats() -> None:
    document = load_seed_document(SEED_PATH)
    orders = document.commerce.orders

    assert document.label == "synthetic-dev-only"
    assert all(ORDER_ID_PATTERN.fullmatch(order.order_id) for order in orders)
    assert all(TRANSACTION_ID_PATTERN.fullmatch(order.transaction_id) for order in orders)
    assert all(
        TRACKING_CODE_PATTERN.fullmatch(order.shipment.tracking_code)
        for order in orders
        if order.shipment
    )


def test_seed_order_totals_add_up_from_lines_and_shipping() -> None:
    document = load_seed_document(SEED_PATH)
    price_of = {
        product.product_id: product.price.amount_minor for product in document.commerce.products
    }

    differences = [
        order.order_total.amount_minor
        - order.shipping_cost.amount_minor
        - sum(price_of[line.product_id] * line.quantity for line in order.lines)
        for order in document.commerce.orders
    ]

    assert set(differences) == {0}


def test_seed_file_holds_no_password() -> None:
    text_of_file = SEED_PATH.read_text(encoding="utf-8").lower()

    assert "password" not in text_of_file


async def test_seed_twice_through_reset_gives_the_same_rows_apart_from_the_hashes(
    owner_engine: AsyncEngine, seeded: Settings
) -> None:
    first = await read_every_table(owner_engine)

    await reset(seeded, RecordingEventRecorder(), seed_file=SEED_PATH)

    assert await read_every_table(owner_engine) == first


async def test_each_seeded_password_matches_its_hash(
    builder: DatabaseBuilder, seeded: Settings
) -> None:
    assert seeded.seed_password_staff is not None
    password_hash = await builder.scalar(
        "SELECT password_hash FROM accounts WHERE login_name = 'staff-1'"
    )

    is_valid = await Argon2Passwords().verify(
        PasswordHash(str(password_hash)), Password(STAFF_PASSWORD)
    )
    is_other_valid = await Argon2Passwords().verify(
        PasswordHash(str(password_hash)), Password(ADMIN_PASSWORD)
    )

    assert is_valid is True
    assert is_other_valid is False


async def test_accounts_of_one_role_have_different_salts(
    builder: DatabaseBuilder, seeded: Settings
) -> None:
    assert seeded.seed_password_customer is not None

    count = await builder.scalar(
        "SELECT count(DISTINCT password_hash) FROM accounts WHERE role = 'customer'"
    )

    assert count == await builder.scalar("SELECT count(*) FROM accounts WHERE role = 'customer'")


async def test_reset_returns_changed_accounts_and_tickets_to_the_seed(
    owner_engine: AsyncEngine, builder: DatabaseBuilder, seeded: Settings
) -> None:
    fresh = await read_every_table(owner_engine)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("UPDATE accounts SET role = 'manager' WHERE login_name = 'staff-1'")
        )
        await connection.execute(
            text("UPDATE accounts SET is_active = false WHERE login_name = 'staff-2'")
        )
    await builder.ticket(await customer_of_the_seed(builder), SEEDED_ORDER)
    events = RecordingEventRecorder()

    await reset(seeded, events, seed_file=SEED_PATH)

    assert await read_every_table(owner_engine) == fresh
    assert events.names() == (EventName.SEED_RESET,)


async def test_reset_restarts_the_ticket_numbers(
    builder: DatabaseBuilder, seeded: Settings
) -> None:
    customer_id = await customer_of_the_seed(builder)
    await builder.ticket(customer_id, SEEDED_ORDER)

    await reset(seeded, RecordingEventRecorder(), seed_file=SEED_PATH)
    ticket_id = await builder.ticket(customer_id, SEEDED_ORDER)

    assert ticket_id == "TCK-1001"


async def test_seed_on_a_seeded_database_fails_and_changes_nothing(
    owner_engine: AsyncEngine, seeded: Settings
) -> None:
    before = await read_every_table(owner_engine)

    with pytest.raises(DatabaseOperationError):
        await seed(seeded, RecordingEventRecorder(), seed_file=SEED_PATH)

    assert await read_every_table(owner_engine) == before


async def test_seed_names_a_missing_password_setting(worker_database: WorkerDatabase) -> None:
    settings = build_settings(worker_database, database_url_owner=worker_database.owner_url)

    with pytest.raises(SettingRequiredError) as caught:
        await seed(settings, RecordingEventRecorder(), seed_file=SEED_PATH)

    assert caught.value.setting_name == "seed_password_customer"


async def test_seed_refuses_a_missing_file(worker_database: WorkerDatabase) -> None:
    with pytest.raises(SeedFileInvalidError):
        await seed(
            seed_settings(worker_database),
            RecordingEventRecorder(),
            seed_file=BACKEND_ROOT / "seed" / "missing.json",
        )


@pytest.mark.parametrize(
    "path_to_value",
    [
        ("accounts", 0, "login_name"),
        ("commerce", "orders", 0, "order_id"),
        ("commerce", "orders", 0, "transaction_id"),
    ],
    ids=["login-name-not-normalized", "order-id-format", "transaction-id-format"],
)
def test_seed_file_with_a_value_outside_its_format_is_refused(
    tmp_path: Path, path_to_value: tuple[str | int, ...]
) -> None:
    document = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    parent = reduce(operator.getitem, path_to_value[:-1], document)
    parent[path_to_value[-1]] = "NOT VALID"
    seed_file = tmp_path / "invalid-seed.json"
    seed_file.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(SeedFileInvalidError):
        load_seed_document(seed_file)

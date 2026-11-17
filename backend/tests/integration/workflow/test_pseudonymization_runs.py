"""`PseudonymizeMessage` against PostgreSQL 17: one map per ticket, nothing kept of a failure.

The first successful run inserts the map, and a later run only compares. A run that fails
keeps no map row, and its failure is audited in a transaction of its own, so a value never
gets two pseudonyms (ADR-0010, Storage and lifecycle, items 2 to 4). A storage error is no
pseudonymization failure: it rolls everything back and audits nothing (backend ticket
workflow design, Pseudonymization, item 3).
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from supportiq_backend.accounts import CustomerId
from supportiq_backend.audit.adapters.audit_log import PostgresAuditLog
from supportiq_backend.commerce import OrderId
from supportiq_backend.commerce.adapters.customer_records import PostgresCustomerRecords
from supportiq_backend.platform import DatabaseUnavailableError
from supportiq_backend.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_session_factory,
)
from supportiq_backend.pseudonymization import (
    Detector,
    DetectorError,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    MapTicketId,
    MessageToPseudonymize,
    PatternDetector,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
)
from supportiq_backend.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from supportiq_backend.pseudonymization.domain import (
    Detection,
    KnownValue,
    PseudonymEntry,
    PseudonymMapStore,
    StoredMapDiffersError,
)
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.schema.statements import run_statement
from tests.unit.platform.fakes import (
    FakeClock,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)

pytestmark = pytest.mark.anyio

DETECTORS: tuple[Detector, ...] = (
    LiteralPlaceholderDetector(),
    KnownValueDetector(),
    PatternDetector(),
)
COUNT_MAP_ROWS = "SELECT count(*) FROM pseudonym_map_entries WHERE ticket_id = :ticket_id"
COUNT_AUDIT_ENTRIES = (
    "SELECT count(*) FROM audit_log_entries"
    " WHERE ticket_id = :ticket_id AND event_type = 'message.pseudonymized'"
)
FAILURE_REASON = (
    "SELECT data ->> 'failure_reason' FROM audit_log_entries"
    " WHERE ticket_id = :ticket_id AND event_type = 'message.pseudonymized'"
)
INSERT_MAP_ROW = (
    "INSERT INTO pseudonym_map_entries"
    " (ticket_id, pseudonym, pseudonym_type, original_value, created_at)"
    " VALUES (:ticket_id, '[NAME_1]', 'NAME', 'Minh Le', now())"
)
# The pseudonyms of the seeded message: the name, the order ID, and the email.
SEEDED_PSEUDONYM_COUNT = 3


@dataclass(frozen=True, slots=True)
class FailingDetector:
    """A detector that cannot run."""

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Raise the error of a detector that cannot run."""
        del message, known_values
        raise DetectorError


@dataclass(frozen=True, slots=True)
class FailingAfterInsert:
    """A map store whose insert writes its rows and then loses the connection."""

    inner: PostgresPseudonymMapStore

    async def insert_map(
        self, ticket_id: MapTicketId, entries: tuple[PseudonymEntry, ...], created_at: datetime
    ) -> None:
        """Insert the rows, then fail as a lost connection does."""
        await self.inner.insert_map(ticket_id, entries, created_at)
        raise DatabaseUnavailableError

    async def load_entries(self, ticket_id: MapTicketId) -> tuple[PseudonymEntry, ...]:
        """Load the map through the real store."""
        return await self.inner.load_entries(ticket_id)


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


def as_is(store: PostgresPseudonymMapStore) -> PseudonymMapStore:
    return store


def build_use_case(
    app_engine: AsyncEngine,
    *,
    detectors: tuple[Detector, ...] = DETECTORS,
    map_store: Callable[[PostgresPseudonymMapStore], PseudonymMapStore] = as_is,
) -> PseudonymizeMessage:
    def build_stores(session: AsyncSession) -> PseudonymizationStores:
        return PseudonymizationStores(
            map_store(PostgresPseudonymMapStore(session)),
            PostgresCustomerRecords(session),
            PostgresAuditLog(session),
        )

    return PseudonymizeMessage(
        SqlAlchemyTransactionRunner(create_session_factory(app_engine), build_stores),
        PseudonymizationPorts(
            detectors=detectors,
            clock=FakeClock(),
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=RecordingEventRecorder(),
            steps=RecordingStepTracer(),
        ),
    )


async def seed_message(builder: DatabaseBuilder) -> MessageToPseudonymize:
    _account_id, customer_id = await builder.customer_account()
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id)
    email = await builder.scalar(
        "SELECT email FROM customers WHERE customer_id = :customer_id", customer_id=customer_id
    )
    return MessageToPseudonymize(
        MapTicketId(ticket_id),
        f"I am Lan Tran, order {order_id}, mail {email}.",
        CustomerId(str(customer_id)),
        OrderId(order_id),
    )


async def test_the_first_run_stores_the_map_and_audits_the_outcome(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)

    text = await build_use_case(app_engine).pseudonymize(message)

    assert text == "I am [NAME_1], order [ORDER_ID_1], mail [EMAIL_1]."
    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == (
        SEEDED_PSEUDONYM_COUNT
    )
    assert await builder.scalar(COUNT_AUDIT_ENTRIES, ticket_id=message.ticket_id) == 1


async def test_a_later_run_reads_the_map_and_gives_the_same_text(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)
    use_case = build_use_case(app_engine)
    first = await use_case.pseudonymize(message)

    second = await use_case.pseudonymize(message)

    assert second == first
    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == (
        SEEDED_PSEUDONYM_COUNT
    )


async def test_a_stored_map_that_differs_keeps_no_row_of_the_failed_run(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)
    await run_statement(owner_engine, INSERT_MAP_ROW, ticket_id=message.ticket_id)

    with pytest.raises(StoredMapDiffersError):
        await build_use_case(app_engine).pseudonymize(message)

    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == 1
    assert await builder.scalar(FAILURE_REASON, ticket_id=message.ticket_id) == (
        "stored_map_differs"
    )


async def test_a_detector_failure_keeps_no_map_row_and_audits_the_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)

    with pytest.raises(DetectorError):
        await build_use_case(app_engine, detectors=(*DETECTORS, FailingDetector())).pseudonymize(
            message
        )

    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == 0
    assert await builder.scalar(FAILURE_REASON, ticket_id=message.ticket_id) == "detector_error"


async def test_an_insert_that_fails_rolls_the_map_back_and_audits_nothing(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)

    with pytest.raises(DatabaseUnavailableError):
        await build_use_case(app_engine, map_store=FailingAfterInsert).pseudonymize(message)

    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == 0
    assert await builder.scalar(COUNT_AUDIT_ENTRIES, ticket_id=message.ticket_id) == 0


async def test_two_first_runs_at_the_same_time_keep_one_map(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    message = await seed_message(builder)
    use_case = build_use_case(app_engine)

    first, second = await asyncio.gather(
        use_case.pseudonymize(message), use_case.pseudonymize(message)
    )

    assert first == second
    assert await builder.scalar(COUNT_MAP_ROWS, ticket_id=message.ticket_id) == (
        SEEDED_PSEUDONYM_COUNT
    )

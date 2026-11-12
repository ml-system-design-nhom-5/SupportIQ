"""Migration `r0003` against PostgreSQL 17: triggers, privileges, and the claim statement.

What no privilege can express is refused by the database for every role: a final suggestion
part never changes, a request is written once, and a ticket status changes only along the
state machine (backend ticket workflow design, Tables). Two claims never get the same job
(ADR-0011, item 2).
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionJobStore
from tests.integration.builders import DatabaseBuilder
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
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
INSERT_SUGGESTION = (
    "INSERT INTO suggestions (suggestion_id, ticket_id, trigger, created_at, trace_id)"
    " VALUES (:suggestion_id, :ticket_id, 'ticket_created', now(), :trace_id)"
)
INSERT_PART = (
    "INSERT INTO suggestion_parts (suggestion_id, part, status, reason_codes, completed_at)"
    " VALUES (:suggestion_id, :part, :status, '[]', :completed_at)"
)
INSERT_JOB = (
    "INSERT INTO suggestion_jobs (suggestion_id, state, attempt_number, created_at, updated_at)"
    " VALUES (:suggestion_id, 'queued', 0, :created_at, :created_at)"
)


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine_raw(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_raw_app_engine(worker_database)
    yield engine
    await engine.dispose()


async def insert_suggestion(
    owner_engine: AsyncEngine, builder: DatabaseBuilder, *, status: str = "pending"
) -> tuple[str, UUID]:
    _account_id, customer_id = await builder.customer_account()
    order_id = await builder.order_of_one_product(customer_id)
    ticket_id = await builder.ticket(customer_id, order_id)
    suggestion_id = builder.next_uuid()
    await run_statement(
        owner_engine,
        INSERT_SUGGESTION,
        suggestion_id=suggestion_id,
        ticket_id=ticket_id,
        trace_id=TRACE_ID,
    )
    await run_statement(
        owner_engine,
        INSERT_PART,
        suggestion_id=suggestion_id,
        part="analysis",
        status=status,
        completed_at=None if status == "pending" else FAKE_CLOCK_START,
    )
    await run_statement(
        owner_engine, INSERT_JOB, suggestion_id=suggestion_id, created_at=builder.next_time()
    )
    return ticket_id, suggestion_id


async def test_a_final_part_is_never_changed(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    _ticket_id, suggestion_id = await insert_suggestion(owner_engine, builder, status="ready")

    sqlstate = await sqlstate_of_refusal(
        owner_engine,
        "UPDATE suggestion_parts SET status = 'unavailable' WHERE suggestion_id = :suggestion_id",
        suggestion_id=suggestion_id,
    )

    assert sqlstate == CHECK_VIOLATION


async def test_a_request_is_written_once(
    owner_engine: AsyncEngine, app_engine_raw: AsyncEngine, builder: DatabaseBuilder
) -> None:
    _ticket_id, suggestion_id = await insert_suggestion(owner_engine, builder)
    write = "UPDATE suggestions SET request = :request WHERE suggestion_id = :suggestion_id"
    await run_statement(
        app_engine_raw, write, request='{"message": "a"}', suggestion_id=suggestion_id
    )

    sqlstate = await sqlstate_of_refusal(
        app_engine_raw, write, request='{"message": "b"}', suggestion_id=suggestion_id
    )

    assert sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    ("before", "after"),
    [("closed", "open"), ("escalated", "awaiting_approval"), ("awaiting_approval", "open")],
)
async def test_a_ticket_status_changes_only_along_the_state_machine(
    owner_engine: AsyncEngine, builder: DatabaseBuilder, before: str, after: str
) -> None:
    ticket_id, _suggestion_id = await insert_suggestion(owner_engine, builder)
    await run_statement(
        owner_engine,
        "UPDATE tickets SET status = :status WHERE ticket_id = :ticket_id",
        status=before,
        ticket_id=ticket_id,
    )

    sqlstate = await sqlstate_of_refusal(
        owner_engine,
        "UPDATE tickets SET status = :status WHERE ticket_id = :ticket_id",
        status=after,
        ticket_id=ticket_id,
    )

    assert sqlstate == CHECK_VIOLATION


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE replies SET body = 'x'",
        "DELETE FROM staff_decisions",
        "UPDATE pseudonym_map_entries SET original_value = 'x'",
        "DELETE FROM pseudonym_map_entries",
        "UPDATE suggestions SET trigger = 'retry'",
        "UPDATE suggestion_parts SET suggestion_id = gen_random_uuid()",
        "DELETE FROM suggestion_jobs",
        "UPDATE escalations SET note = 'x'",
        "UPDATE reply_proposals SET body = 'x'",
    ],
)
async def test_supportiq_app_has_no_privilege_beyond_the_design(
    app_engine_raw: AsyncEngine, statement: str
) -> None:
    sqlstate = await sqlstate_of_refusal(app_engine_raw, statement)

    assert sqlstate == INSUFFICIENT_PRIVILEGE


async def test_a_second_reply_of_one_ticket_is_impossible(
    owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id, _suggestion_id = await insert_suggestion(owner_engine, builder)
    account_id, _customer_id = await builder.customer_account(display_name="Staff One")
    insert_reply = (
        "INSERT INTO replies (reply_id, ticket_id, basis, acknowledged_warning_ids,"
        " staff_reason_codes, sent_by_account_id, sent_at, body)"
        " VALUES (gen_random_uuid(), :ticket_id, 'no_ai_draft', '[]', '[]', :account_id,"
        " now(), 'Hello')"
    )
    await run_statement(owner_engine, insert_reply, ticket_id=ticket_id, account_id=account_id)

    sqlstate = await sqlstate_of_refusal(
        owner_engine, insert_reply, ticket_id=ticket_id, account_id=account_id
    )

    assert sqlstate == UNIQUE_VIOLATION


async def test_two_claims_never_get_the_same_job(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    await insert_suggestion(owner_engine, builder)
    await insert_suggestion(owner_engine, builder)
    sessions = create_session_factory(app_engine)
    lease_expires_at = FAKE_CLOCK_START + timedelta(milliseconds=15_000)

    async with sessions() as first, sessions() as second:
        first_job = await PostgresSuggestionJobStore(first).claim_next(
            FAKE_CLOCK_START, lease_expires_at
        )
        second_job = await PostgresSuggestionJobStore(second).claim_next(
            FAKE_CLOCK_START, lease_expires_at
        )
        await first.commit()
        await second.commit()

    assert first_job is not None
    assert second_job is not None
    assert first_job.suggestion_id != second_job.suggestion_id
    assert first_job.attempt_number == second_job.attempt_number == 1


async def test_an_expired_lease_is_claimed_again_with_the_next_attempt(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    await insert_suggestion(owner_engine, builder)
    sessions = create_session_factory(app_engine)
    lease_ms = timedelta(milliseconds=15_000)
    async with sessions() as session:
        await PostgresSuggestionJobStore(session).claim_next(
            FAKE_CLOCK_START, FAKE_CLOCK_START + lease_ms
        )
        await session.commit()
    later = FAKE_CLOCK_START + lease_ms

    async with sessions() as session:
        again = await PostgresSuggestionJobStore(session).claim_next(later, later + lease_ms)
        await session.commit()

    assert again is not None
    assert again.attempt_number == 1 + 1

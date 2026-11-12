"""The suggestion stores in the transactions of a job, against PostgreSQL 17 (TEST-01, ERR-22).

A job runs with the PostgreSQL stores of the composition root and a fake for every other port.
Only these runs show the rules that need several stores at once: a result is stored only while
its attempt and its suggestion are current, the authority flag is set in the transaction that
stores the part, a job without attempts left ends unavailable without a call, and storing a
result locks the ticket, then the job, then the parts (backend ticket workflow design,
Suggestions and the job queue; ADR-0011, items 4 and 6). A wait for a lock polls `pg_locks` and
never sleeps (TEST-14).
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import AccountId
from supportiq_backend.composition_root.suggestions_wiring import build_job_stores
from supportiq_backend.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_session_factory,
)
from supportiq_backend.suggestions import (
    AiService,
    ClaimedJob,
    JobRunnerPorts,
    ReceivedDraftOutcome,
    SuggestionId,
    SuggestionJobRunner,
    SuggestionRequest,
    SuggestionStart,
    SuggestionTicketId,
    SuggestionTrigger,
)
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionJobStore
from supportiq_backend.tickets.adapters.console_store import PostgresTicketLinks
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.schema.statements import sqlstate_of_refusal
from tests.integration.workflow.workflow_rows import (
    LEASE,
    QUEUE_SETTINGS,
    claim_job,
    insert_ticket,
    leave_job_running,
    load_authority_flag,
    load_job_state,
    load_part_reason_codes,
    load_part_statuses,
    received_analysis_example,
    received_draft_example,
    start_suggestion,
    ticket_created,
    wait_until_row_lock_waits,
)
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeClock,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.suggestions.fakes import FakeAiService, FakePseudonymizer

pytestmark = pytest.mark.anyio

NOW = FAKE_CLOCK_START
FIRST_ATTEMPT = 1
SECOND_ATTEMPT = 2
# What `sqlstate_of_refusal` returns for a statement that ran, and the SQLSTATE of NOWAIT on a
# row that another transaction holds.
ACCEPTED = "accepted"
LOCK_NOT_AVAILABLE = "55P03"
LOCK_TICKET_NOWAIT = "SELECT 1 FROM tickets WHERE ticket_id = :ticket_id FOR UPDATE NOWAIT"
LOCK_JOB_NOWAIT = (
    "SELECT 1 FROM suggestion_jobs WHERE suggestion_id = :suggestion_id FOR UPDATE NOWAIT"
)
LOCK_PARTS_NOWAIT = (
    "SELECT 1 FROM suggestion_parts WHERE suggestion_id = :suggestion_id FOR UPDATE NOWAIT"
)
STORED_PARTS = {"analysis": "ready", "draft": "draft_ready"}
BOTH_PENDING = {"analysis": "pending", "draft": "pending"}
BOTH_CANCELLED = {"analysis": "cancelled", "draft": "cancelled"}


@dataclass(frozen=True, slots=True)
class ClaimedTicket:
    """A ticket whose first suggestion was claimed once.

    Attributes:
        ticket_id: The ticket.
        suggestion_id: Its current suggestion.
        job: The claim.
    """

    ticket_id: SuggestionTicketId
    suggestion_id: SuggestionId
    job: ClaimedJob


@dataclass(slots=True)
class InterleavedAiService(FakeAiService):
    """An ai-service whose draft call first lets another transaction act, then answers.

    Attributes:
        meanwhile: What another replica or request does while the call runs.
    """

    meanwhile: Callable[[], Awaitable[object]] = field(kw_only=True)

    async def draft(self, request: SuggestionRequest) -> ReceivedDraftOutcome:
        """Run `meanwhile`, then answer the draft call."""
        await self.meanwhile()
        return await FakeAiService.draft(self, request)


@pytest.fixture
async def owner_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    engine = create_owner_engine(worker_database)
    yield engine
    await engine.dispose()


async def claim_new_ticket(engine: AsyncEngine, builder: DatabaseBuilder) -> ClaimedTicket:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(engine, builder, ticket_created(ticket_id))
    return ClaimedTicket(ticket_id, suggestion_id, await claim_job(engine, NOW))


def build_job_runner(engine: AsyncEngine, ai_service: AiService) -> SuggestionJobRunner:
    return SuggestionJobRunner(
        SqlAlchemyTransactionRunner(create_session_factory(engine), build_job_stores),
        JobRunnerPorts(
            pseudonymizer=FakePseudonymizer(),
            ai_service=ai_service,
            clock=FakeClock(),
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=RecordingEventRecorder(),
            steps=RecordingStepTracer(),
        ),
        QUEUE_SETTINGS,
    )


async def test_a_job_of_the_current_attempt_stores_both_parts_and_ends(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)
    ai_service = FakeAiService(
        analysis_result=received_analysis_example("draft"),
        draft_result=received_draft_example("draft-ready"),
    )

    await build_job_runner(app_engine, ai_service).run(claimed.job)

    assert await load_part_statuses(builder, claimed.suggestion_id) == STORED_PARTS
    assert await load_job_state(builder, claimed.suggestion_id) == {
        "state": "done",
        "attempt_number": FIRST_ATTEMPT,
    }


async def test_a_result_that_requires_authority_sets_the_flag_with_the_part(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)
    ai_service = FakeAiService(draft_result=received_draft_example("requires-authority"))

    await build_job_runner(app_engine, ai_service).run(claimed.job)

    assert await load_authority_flag(builder, claimed.ticket_id) is True
    assert await load_part_statuses(builder, claimed.suggestion_id) == STORED_PARTS


async def test_a_result_of_an_attempt_claimed_again_meanwhile_is_discarded(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)
    ai_service = InterleavedAiService(
        draft_result=received_draft_example("requires-authority"),
        meanwhile=lambda: claim_job(app_engine, NOW + LEASE),
    )

    await build_job_runner(app_engine, ai_service).run(claimed.job)

    assert await load_part_statuses(builder, claimed.suggestion_id) == BOTH_PENDING
    assert await load_authority_flag(builder, claimed.ticket_id) is False
    assert await load_job_state(builder, claimed.suggestion_id) == {
        "state": "running",
        "attempt_number": SECOND_ATTEMPT,
    }


async def test_a_result_of_a_superseded_suggestion_is_discarded(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)
    staff_id = AccountId(str(await builder.account(AccountSpec("staff"))))
    retry = SuggestionStart(claimed.ticket_id, SuggestionTrigger.RETRY, None, staff_id)
    ai_service = InterleavedAiService(
        draft_result=received_draft_example("requires-authority"),
        meanwhile=lambda: start_suggestion(app_engine, builder, retry),
    )

    await build_job_runner(app_engine, ai_service).run(claimed.job)

    assert await load_part_statuses(builder, claimed.suggestion_id) == BOTH_CANCELLED
    assert await load_authority_flag(builder, claimed.ticket_id) is False


async def test_a_job_without_attempts_left_ends_unavailable_without_a_call(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    await leave_job_running(
        owner_engine,
        suggestion_id,
        attempt_number=QUEUE_SETTINGS.max_attempts,
        lease_expires_at=NOW,
    )
    job = await claim_job(app_engine, NOW)
    ai_service = FakeAiService()

    await build_job_runner(app_engine, ai_service).run(job)

    assert await load_part_reason_codes(builder, suggestion_id) == {
        "analysis": ["ai_service_unavailable"],
        "draft": ["ai_service_unavailable"],
    }
    assert await load_job_state(builder, suggestion_id) == {
        "state": "done",
        "attempt_number": QUEUE_SETTINGS.max_attempts + 1,
    }
    assert ai_service.requests == ()


async def test_storing_a_result_waits_for_the_ticket_before_it_locks_the_job_or_the_parts(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)
    suggestion_key = UUID(claimed.suggestion_id)

    async with create_session_factory(app_engine)() as holder:
        ai_service = InterleavedAiService(
            draft_result=received_draft_example("draft-ready"),
            meanwhile=lambda: PostgresTicketLinks(holder).lock_ticket(claimed.ticket_id),
        )
        run = asyncio.create_task(build_job_runner(app_engine, ai_service).run(claimed.job))
        await wait_until_row_lock_waits(builder, 1, run)
        job_lock = await sqlstate_of_refusal(
            owner_engine, LOCK_JOB_NOWAIT, suggestion_id=suggestion_key
        )
        part_lock = await sqlstate_of_refusal(
            owner_engine, LOCK_PARTS_NOWAIT, suggestion_id=suggestion_key
        )
        await holder.commit()
    await run

    assert job_lock == part_lock == ACCEPTED
    assert await load_part_statuses(builder, claimed.suggestion_id) == STORED_PARTS


async def test_storing_a_result_holds_the_ticket_and_no_part_while_it_waits_for_the_job(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    claimed = await claim_new_ticket(app_engine, builder)

    async with create_session_factory(app_engine)() as holder:
        ai_service = InterleavedAiService(
            draft_result=received_draft_example("draft-ready"),
            meanwhile=lambda: PostgresSuggestionJobStore(holder).lock_job(claimed.suggestion_id),
        )
        run = asyncio.create_task(build_job_runner(app_engine, ai_service).run(claimed.job))
        await wait_until_row_lock_waits(builder, 1, run)
        ticket_lock = await sqlstate_of_refusal(
            owner_engine, LOCK_TICKET_NOWAIT, ticket_id=claimed.ticket_id
        )
        part_lock = await sqlstate_of_refusal(
            owner_engine, LOCK_PARTS_NOWAIT, suggestion_id=UUID(claimed.suggestion_id)
        )
        await holder.commit()
    await run

    assert ticket_lock == LOCK_NOT_AVAILABLE
    assert part_lock == ACCEPTED
    assert await load_part_statuses(builder, claimed.suggestion_id) == STORED_PARTS

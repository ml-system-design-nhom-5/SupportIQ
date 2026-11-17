"""The claim loop against PostgreSQL 17: which job it claims, and when (ADR-0011, item 2).

Each loop runs with the real `PostgresSuggestionJobStore` and a fake job runner that keeps the
jobs it ran, so no job pseudonymizes or calls ai-service. Each loop has its own fake clock, which
moves `poll_ms` at every poll wait instead of waiting, and every run is bounded, so no test
waits for real time or hangs (TEST-14). Jobs that a fake runner ran stay `running`, so the
tests about which job is claimed use a lease that no fake clock reaches during a test.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root.suggestions_wiring import build_claim_stores
from supportiq_backend.platform import MILLISECONDS_PER_SECOND
from supportiq_backend.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_database_engine,
    create_session_factory,
)
from supportiq_backend.suggestions import ClaimedJob, ClaimLoop, QueueSettings
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionJobStore
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import DESIGN_TIMEOUTS, WorkerDatabase
from tests.integration.workflow.workflow_rows import (
    LEASE,
    QUEUE_SETTINGS,
    build_new_suggestion,
    claim_job,
    insert_suggestion,
    insert_ticket,
    start_suggestion,
    ticket_created,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START, FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

# The longest a test may run its loops before it fails instead of hanging.
BOUND_MS = 10_000
# A lease that no fake clock reaches while a test runs: each poll wait moves a clock by
# `poll_ms`, and a year of waits is far more than any bounded test does.
LEASE_LONGER_THAN_THE_TEST_MS = 365 * 24 * 60 * 60 * MILLISECONDS_PER_SECOND
ONE_SLOT = replace(QUEUE_SETTINGS, workers_per_replica=1, lease_ms=LEASE_LONGER_THAN_THE_TEST_MS)
SLOTS_PER_LOOP = 2
TWO_SLOTS = replace(ONE_SLOT, workers_per_replica=SLOTS_PER_LOOP)
# The shortest poll wait: the claim after an empty one runs exactly one millisecond later.
SHORTEST_POLL_MS = 1
LEASE_BOUNDARY_SETTINGS = replace(QUEUE_SETTINGS, workers_per_replica=1, poll_ms=SHORTEST_POLL_MS)
FIRST_LEASE_EXPIRES_AT = FAKE_CLOCK_START + LEASE
JUST_BEFORE_THE_FIRST_LEASE_EXPIRES = FIRST_LEASE_EXPIRES_AT - timedelta(
    milliseconds=SHORTEST_POLL_MS
)
JOB_COUNT = 8
FIRST_ATTEMPT = 1
SECOND_ATTEMPT = 2
EARLY = FAKE_CLOCK_START + timedelta(minutes=1)
MIDDLE = FAKE_CLOCK_START + timedelta(minutes=2)
LATE = FAKE_CLOCK_START + timedelta(minutes=3)
JOB_CLAIMED_AT = "SELECT updated_at FROM suggestion_jobs"


@dataclass(slots=True)
class JobLedger:
    """Every job that the runners of a test ran, in order, shared by every loop of the test.

    Each runner holds its job until `held_until_count` jobs ran, so the first jobs all run at
    the same time. With fewer slots per loop than that count, two loops hold jobs at once.

    Attributes:
        expected_count: After how many jobs `every_job_ran` is set.
        held_until_count: How many jobs run before any runner returns.
        jobs: The jobs that ran, in order.
        every_job_ran: Set once `expected_count` jobs ran.
        enough_held: Set once `held_until_count` jobs ran.
    """

    expected_count: int
    held_until_count: int = 1
    jobs: list[ClaimedJob] = field(default_factory=list[ClaimedJob])
    every_job_ran: asyncio.Event = field(default_factory=asyncio.Event)
    enough_held: asyncio.Event = field(default_factory=asyncio.Event)

    async def report(self, job: ClaimedJob) -> None:
        """Keep a job that runs, and return once enough jobs ran.

        Args:
            job: The claimed job.
        """
        self.jobs.append(job)
        if len(self.jobs) >= self.held_until_count:
            self.enough_held.set()
        if len(self.jobs) >= self.expected_count:
            self.every_job_ran.set()
        await self.enough_held.wait()


@dataclass(slots=True)
class LedgerRunner:
    """The fake job runner of one loop: it keeps its jobs and reports each to the ledger."""

    ledger: JobLedger
    jobs: list[ClaimedJob] = field(default_factory=list[ClaimedJob])

    async def run(self, job: ClaimedJob) -> None:
        """Keep the job and report it, without running anything.

        Args:
            job: The claimed job.
        """
        self.jobs.append(job)
        await self.ledger.report(job)


# Sets a queued job `done` and returns a newer queued job, which stays claimable.
type EndJob = Callable[[AsyncEngine, DatabaseBuilder, ClaimedJob], Awaitable[ClaimedJob]]


@pytest.fixture
async def other_replica_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    """Connect as `supportiq_app` with an engine of its own, as a second replica does.

    Args:
        worker_database: The database of the worker.

    Yields:
        The engine, disposed after the test.
    """
    engine = create_database_engine(worker_database.app_url, DESIGN_TIMEOUTS, ca_file=None)
    yield engine
    await engine.dispose()


def build_loop(
    engine: AsyncEngine, runner: LedgerRunner, settings: QueueSettings, clock: FakeClock
) -> ClaimLoop:
    return ClaimLoop(
        SqlAlchemyTransactionRunner(create_session_factory(engine), build_claim_stores),
        runner,
        settings,
        clock,
        RecordingEventRecorder(),
    )


async def run_until_every_job_ran(ledger: JobLedger, *loops: ClaimLoop) -> None:
    async with asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND), asyncio.TaskGroup() as group:
        for loop in loops:
            group.create_task(loop.run())
        await ledger.every_job_ran.wait()
        for loop in loops:
            loop.stop()


async def queue_job(engine: AsyncEngine, builder: DatabaseBuilder) -> ClaimedJob:
    """Start the first suggestion of a new ticket; return its first claim, not made yet."""
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(engine, builder, ticket_created(ticket_id))
    return ClaimedJob(suggestion_id, ticket_id, FIRST_ATTEMPT)


async def queue_jobs(engine: AsyncEngine, builder: DatabaseBuilder, count: int) -> list[ClaimedJob]:
    return [await queue_job(engine, builder) for _number in range(count)]


async def queue_job_created_at(
    engine: AsyncEngine, builder: DatabaseBuilder, created_at: datetime
) -> ClaimedJob:
    """Insert a suggestion and its queued job with the given time and the next builder UUID."""
    suggestion = build_new_suggestion(builder, await insert_ticket(builder), created_at)
    await insert_suggestion(engine, suggestion)
    return ClaimedJob(suggestion.suggestion_id, suggestion.ticket_id, FIRST_ATTEMPT)


async def finish_after_its_claim(
    engine: AsyncEngine, builder: DatabaseBuilder, job: ClaimedJob
) -> ClaimedJob:
    """Claim the job and set it `done` as its runner does, then queue a job of another ticket.

    The lease of the done job stays set, and it expires before the job of the other ticket.
    """
    await claim_job(engine, FAKE_CLOCK_START)
    async with create_session_factory(engine)() as session:
        await PostgresSuggestionJobStore(session).finish_job(job.suggestion_id, FAKE_CLOCK_START)
        await session.commit()
    return await queue_job(engine, builder)


async def supersede_while_queued(
    engine: AsyncEngine, builder: DatabaseBuilder, job: ClaimedJob
) -> ClaimedJob:
    """Start a new suggestion of the job's ticket, which sets the queued job `done`."""
    suggestion_id = await start_suggestion(engine, builder, ticket_created(job.ticket_id))
    return ClaimedJob(suggestion_id, job.ticket_id, FIRST_ATTEMPT)


def sorted_by_suggestion(jobs: Iterable[ClaimedJob]) -> list[ClaimedJob]:
    return sorted(jobs, key=lambda job: job.suggestion_id)


async def test_two_claim_loops_at_the_same_time_never_run_the_same_job(
    app_engine: AsyncEngine, other_replica_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    queued = await queue_jobs(app_engine, builder, JOB_COUNT)
    # One job more than one loop has slots: the first jobs run in both loops at once.
    ledger = JobLedger(expected_count=JOB_COUNT, held_until_count=SLOTS_PER_LOOP + 1)
    first_runner = LedgerRunner(ledger)
    second_runner = LedgerRunner(ledger)
    first = build_loop(app_engine, first_runner, TWO_SLOTS, FakeClock())
    second = build_loop(other_replica_engine, second_runner, TWO_SLOTS, FakeClock())

    await run_until_every_job_ran(ledger, first, second)

    assert sorted_by_suggestion(ledger.jobs) == sorted_by_suggestion(queued)
    assert min(len(first_runner.jobs), len(second_runner.jobs)) >= 1


async def test_a_running_job_is_claimed_again_at_its_lease_expiry_not_one_millisecond_before(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    queued = await queue_job(app_engine, builder)
    await claim_job(app_engine, FAKE_CLOCK_START)
    ledger = JobLedger(expected_count=1)
    # The first claim runs one millisecond before the lease expires, the next one at expiry.
    clock = FakeClock(JUST_BEFORE_THE_FIRST_LEASE_EXPIRES)
    loop = build_loop(app_engine, LedgerRunner(ledger), LEASE_BOUNDARY_SETTINGS, clock)

    await run_until_every_job_ran(ledger, loop)

    claimed_at = await builder.scalar(JOB_CLAIMED_AT)
    assert ledger.jobs == [replace(queued, attempt_number=SECOND_ATTEMPT)]
    assert claimed_at == FIRST_LEASE_EXPIRES_AT


@pytest.mark.parametrize(
    "end_job",
    [
        pytest.param(finish_after_its_claim, id="finished-with-an-expired-lease"),
        pytest.param(supersede_while_queued, id="superseded-while-queued"),
    ],
)
async def test_a_done_job_is_never_claimed(
    app_engine: AsyncEngine, builder: DatabaseBuilder, end_job: EndJob
) -> None:
    done = await queue_job(app_engine, builder)
    queued = await end_job(app_engine, builder, done)
    ledger = JobLedger(expected_count=1)
    # The done job is the oldest, and the loop runs after its lease, if it had one, expired.
    clock = FakeClock(FIRST_LEASE_EXPIRES_AT)
    loop = build_loop(app_engine, LedgerRunner(ledger), ONE_SLOT, clock)

    await run_until_every_job_ran(ledger, loop)

    assert ledger.jobs == [queued]


async def test_the_oldest_job_by_creation_time_is_claimed_first(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    # Inserted out of time order, so the order of the suggestion IDs is not the time order.
    late = await queue_job_created_at(app_engine, builder, LATE)
    early = await queue_job_created_at(app_engine, builder, EARLY)
    middle = await queue_job_created_at(app_engine, builder, MIDDLE)
    ledger = JobLedger(expected_count=3)
    loop = build_loop(app_engine, LedgerRunner(ledger), ONE_SLOT, FakeClock())

    await run_until_every_job_ran(ledger, loop)

    assert ledger.jobs == [early, middle, late]

"""Tests of the claim loop: it runs claimed jobs, survives failures, and cancels old calls."""

import asyncio
from dataclasses import dataclass, field

import pytest

from app.platform import (
    MILLISECONDS_PER_SECOND,
    DatabaseUnavailableError,
    EventName,
)
from app.suggestions import (
    ClaimedJob,
    ClaimLoop,
    ClaimStores,
    JobState,
    QueueSettings,
    SuggestionId,
)
from tests.unit.platform.fakes import FakeClock, FakeTransactionRunner, RecordingEventRecorder
from tests.unit.suggestions.builders import SUGGESTION_ID, TICKET_ID, build_suggestion
from tests.unit.suggestions.fakes import FakeSuggestionData, FakeSuggestionJobStore

SETTINGS = QueueSettings(workers_per_replica=2, lease_ms=15_000, max_attempts=3, poll_ms=500)
NEW_SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000099")
FAILED = EventName.SUGGESTION_JOB_FAILED
# The longest a test may run its loop before it fails instead of hanging; a guard, not a wait.
BOUND_MS = 5_000


@dataclass(slots=True)
class RecordingRunner:
    """A job runner that keeps the jobs it ran and stops the loop after the last one."""

    loop: ClaimLoop | None = None
    jobs: list[ClaimedJob] = field(default_factory=list[ClaimedJob])
    failure: Exception | None = None

    async def run(self, job: ClaimedJob) -> None:
        """Keep the job, fail when chosen, and stop the loop."""
        self.jobs.append(job)
        if self.loop is not None:
            self.loop.stop()
        if self.failure is not None:
            raise self.failure


def build_loop(
    runner: RecordingRunner, jobs: FakeSuggestionJobStore, events: RecordingEventRecorder
) -> ClaimLoop:
    loop = ClaimLoop(
        FakeTransactionRunner(ClaimStores(jobs)),
        runner,
        SETTINGS,
        FakeClock(),
        events,
    )
    runner.loop = loop
    return loop


def queued_jobs() -> FakeSuggestionJobStore:
    data = FakeSuggestionData()
    data.add(build_suggestion())
    return FakeSuggestionJobStore(data)


def bounded() -> asyncio.Timeout:
    return asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND)


@pytest.mark.anyio
async def test_the_loop_claims_and_runs_a_queued_job() -> None:
    runner = RecordingRunner()
    events = RecordingEventRecorder()
    loop = build_loop(runner, queued_jobs(), events)

    async with bounded():
        await loop.run()

    assert runner.jobs == [ClaimedJob(SUGGESTION_ID, TICKET_ID, 1)]
    assert EventName.SUGGESTION_JOB_CLAIMED in events.names()


# TODO(#43): this test and the next are the only ones that reach the failure path of a job, and the
# branch that ends its loop of errors is covered only in some test orders (TEST-15, TEST-17).
@pytest.mark.anyio
async def test_a_failing_job_is_logged_once_and_the_loop_survives() -> None:
    runner = RecordingRunner(failure=DatabaseUnavailableError())
    events = RecordingEventRecorder()
    loop = build_loop(runner, queued_jobs(), events)

    async with bounded():
        await loop.run()

    (failure,) = events.of(EventName.SUGGESTION_JOB_FAILED)
    assert failure.attributes["error_type"] == "DatabaseUnavailableError"


@pytest.mark.anyio
async def test_each_error_of_a_job_group_is_logged_with_its_own_type() -> None:
    grouped = ExceptionGroup("calls", [DatabaseUnavailableError(), ValueError("bad")])
    runner = RecordingRunner(failure=grouped)
    events = RecordingEventRecorder()
    loop = build_loop(runner, queued_jobs(), events)

    async with bounded():
        await loop.run()

    error_types = {event.attributes["error_type"] for event in events.of(FAILED)}
    assert error_types == {"DatabaseUnavailableError", "ValueError"}


@pytest.mark.anyio
async def test_a_claim_that_fails_with_any_error_is_logged_and_the_loop_goes_on() -> None:
    runner = RecordingRunner()
    events = RecordingEventRecorder()
    jobs = FakeSuggestionJobStore(claim_failure=RuntimeError("driver bug"))
    loop = build_loop(runner, jobs, events)

    async with bounded(), asyncio.TaskGroup() as group:
        task = group.create_task(loop.run())
        await asyncio.sleep(0)
        is_running = not task.done()
        loop.stop()

    (failure,) = events.of(FAILED)
    assert is_running
    assert failure.attributes["error_type"] == "RuntimeError"


@pytest.mark.anyio
async def test_a_failing_claim_is_logged_and_the_loop_waits() -> None:
    runner = RecordingRunner()
    events = RecordingEventRecorder()
    jobs = FakeSuggestionJobStore(claim_failure=DatabaseUnavailableError())
    loop = build_loop(runner, jobs, events)

    async with bounded(), asyncio.TaskGroup() as group:
        group.create_task(loop.run())
        await asyncio.sleep(0)
        loop.stop()

    assert EventName.SUGGESTION_JOB_FAILED in events.names()
    assert runner.jobs == []


@pytest.mark.anyio
async def test_a_new_suggestion_cancels_the_running_call_of_an_older_one() -> None:
    started = asyncio.Event()
    events = RecordingEventRecorder()

    @dataclass(slots=True)
    class BlockingRunner:
        """A runner whose job waits until it is cancelled."""

        cancelled: list[ClaimedJob] = field(default_factory=list[ClaimedJob])

        async def run(self, job: ClaimedJob) -> None:
            """Wait for ever, and keep the job when it is cancelled."""
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.append(job)
                raise

    runner = BlockingRunner()
    loop = ClaimLoop(
        FakeTransactionRunner(ClaimStores(queued_jobs())),
        runner,
        SETTINGS,
        FakeClock(),
        events,
    )

    async with bounded(), asyncio.TaskGroup() as group:
        group.create_task(loop.run())
        await started.wait()
        loop.notify_new_suggestion(TICKET_ID, NEW_SUGGESTION_ID)
        await asyncio.sleep(0)
        loop.stop()

    assert runner.cancelled == [ClaimedJob(SUGGESTION_ID, TICKET_ID, 1)]
    assert EventName.SUGGESTION_PART_CANCELLED in events.names()


@pytest.mark.anyio
async def test_a_job_claimed_again_after_its_lease_cancels_its_earlier_attempt() -> None:
    jobs = queued_jobs()
    events = RecordingEventRecorder()
    attempts: list[int] = []
    cancelled: list[int] = []
    second_started = asyncio.Event()

    @dataclass(slots=True)
    class SlowRunner:
        """A runner whose first attempt outlives its lease."""

        async def run(self, job: ClaimedJob) -> None:
            """Block the first attempt; end the second at once."""
            attempts.append(job.attempt_number)
            if job.attempt_number > 1:
                second_started.set()
                return
            # The lease of the first attempt expires while it runs.
            jobs.data.jobs[SUGGESTION_ID].state = JobState.QUEUED
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(job.attempt_number)
                raise

    loop = ClaimLoop(
        FakeTransactionRunner(ClaimStores(jobs)), SlowRunner(), SETTINGS, FakeClock(), events
    )

    async with bounded(), asyncio.TaskGroup() as group:
        group.create_task(loop.run())
        await second_started.wait()
        loop.stop()

    assert attempts == [1, 2]
    assert cancelled == [1]


@pytest.mark.anyio
async def test_a_cancelled_earlier_attempt_keeps_the_running_entry_of_the_new_attempt() -> None:
    jobs = queued_jobs()
    events = RecordingEventRecorder()
    cancelled: list[int] = []
    second_started = asyncio.Event()
    first_cancelled = asyncio.Event()
    release = asyncio.Event()

    @dataclass(slots=True)
    class ReclaimedRunner:
        """A runner whose attempts wait for the release; the first one outlives its lease."""

        async def run(self, job: ClaimedJob) -> None:
            """Block the attempt, and mark when the second starts and the first is cancelled."""
            if job.attempt_number > 1:
                second_started.set()
            else:
                # The lease of the first attempt expires while it runs.
                jobs.data.jobs[SUGGESTION_ID].state = JobState.QUEUED
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.append(job.attempt_number)
                if job.attempt_number == 1:
                    first_cancelled.set()
                raise

    loop = ClaimLoop(
        FakeTransactionRunner(ClaimStores(jobs)), ReclaimedRunner(), SETTINGS, FakeClock(), events
    )

    async with bounded(), asyncio.TaskGroup() as group:
        group.create_task(loop.run())
        await second_started.wait()
        await first_cancelled.wait()
        # Only the running entry of the second attempt lets the new suggestion cancel it.
        loop.notify_new_suggestion(TICKET_ID, NEW_SUGGESTION_ID)
        # An attempt that the notification missed ends here instead of blocking the stop.
        release.set()
        loop.stop()

    (cancellation,) = events.of(EventName.SUGGESTION_PART_CANCELLED)
    assert cancelled == [1, 2]
    assert cancellation.attributes == {"ticket_id": TICKET_ID, "suggestion_id": SUGGESTION_ID}

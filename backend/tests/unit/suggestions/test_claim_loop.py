"""Tests of the claim loop: it runs claimed jobs, survives failures, and cancels old calls."""

import asyncio
from dataclasses import dataclass, field

import pytest

from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.suggestions import (
    ClaimedJob,
    ClaimLoop,
    ClaimStores,
    QueueSettings,
    SuggestionId,
)
from tests.unit.platform.fakes import FakeClock, FakeTransactionRunner, RecordingEventRecorder
from tests.unit.suggestions.builders import SUGGESTION_ID, TICKET_ID, build_suggestion
from tests.unit.suggestions.fakes import FakeSuggestionData, FakeSuggestionJobStore

SETTINGS = QueueSettings(workers_per_replica=2, lease_ms=15_000, max_attempts=3, poll_ms=500)
NEW_SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000099")


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


@pytest.mark.anyio
async def test_the_loop_claims_and_runs_a_queued_job() -> None:
    runner = RecordingRunner()
    events = RecordingEventRecorder()
    loop = build_loop(runner, queued_jobs(), events)

    await loop.run()

    assert runner.jobs == [ClaimedJob(SUGGESTION_ID, TICKET_ID, 1)]
    assert EventName.SUGGESTION_JOB_CLAIMED in events.names()


@pytest.mark.anyio
async def test_a_failing_job_is_logged_once_and_the_loop_survives() -> None:
    runner = RecordingRunner(failure=DatabaseUnavailableError())
    events = RecordingEventRecorder()
    loop = build_loop(runner, queued_jobs(), events)

    await loop.run()

    (failure,) = events.of(EventName.SUGGESTION_JOB_FAILED)
    assert failure.attributes["error_type"] == "DatabaseUnavailableError"


@pytest.mark.anyio
async def test_a_failing_claim_is_logged_and_the_loop_waits() -> None:
    runner = RecordingRunner()
    events = RecordingEventRecorder()
    jobs = FakeSuggestionJobStore(claim_failure=DatabaseUnavailableError())
    loop = build_loop(runner, jobs, events)

    async with asyncio.TaskGroup() as group:
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

    async with asyncio.TaskGroup() as group:
        group.create_task(loop.run())
        await started.wait()
        loop.notify_new_suggestion(TICKET_ID, NEW_SUGGESTION_ID)
        await asyncio.sleep(0)
        loop.stop()

    assert runner.cancelled == [ClaimedJob(SUGGESTION_ID, TICKET_ID, 1)]
    assert EventName.SUGGESTION_PART_CANCELLED in events.names()

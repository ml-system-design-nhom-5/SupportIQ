"""Tests of the claim loop doubles: one failed claim does not stop a test (TEST-14).

A claim can fail once when PostgreSQL is slow, for example on a loaded machine. The claim loop
then waits its poll interval and claims again. These tests run the claim loop over in-memory
stores with `WakeUpOnlyClock`, so a wait that never ends after a failed claim fails the bound
instead of hanging.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from app.platform import MILLISECONDS_PER_SECOND, DatabaseUnavailableError
from app.suggestions import ClaimedJob, ClaimLoop, ClaimStores, QueueSettings
from tests.integration.claim_loop_doubles import SignallingEventRecorder, WakeUpOnlyClock
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeTransactionRunner,
    RecordingEventRecorder,
)
from tests.unit.suggestions.builders import SUGGESTION_ID, build_suggestion
from tests.unit.suggestions.fakes import FakeSuggestionData, FakeSuggestionJobStore

pytestmark = pytest.mark.anyio

SETTINGS = QueueSettings(workers_per_replica=1, lease_ms=15_000, max_attempts=3, poll_ms=500)
FIRST_ATTEMPT = 1
# The longest a test may run its loop before it fails instead of hanging; a guard, not a wait.
BOUND_MS = 5_000


class FailingOnceJobStore(FakeSuggestionJobStore):
    """A job store whose first claim fails as a transient failure of PostgreSQL would."""

    async def claim_next(self, now: datetime, lease_expires_at: datetime) -> ClaimedJob | None:
        """Raise the failure once, then claim as the in-memory store does.

        Args:
            now: The time of the claim.
            lease_expires_at: The end of the lease of the claimed job.

        Returns:
            The claimed job, or None when no job is claimable.

        Raises:
            DatabaseUnavailableError: On the first claim.
        """
        failure, self.claim_failure = self.claim_failure, None
        if failure is not None:
            raise failure
        return await super().claim_next(now, lease_expires_at)


@dataclass(slots=True)
class StoppingRunner:
    """A job runner that keeps the jobs it ran and stops the loop."""

    loop: ClaimLoop | None = None
    jobs: list[ClaimedJob] = field(default_factory=list[ClaimedJob])

    async def run(self, job: ClaimedJob) -> None:
        """Keep the job and stop the loop."""
        self.jobs.append(job)
        if self.loop is not None:
            self.loop.stop()


async def test_a_job_runs_after_one_failed_claim_and_the_time_does_not_move() -> None:
    data = FakeSuggestionData()
    data.add(build_suggestion())
    jobs = FailingOnceJobStore(data, claim_failure=DatabaseUnavailableError())
    events = SignallingEventRecorder(RecordingEventRecorder())
    clock = WakeUpOnlyClock(events)
    runner = StoppingRunner()
    loop = ClaimLoop(FakeTransactionRunner(ClaimStores(jobs)), runner, SETTINGS, clock, events)
    runner.loop = loop

    async with asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND):
        await loop.run()

    assert events.failed_claim_count() == 1
    assert [(job.suggestion_id, job.attempt_number) for job in runner.jobs] == [
        (SUGGESTION_ID, FIRST_ATTEMPT)
    ]
    assert clock.now() == FAKE_CLOCK_START

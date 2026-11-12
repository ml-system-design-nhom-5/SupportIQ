"""The claim loop of one replica (ADR-0011, Suggestion job queue; ARCH-41).

While a slot is free, the loop claims the oldest claimable job in one statement and runs it.
When nothing is claimable, it sleeps `suggestion_queue_poll_ms`, or less when a use case of
this replica wakes it after a commit. The wake-up holds no state: a lost one only delays the
job until the next poll. Nothing re-queues jobs at startup: an expired lease recovers the jobs
of a stopped replica.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from supportiq_backend.platform import (
    BackendError,
    Clock,
    EventName,
    EventRecorder,
    TransactionRunner,
)
from supportiq_backend.suggestions.domain import (
    ClaimedJob,
    QueueSettings,
    SuggestionId,
    SuggestionJobStore,
    SuggestionTicketId,
)


@dataclass(frozen=True, slots=True)
class ClaimStores:
    """The store of the claim transaction.

    Attributes:
        jobs: The suggestion jobs.
    """

    jobs: SuggestionJobStore


class JobRunner(Protocol):
    """Run one claimed job to its end; `SuggestionJobRunner` is the one of the replicas."""

    async def run(self, job: ClaimedJob) -> None:
        """Run the job.

        Args:
            job: The claimed job.
        """
        ...


@dataclass(frozen=True, slots=True)
class _RunningJob:
    ticket_id: SuggestionTicketId
    task: asyncio.Task[None]


class ClaimLoop:
    """Claim and run suggestion jobs with a fixed number of slots, until stopped."""

    def __init__(
        self,
        transactions: TransactionRunner[ClaimStores],
        runner: JobRunner,
        settings: QueueSettings,
        clock: Clock,
        events: EventRecorder,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the claim transactions.
            runner: Runs one claimed job.
            settings: The queue settings.
            clock: The clock, for leases and the poll interval.
            events: Where events are recorded.
        """
        self._transactions = transactions
        self._runner = runner
        self._settings = settings
        self._clock = clock
        self._events = events
        self._wake_up = asyncio.Event()
        self._stop = asyncio.Event()
        self._running: dict[SuggestionId, _RunningJob] = {}

    def notify_new_suggestion(
        self, ticket_id: SuggestionTicketId, suggestion_id: SuggestionId
    ) -> None:
        """Wake the loop and cancel the running calls of the ticket's older suggestions.

        A call that cannot be stopped finishes, and the job runner discards its result.

        Args:
            ticket_id: The ticket.
            suggestion_id: Its new current suggestion, committed already.
        """
        for running_id, running in tuple(self._running.items()):
            if running.ticket_id == ticket_id and running_id != suggestion_id:
                running.task.cancel()
                self._events.record(
                    EventName.SUGGESTION_PART_CANCELLED,
                    ticket_id=ticket_id,
                    suggestion_id=running_id,
                )
        self._wake_up.set()

    def stop(self) -> None:
        """Ask the loop to end; running jobs are cancelled and their leases recover them."""
        self._stop.set()
        self._wake_up.set()

    async def run(self) -> None:
        """Claim and run jobs until `stop` is called.

        Every failure inside the loop is logged once, and the loop goes on (LOG-17).
        """
        async with asyncio.TaskGroup() as group:
            while not self._stop.is_set():
                job = await self._claim() if self._has_free_slot() else None
                if job is None:
                    await self._wait_for_work()
                    continue
                task = group.create_task(self._run_job(job))
                self._running[job.suggestion_id] = _RunningJob(job.ticket_id, task)
            for running in self._running.values():
                running.task.cancel()

    def _has_free_slot(self) -> bool:
        return len(self._running) < self._settings.workers_per_replica

    async def _claim(self) -> ClaimedJob | None:
        now = self._clock.now()
        try:
            async with self._transactions.begin() as transaction:
                job = await transaction.stores.jobs.claim_next(
                    now, now + timedelta(milliseconds=self._settings.lease_ms)
                )
                await transaction.commit()
        except BackendError as error:
            self._events.record(EventName.SUGGESTION_JOB_FAILED, error_type=type(error).__name__)
            return None
        if job is not None:
            self._events.record(
                EventName.SUGGESTION_JOB_CLAIMED,
                ticket_id=job.ticket_id,
                suggestion_id=job.suggestion_id,
                attempt_number=job.attempt_number,
            )
        return job

    async def _run_job(self, job: ClaimedJob) -> None:
        # The top-level runner of a job: it logs every failure once, and the job waits for its
        # lease, so the loop stays alive (PY-21, LOG-17).
        try:
            await self._runner.run(job)
        except Exception as error:
            self._events.record(
                EventName.SUGGESTION_JOB_FAILED,
                ticket_id=job.ticket_id,
                suggestion_id=job.suggestion_id,
                error_type=type(error).__name__,
            )
        finally:
            self._running.pop(job.suggestion_id, None)
            self._wake_up.set()

    async def _wait_for_work(self) -> None:
        async with asyncio.TaskGroup() as group:
            sleep = group.create_task(self._clock.sleep(self._settings.poll_ms))
            wake_up = group.create_task(self._wake_up.wait())
            await asyncio.wait((sleep, wake_up), return_when=asyncio.FIRST_COMPLETED)
            sleep.cancel()
            wake_up.cancel()
        self._wake_up.clear()

"""Suggestion jobs: one per suggestion, claimed under a lease (ADR-0011, Suggestion job queue)."""

from dataclasses import dataclass
from enum import StrEnum

from supportiq_backend.suggestions.domain.suggestions import SuggestionId, SuggestionTicketId


class JobState(StrEnum):
    """The state of a suggestion job, as `suggestion_jobs.state` holds it."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class QueueSettings:
    """The settings of the queue (backend ticket workflow design, Choice 3).

    Attributes:
        workers_per_replica: How many jobs one replica runs at once.
        lease_ms: How long a claim holds a job; longer than the draft timeout.
        max_attempts: How many claims a job gets before its pending parts end unavailable.
        poll_ms: How long the claim loop sleeps when nothing is claimable.
    """

    workers_per_replica: int
    lease_ms: int
    max_attempts: int
    poll_ms: int


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A job that this replica claimed, with the attempt that its results must match.

    Attributes:
        suggestion_id: The suggestion of the job.
        ticket_id: Its ticket.
        attempt_number: The attempt of this claim, from 1.
    """

    suggestion_id: SuggestionId
    ticket_id: SuggestionTicketId
    attempt_number: int


@dataclass(frozen=True, slots=True)
class LockedJob:
    """A job row locked in the transaction that stores a result (ERR-22).

    Attributes:
        state: The state of the job.
        attempt_number: The attempt of the latest claim.
    """

    state: JobState
    attempt_number: int

    def is_held_by(self, job: ClaimedJob) -> bool:
        """Tell whether a claim may still store results.

        Args:
            job: The claim.

        Returns:
            True when the job still runs under the same attempt.
        """
        return self.state is JobState.RUNNING and self.attempt_number == job.attempt_number

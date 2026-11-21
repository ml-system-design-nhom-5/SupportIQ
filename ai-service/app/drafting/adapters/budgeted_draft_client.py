"""The LLM step of `main` within its budget: bounded retries of one Gemini call (NFR-07).

The budget covers the whole step, retries and waits included, and is at most 10 seconds
(NFR-07, ERR-10). Each attempt gets the smaller of its own timeout and what remains of the
budget (ERR-09). Only a timeout, a connection error, a `502`, `503`, or `504`, or a rate limit
is retried (ERR-12). A retry waits the delay that Gemini asked for, or else an exponential
backoff with full jitter (ERR-13); a rate limit without a delay, a hard quota, or a wait
longer than the rest of the budget ends the step at once. When the step gives no reply, the
draft outcome says why, and the tokens of every answered attempt still count.

The budget is checked before each attempt and before each wait, but httpx applies the timeout
of an attempt to each phase of the request (connect, write, read, and pool), not to the whole
request. In the worst case one attempt, and so the whole step, runs past its time; `main`
stated the same limit (README.md, Known limits).
"""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.drafting.adapters.gemini import GeminiCallError, GeminiFailure
from app.drafting.domain import (
    DraftReply,
    DraftRequest,
    LlmCallError,
    LlmFailure,
    TokenUsage,
)


class _ModelCall(Protocol):
    def call(self, request: DraftRequest, timeout_seconds: float) -> DraftReply: ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The budget and the retries of the LLM step (settings: `llm_*`).

    Attributes:
        budget_seconds: The budget of the whole step, retries and waits included.
        attempt_timeout_seconds: The timeout of one attempt.
        max_attempts: The number of attempts, the first one included.
        backoff_base_seconds: The backoff before the second attempt; it doubles after.
        backoff_max_seconds: The longest backoff.
    """

    budget_seconds: float
    attempt_timeout_seconds: float
    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float


class BudgetedDraftWriter:
    """Implement the `DraftWriter` port with Gemini, within the budget of the LLM step."""

    def __init__(
        self,
        model: _ModelCall,
        policy: RetryPolicy,
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
        random: Callable[[], float],
    ) -> None:
        """Keep the model call, the policy, and the sources of time and randomness.

        Args:
            model: One call of the model.
            policy: The budget and the retries.
            monotonic: A clock in seconds that never goes back.
            sleep: Waits a number of seconds.
            random: A number from 0 up to 1, for the jitter of the backoff.
        """
        self._model = model
        self._policy = policy
        self._monotonic = monotonic
        self._sleep = sleep
        self._random = random

    def write(self, request: DraftRequest) -> DraftReply:
        """Draft one reply, retrying within the budget.

        Args:
            request: What the LLM receives.

        Returns:
            The draft before the grounding check, or the finding that the sources do not
            answer the request, with the tokens of every attempt.

        Raises:
            LlmCallError: The step gave no reply within the budget and the attempts.
        """
        policy = self._policy
        deadline = self._monotonic() + policy.budget_seconds
        usage: TokenUsage | None = None
        for attempt in range(policy.max_attempts):
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            try:
                reply = self._model.call(request, min(policy.attempt_timeout_seconds, remaining))
            except GeminiCallError as error:
                usage = _added(usage, error.usage)
                delay = self._retry_delay(error, attempt)
                last_attempt = attempt + 1 >= policy.max_attempts
                if delay is None or last_attempt or delay >= deadline - self._monotonic():
                    raise LlmCallError(error.failure.llm_failure, usage) from error
                self._sleep(delay)
            else:
                return _with_usage(reply, _added(usage, reply.usage))
        raise LlmCallError(LlmFailure.UNAVAILABLE, usage)

    def _retry_delay(self, error: GeminiCallError, attempt: int) -> float | None:
        # None when no attempt may follow.
        if not error.failure.retryable or error.retry_forbidden:
            return None
        if error.retry_after_seconds is not None:
            return error.retry_after_seconds
        if error.failure is GeminiFailure.RATE_LIMITED:
            # A rate limit without a delay is never retried at once, as in `main`.
            return None
        backoff = min(
            self._policy.backoff_base_seconds * 2**attempt, self._policy.backoff_max_seconds
        )
        return self._random() * backoff


def _added(total: TokenUsage | None, more: TokenUsage | None) -> TokenUsage | None:
    if total is None:
        return more
    if more is None:
        return total
    return total + more


def _with_usage(reply: DraftReply, usage: TokenUsage | None) -> DraftReply:
    # The reply carries the tokens of every attempt, not only those of the last one.
    return dataclasses.replace(reply, usage=usage or reply.usage)

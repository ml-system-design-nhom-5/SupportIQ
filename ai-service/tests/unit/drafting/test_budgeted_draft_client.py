"""The LLM step retries only retryable failures, in its budget, with injected jitter (ERR-13)."""

from collections.abc import Iterable
from dataclasses import dataclass, field

import pytest

from app.drafting import (
    DraftReply,
    DraftRequest,
    LlmCallError,
    LlmFailure,
    TokenUsage,
    UnanswerableRequest,
    WrittenDraft,
)
from app.drafting.adapters.budgeted_draft_client import (
    BudgetedDraftWriter,
    RetryPolicy,
)
from app.drafting.adapters.gemini import GeminiCallError, GeminiFailure
from tests.unit.drafting.fakes import REQUEST

POLICY = RetryPolicy(
    budget_seconds=10.0,
    attempt_timeout_seconds=5.0,
    max_attempts=2,
    backoff_base_seconds=0.25,
    backoff_max_seconds=2.0,
)
# The jitter of every test: half of the backoff.
JITTER = 0.5
USAGE = TokenUsage(input_token_count=12, output_token_count=10)
DRAFT = WrittenDraft(
    text="A draft [S1].", cited_source_ids=("S1",), is_clarification=False, usage=USAGE
)

type Outcome = DraftReply | GeminiCallError


@dataclass(slots=True)
class ScriptedModel:
    """A model call that answers from a script and takes a set time on a fake clock."""

    script: list[Outcome]
    seconds_per_call: float = 0.0
    now: float = 0.0
    timeouts: list[float] = field(default_factory=list[float])
    sleeps: list[float] = field(default_factory=list[float])

    def call(self, request: DraftRequest, timeout_seconds: float) -> DraftReply:
        """Answer the next entry of the script.

        Raises:
            GeminiCallError: The next entry of the script is an error.
        """
        del request
        self.timeouts.append(timeout_seconds)
        self.now += self.seconds_per_call
        outcome = self.script.pop(0)
        if isinstance(outcome, GeminiCallError):
            raise outcome
        return outcome

    def monotonic(self) -> float:
        """Return the time of the fake clock."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Keep the wait, and move the fake clock by it."""
        self.sleeps.append(seconds)
        self.now += seconds


def _writer(model: ScriptedModel, policy: RetryPolicy = POLICY) -> BudgetedDraftWriter:
    return BudgetedDraftWriter(model, policy, model.monotonic, model.sleep, lambda: JITTER)


def _model(outcomes: Iterable[Outcome], seconds_per_call: float = 0.0) -> ScriptedModel:
    return ScriptedModel(list(outcomes), seconds_per_call)


def _refusal(writer: BudgetedDraftWriter) -> LlmCallError:
    with pytest.raises(LlmCallError) as raised:
        writer.write(REQUEST)
    return raised.value


def test_a_first_answer_is_returned_with_one_attempt_of_its_own_timeout() -> None:
    model = _model([DRAFT])

    assert _writer(model).write(REQUEST) == DRAFT
    assert (model.timeouts, model.sleeps) == ([5.0], [])


@pytest.mark.parametrize("failure", [GeminiFailure.TIMEOUT, GeminiFailure.UNAVAILABLE])
def test_a_retryable_failure_is_retried_after_a_jittered_backoff(failure: GeminiFailure) -> None:
    model = _model([GeminiCallError(failure), DRAFT], seconds_per_call=5.0)

    assert _writer(model).write(REQUEST) == DRAFT
    # The second attempt gets what remains of the budget after the first one and the wait.
    assert model.sleeps == [JITTER * 0.25]
    assert model.timeouts == [5.0, pytest.approx(10.0 - 5.0 - JITTER * 0.25)]


def test_the_backoff_doubles_up_to_its_maximum() -> None:
    policy = RetryPolicy(10.0, 1.0, 3, backoff_base_seconds=1.5, backoff_max_seconds=2.0)
    model = _model([GeminiCallError(GeminiFailure.UNAVAILABLE)] * 2 + [DRAFT])

    _writer(model, policy).write(REQUEST)

    assert model.sleeps == [JITTER * 1.5, JITTER * 2.0]


def test_a_rate_limit_waits_the_delay_that_gemini_asks_for() -> None:
    model = _model([GeminiCallError(GeminiFailure.RATE_LIMITED, retry_after_seconds=3.0), DRAFT])

    assert _writer(model).write(REQUEST) == DRAFT
    assert model.sleeps == [3.0]


def test_a_rate_limit_without_a_delay_is_never_retried() -> None:
    model = _model([GeminiCallError(GeminiFailure.RATE_LIMITED), DRAFT])

    error = _refusal(_writer(model))

    assert (error.failure, model.sleeps, len(model.timeouts)) == (LlmFailure.UNAVAILABLE, [], 1)


def test_a_hard_quota_or_an_unreadable_delay_is_never_retried() -> None:
    model = _model(
        [GeminiCallError(GeminiFailure.RATE_LIMITED, retry_after_seconds=1.0, retry_forbidden=True)]
    )

    error = _refusal(_writer(model))

    assert (error.failure, model.sleeps) == (LlmFailure.UNAVAILABLE, [])


def test_a_delay_of_exactly_the_rest_of_the_budget_fails_at_once_without_waiting() -> None:
    model = _model(
        [GeminiCallError(GeminiFailure.UNAVAILABLE, retry_after_seconds=5.0), DRAFT],
        seconds_per_call=5.0,
    )

    error = _refusal(_writer(model))

    assert (error.failure, model.sleeps, len(model.timeouts)) == (LlmFailure.UNAVAILABLE, [], 1)


def test_a_delay_longer_than_the_rest_of_the_budget_fails_at_once_without_waiting() -> None:
    model = _model(
        [GeminiCallError(GeminiFailure.UNAVAILABLE, retry_after_seconds=6.0), DRAFT],
        seconds_per_call=5.0,
    )

    error = _refusal(_writer(model))

    assert (error.failure, model.sleeps, len(model.timeouts)) == (LlmFailure.UNAVAILABLE, [], 1)


@pytest.mark.parametrize(
    ("failure", "llm_failure"),
    [
        (GeminiFailure.REJECTED, LlmFailure.UNAVAILABLE),
        (GeminiFailure.EGRESS_REFUSED, LlmFailure.UNAVAILABLE),
        (GeminiFailure.INVALID_OUTPUT, LlmFailure.INVALID_OUTPUT),
    ],
)
def test_a_final_failure_is_never_retried(failure: GeminiFailure, llm_failure: LlmFailure) -> None:
    model = _model([GeminiCallError(failure, usage=USAGE), DRAFT])

    error = _refusal(_writer(model))

    assert (error.failure, error.usage, len(model.timeouts)) == (llm_failure, USAGE, 1)


def test_the_last_attempt_is_not_followed_by_a_wait() -> None:
    model = _model([GeminiCallError(GeminiFailure.TIMEOUT)] * 2)

    error = _refusal(_writer(model))

    assert (error.failure, len(model.timeouts), model.sleeps) == (
        LlmFailure.UNAVAILABLE,
        2,
        [JITTER * 0.25],
    )


def test_an_attempt_that_spends_the_whole_budget_leaves_no_second_attempt() -> None:
    model = _model([GeminiCallError(GeminiFailure.TIMEOUT), DRAFT], seconds_per_call=10.0)

    error = _refusal(_writer(model))

    assert (error.failure, len(model.timeouts), model.sleeps) == (LlmFailure.UNAVAILABLE, 1, [])


def test_the_tokens_of_every_answered_attempt_are_added() -> None:
    model = _model([GeminiCallError(GeminiFailure.TIMEOUT, usage=USAGE), DRAFT])

    reply = _writer(model).write(REQUEST)

    assert reply == WrittenDraft(
        text=DRAFT.text,
        cited_source_ids=DRAFT.cited_source_ids,
        is_clarification=False,
        usage=TokenUsage(input_token_count=24, output_token_count=20),
    )


def test_a_request_that_the_sources_do_not_answer_is_returned_with_its_tokens() -> None:
    unanswerable = UnanswerableRequest(usage=USAGE)

    assert _writer(_model([unanswerable])).write(REQUEST) == unanswerable


def test_a_wait_that_overruns_the_budget_leaves_no_attempt() -> None:
    model = _model([GeminiCallError(GeminiFailure.TIMEOUT), DRAFT])

    def late_sleep(seconds: float) -> None:
        # The process wakes up later than asked, after the end of the budget.
        model.sleeps.append(seconds)
        model.now += 20.0

    writer = BudgetedDraftWriter(model, POLICY, model.monotonic, late_sleep, lambda: JITTER)

    error = _refusal(writer)

    assert (error.failure, len(model.timeouts)) == (LlmFailure.UNAVAILABLE, 1)


def test_the_tokens_of_an_earlier_answered_attempt_stay_with_the_failure() -> None:
    model = _model(
        [
            GeminiCallError(GeminiFailure.TIMEOUT, usage=USAGE),
            GeminiCallError(GeminiFailure.TIMEOUT),
        ]
    )

    error = _refusal(_writer(model))

    assert (error.failure, error.usage) == (LlmFailure.UNAVAILABLE, USAGE)


def test_a_policy_without_attempts_makes_no_call() -> None:
    model = _model([DRAFT])
    policy = RetryPolicy(10.0, 5.0, 0, backoff_base_seconds=0.25, backoff_max_seconds=2.0)

    error = _refusal(_writer(model, policy))

    assert (error.failure, error.usage, model.timeouts) == (LlmFailure.UNAVAILABLE, None, [])

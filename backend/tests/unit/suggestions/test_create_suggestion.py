"""Tests of `CreateSuggestion` and of the suggestion rules it uses (contracts v1 design)."""

from dataclasses import dataclass
from uuid import UUID

import pytest

from supportiq_backend.accounts import Authorizer, SupportPrincipal, SupportRole
from supportiq_backend.audit import AuditEventType
from supportiq_backend.idempotency import IdempotencyGuard, IdempotencyKey, StoredResponse
from supportiq_backend.platform import ResourceNotFoundError
from supportiq_backend.suggestions import (
    AiReasonCode,
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
    IntentLabel,
    InvalidTicketStateError,
    NoDraftStatus,
    NoIntentKnownError,
    NothingToRetryError,
    Suggestion,
    SuggestionPendingError,
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTicketId,
    SuggestionTrigger,
    TicketForSuggestion,
    choose_view_trigger,
    plan_requested_suggestion,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    SequentialIdGenerator,
)
from tests.unit.suggestions.builders import (
    KB_VERSION,
    OTHER_KB_VERSION,
    PREDICTED_INTENT,
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    TICKET_ID,
    build_failed_suggestion,
    build_no_draft,
    build_ready_suggestion,
    build_suggestion,
    with_override,
)
from tests.unit.suggestions.fakes import (
    FakeSuggestionStore,
    FakeTicketLinks,
    RecordingSuggestionQueue,
)

KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000321"))
SUPPORT = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
CHOSEN_INTENT = IntentLabel.REQUEST_REFUND
UNKNOWN_TICKET_ID = SuggestionTicketId("TCK-9")


@dataclass(slots=True)
class Harness:
    """The use case with its fakes."""

    create: CreateSuggestion
    suggestions: FakeSuggestionStore
    audit: FakeAuditLog
    queue: RecordingSuggestionQueue


def render(suggestion: Suggestion) -> StoredResponse:
    return StoredResponse(202, suggestion.suggestion_id)


def build_harness(
    current: Suggestion | None, *, is_open: bool = True, is_assisted: bool = True
) -> Harness:
    suggestions = FakeSuggestionStore()
    if current is not None:
        suggestions.data.add(current)
    links = FakeTicketLinks(
        tickets={
            TICKET_ID: TicketForSuggestion(
                None if current is None else current.suggestion_id,
                is_open,
                is_assisted,
                "open" if is_open else "closed",
            )
        }
    )
    audit = FakeAuditLog()
    events = RecordingEventRecorder()
    queue = RecordingSuggestionQueue()
    clock = FakeClock()
    create = CreateSuggestion(
        FakeTransactionRunner(
            CreateSuggestionStores(suggestions, links, FakeIdempotencyStore(), audit)
        ),
        CreateSuggestionPorts(
            authorizer=Authorizer(events),
            guard=IdempotencyGuard(clock, 86_400_000),
            starter=SuggestionStarter(
                SuggestionStarterPorts(
                    clock=clock,
                    ids=SequentialIdGenerator(start=700),
                    traces=FixedTraceContext(),
                    events=events,
                    queue=queue,
                )
            ),
            clock=clock,
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=events,
        ),
        render,
    )
    return Harness(create, suggestions, audit, queue)


def new_suggestion(harness: Harness) -> Suggestion:
    (notification,) = harness.queue.notifications
    return harness.suggestions.data.suggestions[notification[1]]


@pytest.mark.anyio
async def test_a_correction_supersedes_the_current_suggestion_and_audits_the_intents() -> None:
    harness = build_harness(build_ready_suggestion())

    await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)

    created = new_suggestion(harness)
    (entry,) = harness.audit.entries
    assert created.trigger is SuggestionTrigger.INTENT_OVERRIDE
    assert created.intent_override is CHOSEN_INTENT
    assert entry.event_type is AuditEventType.INTENT_OVERRIDDEN
    assert entry.data["previous_intent"] == PREDICTED_INTENT.value
    assert entry.data["chosen_intent"] == CHOSEN_INTENT.value


@pytest.mark.anyio
async def test_a_correction_while_the_draft_generates_cancels_the_pending_draft() -> None:
    harness = build_harness(build_suggestion(analysis=build_ready_suggestion().analysis))

    await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)

    assert not harness.suggestions.data.suggestions[SUGGESTION_ID].has_pending_part


@pytest.mark.anyio
async def test_a_retry_repeats_the_intent_that_staff_chose() -> None:
    failed = with_override(
        build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE), CHOSEN_INTENT
    )
    harness = build_harness(failed)

    await harness.create.execute(SUPPORT, TICKET_ID, None, KEY)

    created = new_suggestion(harness)
    assert created.trigger is SuggestionTrigger.RETRY
    assert created.intent_override is CHOSEN_INTENT
    assert harness.audit.entries == []


@pytest.mark.anyio
async def test_a_ticket_in_manual_mode_never_gets_a_suggestion() -> None:
    harness = build_harness(None, is_assisted=False)

    with pytest.raises(InvalidTicketStateError) as caught:
        await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)

    assert "manual mode" in caught.value.detail
    assert harness.suggestions.data.suggestions == {}


@pytest.mark.anyio
async def test_a_ticket_that_is_not_open_gets_no_suggestion() -> None:
    harness = build_harness(build_ready_suggestion(), is_open=False)

    with pytest.raises(InvalidTicketStateError):
        await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)


@pytest.mark.anyio
async def test_an_unknown_ticket_is_not_found() -> None:
    harness = build_harness(None)

    with pytest.raises(ResourceNotFoundError):
        await harness.create.execute(SUPPORT, UNKNOWN_TICKET_ID, CHOSEN_INTENT, KEY)


def test_a_correction_while_no_intent_is_known_and_a_part_is_pending_is_a_conflict() -> None:
    with pytest.raises(SuggestionPendingError):
        plan_requested_suggestion(build_suggestion(), CHOSEN_INTENT)


def test_a_correction_while_no_intent_is_known_and_nothing_is_pending_is_invalid() -> None:
    with pytest.raises(NoIntentKnownError):
        plan_requested_suggestion(
            build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE), CHOSEN_INTENT
        )


@pytest.mark.parametrize(
    "current",
    [
        None,
        build_ready_suggestion(),
        build_suggestion(),
        build_failed_suggestion(AiReasonCode.PSEUDONYMIZATION_FAILED),
    ],
)
def test_a_retry_without_a_failure_to_fix_is_invalid(current: Suggestion | None) -> None:
    with pytest.raises(NothingToRetryError):
        plan_requested_suggestion(current, None)


def test_a_draft_that_the_llm_could_not_write_can_be_retried() -> None:
    suggestion = build_ready_suggestion(build_no_draft(NoDraftStatus.LLM_UNAVAILABLE))

    plan = plan_requested_suggestion(suggestion, None)

    assert plan == (SuggestionTrigger.RETRY, None)


@pytest.mark.parametrize(
    ("loaded_kb_version", "is_first_view", "expected"),
    [
        (OTHER_KB_VERSION, True, SuggestionTrigger.KB_VERSION_CHANGED),
        (KB_VERSION, True, None),
        (OTHER_KB_VERSION, False, None),
        (None, True, None),
    ],
)
def test_a_view_reruns_a_suggestion_only_on_the_first_view_after_a_kb_change(
    loaded_kb_version: str | None,
    *,
    is_first_view: bool,
    expected: SuggestionTrigger | None,
) -> None:
    trigger = choose_view_trigger(
        build_ready_suggestion(),
        is_first_view=is_first_view,
        loaded_kb_version=loaded_kb_version,
    )

    assert trigger is expected


def test_a_pending_suggestion_blocks_every_view_trigger() -> None:
    trigger = choose_view_trigger(
        build_suggestion(), is_first_view=True, loaded_kb_version=OTHER_KB_VERSION
    )

    assert trigger is None

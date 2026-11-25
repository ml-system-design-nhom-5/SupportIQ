"""Tests of the suggestion progress stream with fakes of every port (ADR-0022)."""

import asyncio
from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace

import pytest

from app.accounts import (
    AccountId,
    Authorizer,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    Principal,
)
from app.platform import DatabaseUnavailableError, EventName, ResourceNotFoundError
from app.suggestions import (
    AiReasonCode,
    CancelledPart,
    PartStatus,
    ProgressSignals,
    ProgressStores,
    StreamSettings,
    Suggestion,
    SuggestionProgress,
    SuggestionTicketId,
    TicketForSuggestion,
    WatchProgressPorts,
    WatchSuggestionProgress,
)
from app.suggestions.api.suggestion_events import to_event_frame
from tests.unit.platform.fakes import FakeClock, FakeTransactionRunner, RecordingEventRecorder
from tests.unit.suggestions.builders import (
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    TICKET_ID,
    build_analysis,
    build_failed_suggestion,
    build_ready_suggestion,
    build_suggestion,
)
from tests.unit.suggestions.fakes import FakeSuggestionStore, FakeTicketLinks

STREAM_SETTINGS = StreamSettings(poll_ms=1_000, max_ms=60_000)
POLLS_BEFORE_A_PING = 15
OPEN_TICKET = TicketForSuggestion(SUGGESTION_ID, True, True, "open")
OTHER_TICKET_ID = SuggestionTicketId("TCK-2042")
PENDING = SuggestionProgress(SUGGESTION_ID, PartStatus.PENDING, PartStatus.PENDING)
CUSTOMER = CustomerPrincipal(
    AccountId("00000000-0000-4000-8000-0000000000cc"),
    CustomerId("00000000-0000-4000-8000-0000000000c1"),
)
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)

type Stream = AsyncIterator[SuggestionProgress | None]


@dataclass(slots=True)
class Harness:
    """The stream with the fakes that a test changes or inspects."""

    watch: WatchSuggestionProgress
    store: FakeSuggestionStore
    links: FakeTicketLinks
    signals: ProgressSignals
    clock: FakeClock
    events: RecordingEventRecorder


class StoppedClock(FakeClock):
    """A clock whose sleeps never end, so only a wake-up moves a stream on."""

    async def sleep(self, duration_ms: int) -> None:
        """Wait forever."""
        del duration_ms
        await asyncio.Event().wait()


class CountingSignals(ProgressSignals):
    """The wake-ups of the replica, with the number of subscriptions still open."""

    def __init__(self) -> None:
        """Start without subscriptions."""
        super().__init__()
        self.open_subscriptions = 0

    @contextmanager
    def subscribe(self, ticket_id: SuggestionTicketId) -> Generator[asyncio.Event]:
        """Count the subscription while it is open."""
        self.open_subscriptions += 1
        try:
            with super().subscribe(ticket_id) as wake_up:
                yield wake_up
        finally:
            self.open_subscriptions -= 1


def build_harness(
    suggestion: Suggestion | None = None,
    ticket: TicketForSuggestion = OPEN_TICKET,
    clock: FakeClock | None = None,
    signals: ProgressSignals | None = None,
) -> Harness:
    store = FakeSuggestionStore()
    store.data.add(suggestion or build_suggestion())
    links = FakeTicketLinks(tickets={TICKET_ID: ticket})
    signals = signals or ProgressSignals()
    events = RecordingEventRecorder()
    the_clock = clock or FakeClock()
    watch = WatchSuggestionProgress(
        FakeTransactionRunner(ProgressStores(links, store)),
        WatchProgressPorts(Authorizer(events), signals, the_clock, events),
        STREAM_SETTINGS,
    )
    return Harness(watch, store, links, signals, the_clock, events)


async def open_stream(harness: Harness) -> Stream:
    stream = await harness.watch.open(TICKET_ID)
    assert stream is not None
    return stream


def store(harness: Harness, suggestion: Suggestion) -> None:
    harness.store.data.suggestions[suggestion.suggestion_id] = suggestion


def end_reasons(harness: Harness) -> list[object]:
    return [
        event.attributes["stream_end_reason"]
        for event in harness.events.events
        if event.name is EventName.SUGGESTION_STREAM_ENDED
    ]


@pytest.mark.parametrize("role", [InternalRole.STAFF, InternalRole.MANAGER])
def test_staff_and_managers_may_follow_a_suggestion(role: InternalRole) -> None:
    harness = build_harness()

    support = harness.watch.authorize(InternalPrincipal(STAFF_ACCOUNT_ID, role))

    assert support.account_id == STAFF_ACCOUNT_ID


@pytest.mark.parametrize("principal", [CUSTOMER, ADMIN])
def test_customers_and_admins_may_not_follow_a_suggestion(principal: Principal) -> None:
    harness = build_harness()

    with pytest.raises(ForbiddenRoleError):
        harness.watch.authorize(principal)


@pytest.mark.anyio
async def test_an_unknown_ticket_is_not_found() -> None:
    harness = build_harness()

    with pytest.raises(ResourceNotFoundError):
        await harness.watch.open(OTHER_TICKET_ID)


@pytest.mark.parametrize(
    ("suggestion", "ticket"),
    [
        (build_suggestion(), replace(OPEN_TICKET, is_open=False, status_name="escalated")),
        (build_suggestion(), replace(OPEN_TICKET, is_assisted=False)),
        (build_suggestion(), replace(OPEN_TICKET, current_suggestion_id=None)),
        (build_ready_suggestion(), OPEN_TICKET),
        (build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE), OPEN_TICKET),
    ],
    ids=["not-open", "manual-mode", "no-suggestion", "ready", "unavailable"],
)
@pytest.mark.anyio
async def test_a_ticket_without_a_pending_part_has_nothing_to_follow(
    suggestion: Suggestion, ticket: TicketForSuggestion
) -> None:
    harness = build_harness(suggestion, ticket)

    assert await harness.watch.open(TICKET_ID) is None


@pytest.mark.anyio
async def test_the_stream_starts_with_the_current_state() -> None:
    stream = await open_stream(build_harness())

    assert await anext(stream) == PENDING


@pytest.mark.anyio
async def test_a_changed_part_status_sends_one_event() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)

    store(harness, build_suggestion(analysis=build_analysis()))

    assert await anext(stream) == replace(PENDING, analysis_status=PartStatus.READY)
    assert harness.clock.sleeps_ms == [STREAM_SETTINGS.poll_ms]


@pytest.mark.anyio
async def test_an_unchanged_state_sends_only_a_ping_after_15_s() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)

    assert await anext(stream) is None
    assert harness.clock.sleeps_ms == [STREAM_SETTINGS.poll_ms] * POLLS_BEFORE_A_PING


@pytest.mark.anyio
async def test_the_stream_ends_right_after_the_event_without_a_pending_part() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)
    store(harness, build_ready_suggestion())

    last = await anext(stream)

    assert last == SuggestionProgress(SUGGESTION_ID, PartStatus.READY, PartStatus.DRAFT_READY)
    assert [item async for item in stream] == []
    assert end_reasons(harness) == ["no_pending_part"]


@pytest.mark.anyio
async def test_the_stream_ends_when_the_ticket_leaves_open() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)

    harness.links.tickets[TICKET_ID] = replace(OPEN_TICKET, is_open=False, status_name="closed")

    assert [item async for item in stream] == []
    assert end_reasons(harness) == ["ticket_not_open"]


@pytest.mark.anyio
async def test_the_stream_ends_at_its_time_limit() -> None:
    harness = build_harness()
    stream = await open_stream(harness)

    items = [item async for item in stream]

    assert items == [PENDING, None, None, None]
    assert end_reasons(harness) == ["time_limit"]


@pytest.mark.anyio
async def test_a_part_cancelled_by_a_newer_suggestion_sends_no_event() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)

    store(harness, build_suggestion(analysis=CancelledPart(), draft=CancelledPart()))

    assert await anext(stream) is None


@pytest.mark.anyio
async def test_a_wake_up_rereads_without_waiting_for_the_poll() -> None:
    harness = build_harness(clock=StoppedClock())
    stream = await open_stream(harness)
    await anext(stream)
    store(harness, build_suggestion(analysis=build_analysis()))

    harness.signals.notify_progress(TICKET_ID)

    assert await anext(stream) == replace(PENDING, analysis_status=PartStatus.READY)


@pytest.mark.anyio
async def test_a_failed_reread_ends_the_stream_with_its_error_type() -> None:
    harness = build_harness()
    stream = await open_stream(harness)
    await anext(stream)

    harness.store.failure = DatabaseUnavailableError()

    assert [item async for item in stream] == []
    (failed,) = harness.events.of(EventName.SUGGESTION_STREAM_FAILED)
    assert failed.attributes == {"ticket_id": TICKET_ID, "error_type": "DatabaseUnavailableError"}


@pytest.mark.anyio
async def test_a_client_disconnect_ends_the_stream_and_its_subscription() -> None:
    signals = CountingSignals()
    harness = build_harness(clock=StoppedClock(), signals=signals)
    stream = await open_stream(harness)
    await anext(stream)
    waiting = asyncio.ensure_future(anext(stream))
    await asyncio.sleep(0)

    # Starlette cancels the body of a response when the client disconnects.
    waiting.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert signals.open_subscriptions == 0
    assert [item async for item in stream] == []


def test_leaving_a_subscription_stops_its_wake_ups() -> None:
    signals = ProgressSignals()
    with signals.subscribe(TICKET_ID) as left:
        pass

    with signals.subscribe(TICKET_ID) as current:
        signals.notify_progress(TICKET_ID)

        assert current.is_set()
        assert not left.is_set()


def test_a_notification_wakes_only_the_streams_of_its_ticket() -> None:
    signals = ProgressSignals()

    with signals.subscribe(TICKET_ID) as woken, signals.subscribe(OTHER_TICKET_ID) as other:
        signals.notify_progress(TICKET_ID)

        assert woken.is_set()
        assert not other.is_set()


def test_an_event_holds_only_the_suggestion_id_and_the_two_statuses() -> None:
    frame = to_event_frame(PENDING)

    assert frame == (
        b"event: suggestion\n"
        b'data: {"suggestion_id":"' + SUGGESTION_ID.encode() + b'",'
        b'"analysis_status":"pending","draft_status":"pending"}\n\n'
    )

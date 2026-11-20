"""A harness of `CreateSuggestion` with a fake of every port, over the tickets a test chooses."""

import json
from collections.abc import Mapping
from dataclasses import dataclass

from app.accounts import Authorizer
from app.idempotency import IdempotencyGuard, StoredResponse
from app.platform import BackendError
from app.suggestions import (
    CreateSuggestion,
    CreateSuggestionPorts,
    CreateSuggestionStores,
    Suggestion,
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTicketId,
    TicketForSuggestion,
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
from tests.unit.suggestions.fakes import (
    FakeSuggestionStore,
    FakeTicketLinks,
    RecordingProgressNotifier,
    RecordingSuggestionQueue,
)

RETENTION_MS = 86_400_000
FIRST_SUGGESTION_NUMBER = 700


@dataclass(slots=True)
class CreateSuggestionHarness:
    """The use case with the fakes that a test inspects.

    Attributes:
        create: The use case.
        suggestions: The suggestion store.
        audit: The audit log.
        queue: The notifications of the claim loop.
        progress: The wake-ups of the streams.
        events: The recorded events.
        transactions: The transaction runner, which counts commits.
    """

    create: CreateSuggestion
    suggestions: FakeSuggestionStore
    audit: FakeAuditLog
    queue: RecordingSuggestionQueue
    progress: RecordingProgressNotifier
    events: RecordingEventRecorder
    transactions: FakeTransactionRunner[CreateSuggestionStores]


def render_suggestion_id(suggestion: Suggestion) -> StoredResponse:
    """Write a `202` whose body is the ID of the new suggestion."""
    return StoredResponse(202, json.dumps({"suggestion_id": suggestion.suggestion_id}))


def build_create_suggestion_harness(
    tickets: Mapping[SuggestionTicketId, TicketForSuggestion],
    *suggestions: Suggestion,
    commit_failure: BackendError | None = None,
) -> CreateSuggestionHarness:
    """Build `CreateSuggestion` over the tickets and the stored suggestions.

    Args:
        tickets: The tickets, as `createSuggestion` locks them.
        *suggestions: The stored suggestions.
        commit_failure: The error that the commit raises, or None to succeed.

    Returns:
        The harness.
    """
    store = FakeSuggestionStore()
    for suggestion in suggestions:
        store.data.add(suggestion)
    audit = FakeAuditLog()
    events = RecordingEventRecorder()
    queue = RecordingSuggestionQueue()
    progress = RecordingProgressNotifier()
    clock = FakeClock()
    transactions = FakeTransactionRunner(
        CreateSuggestionStores(
            store, FakeTicketLinks(tickets=dict(tickets)), FakeIdempotencyStore(), audit
        ),
        commit_failure=commit_failure,
    )
    starter = SuggestionStarter(
        SuggestionStarterPorts(
            clock=clock,
            ids=SequentialIdGenerator(start=FIRST_SUGGESTION_NUMBER),
            traces=FixedTraceContext(),
            events=events,
            queue=queue,
            progress=progress,
        )
    )
    ports = CreateSuggestionPorts(
        authorizer=Authorizer(events),
        guard=IdempotencyGuard(clock, RETENTION_MS),
        starter=starter,
        clock=clock,
        ids=SequentialIdGenerator(),
        traces=FixedTraceContext(),
        events=events,
    )
    create = CreateSuggestion(transactions, ports, render_suggestion_id)
    return CreateSuggestionHarness(create, store, audit, queue, progress, events, transactions)

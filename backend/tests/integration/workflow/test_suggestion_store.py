"""Adapter tests of `PostgresSuggestionStore` against PostgreSQL 17 (TEST-01).

A suggestion is inserted with two pending parts and a queued job, read back with the state of
each part, and superseded by cancelling every pending part of its ticket and ending its job
(backend ticket workflow design, Suggestions and the job queue, item 1). A stored value that no
longer matches the contract is a defect of backend, read as an unexpected failure (ERR-05).
"""

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import AccountId
from supportiq_backend.commerce import Money, OrderStatus, ShipmentStatus
from supportiq_backend.platform import UnexpectedFailureError
from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.suggestions import (
    AiReasonCode,
    AiServiceContractError,
    CancelledPart,
    IntentLabel,
    OrderContext,
    PendingPart,
    Suggestion,
    SuggestionId,
    SuggestionRequest,
    SuggestionTicketId,
    SuggestionTrigger,
    UnavailablePart,
    build_analysis_completion,
    build_draft_completion,
)
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionStore
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import (
    PartSpec,
    SuggestionSpec,
    draft_ready_outcome,
    ready_analysis,
    sent_request,
)
from tests.integration.tickets.console_requests import (
    insert_suggestion as insert_stored_suggestion,
)
from tests.integration.workflow.workflow_rows import (
    LEASE,
    build_new_suggestion,
    build_unavailable_parts,
    claim_job,
    complete_parts,
    insert_suggestion,
    insert_ticket,
    load_job_state,
    load_part_statuses,
    new_suggestion,
    received_analysis_example,
    received_draft_example,
    save_request,
    start_suggestion,
    ticket_created,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START, FAKE_TRACE_ID

pytestmark = pytest.mark.anyio

NOW = FAKE_CLOCK_START
CANCELLED_AT = FAKE_CLOCK_START + timedelta(seconds=4)
UNKNOWN_SUGGESTION_ID = SuggestionId("ffffffff-0000-4000-8000-000000000000")
CHOSEN_INTENT = IntentLabel.TRACK_ORDER
ORDER_CONTEXT = OrderContext(
    order_status=OrderStatus.SHIPPED,
    placed_at=FAKE_CLOCK_START,
    order_total=Money(4_250, "USD"),
    shipment_status=ShipmentStatus.IN_TRANSIT,
)
REQUEST = SuggestionRequest(
    message="Where is the parcel of [ORDER_ID_1]?",
    order_context=ORDER_CONTEXT,
    as_of=FAKE_CLOCK_START,
    intent_override=None,
)
BOTH_PENDING = {"analysis": "pending", "draft": "pending"}
QUEUED_JOB = {"state": "queued", "attempt_number": 0}
DONE_AFTER_ONE_CLAIM = {"state": "done", "attempt_number": 1}
DRAFT_COMPLETED_AT = "SELECT completed_at FROM suggestion_parts WHERE part = 'draft'"
JOB_TIMES = "SELECT ARRAY[lease_expires_at, updated_at] FROM suggestion_jobs"
PART_RESULTS_ARE_ABSENT = """
    SELECT bool_and(versions IS NULL AND mask_count_by_type IS NULL AND result IS NULL)
    FROM suggestion_parts
"""
# A stored analysis, draft outcome, and request that no longer match the contract: a boolean
# as text, a reason code that the contract does not list, and a message that is no text.
OUTSIDE_THE_CONTRACT = [
    SuggestionSpec(analysis=PartSpec("ready", ready_analysis() | {"is_in_scope": "yes"})),
    SuggestionSpec(
        analysis=PartSpec("ready", ready_analysis()),
        draft=PartSpec("draft_ready", draft_ready_outcome() | {"reason_codes": ["unknown"]}),
    ),
    SuggestionSpec(request=sent_request() | {"message": 7}),
]
OUTSIDE_IDS = ["analysis", "draft-outcome", "request"]


async def load_suggestion(engine: AsyncEngine, suggestion_id: SuggestionId) -> Suggestion | None:
    async with create_session_factory(engine)() as session:
        return await PostgresSuggestionStore(session).load_suggestion(suggestion_id)


async def cancel_pending(
    engine: AsyncEngine, ticket_id: SuggestionTicketId
) -> tuple[SuggestionId, ...]:
    async with create_session_factory(engine)() as session:
        cancelled = await PostgresSuggestionStore(session).cancel_pending_suggestions(
            ticket_id, CANCELLED_AT
        )
        await session.commit()
    return cancelled


async def test_insert_suggestion_stores_it_with_two_pending_parts(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    staff_id = AccountId(str(await builder.account(AccountSpec("staff"))))
    suggestion = replace(
        build_new_suggestion(builder, ticket_id, NOW),
        trigger=SuggestionTrigger.INTENT_OVERRIDE,
        intent_override=CHOSEN_INTENT,
        requested_by=staff_id,
    )

    await insert_suggestion(app_engine, suggestion)

    assert await load_suggestion(app_engine, suggestion.suggestion_id) == Suggestion(
        suggestion_id=suggestion.suggestion_id,
        ticket_id=ticket_id,
        trigger=SuggestionTrigger.INTENT_OVERRIDE,
        intent_override=CHOSEN_INTENT,
        requested_by=staff_id,
        created_at=NOW,
        trace_id=FAKE_TRACE_ID,
        analysis=PendingPart(),
        draft=PendingPart(),
        sent_order_context=None,
    )


async def test_insert_suggestion_queues_its_job_without_a_lease(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion = build_new_suggestion(builder, await insert_ticket(builder), NOW)

    await insert_suggestion(app_engine, suggestion)

    assert await load_job_state(builder, suggestion.suggestion_id) == QUEUED_JOB
    assert await builder.scalar(JOB_TIMES) == [None, NOW]


async def test_insert_suggestion_leaves_the_request_absent_until_pseudonymization(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion = build_new_suggestion(builder, await insert_ticket(builder), NOW)

    await insert_suggestion(app_engine, suggestion)

    # Absent is SQL NULL, the only value that `save_request` and the trigger of `r0003` treat
    # as "not written yet" (design, Tables), never the JSON value `null`.
    assert await builder.scalar("SELECT request IS NULL FROM suggestions") is True


async def test_insert_suggestion_leaves_the_results_of_its_pending_parts_absent(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion = build_new_suggestion(builder, await insert_ticket(builder), NOW)

    await insert_suggestion(app_engine, suggestion)

    # A pending part has no versions, masks, or result yet: SQL NULL, never the JSON value
    # `null` (design, Tables: "optional").
    assert await builder.scalar(PART_RESULTS_ARE_ABSENT) is True


async def test_load_suggestion_of_an_unknown_suggestion_is_none(app_engine: AsyncEngine) -> None:
    assert await load_suggestion(app_engine, UNKNOWN_SUGGESTION_ID) is None


async def test_load_suggestions_returns_each_known_suggestion_by_its_id(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    first = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    second = await start_suggestion(app_engine, builder, ticket_created(ticket_id))

    async with create_session_factory(app_engine)() as session:
        loaded = await PostgresSuggestionStore(session).load_suggestions(
            frozenset({first, second, UNKNOWN_SUGGESTION_ID})
        )

    assert set(loaded) == {first, second}
    assert loaded[first].draft == CancelledPart()
    assert loaded[second].draft == PendingPart()


async def test_load_suggestions_of_no_suggestion_is_empty(app_engine: AsyncEngine) -> None:
    async with create_session_factory(app_engine)() as session:
        loaded = await PostgresSuggestionStore(session).load_suggestions(frozenset())

    assert loaded == {}


async def test_load_suggestion_reads_a_stored_analysis_and_draft_outcome(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    analysis = received_analysis_example("draft")
    draft = received_draft_example("draft-ready")
    await complete_parts(
        app_engine,
        suggestion_id,
        build_analysis_completion(analysis, NOW),
        build_draft_completion(draft, NOW),
    )

    loaded = await load_suggestion(app_engine, suggestion_id)

    assert loaded is not None
    assert loaded.analysis == analysis.analysis
    assert loaded.draft == draft.outcome


async def test_load_suggestion_reads_an_unavailable_part_with_its_reason_code(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    failed = build_unavailable_parts(AiReasonCode.PSEUDONYMIZATION_FAILED, NOW)
    await complete_parts(app_engine, suggestion_id, *failed)

    loaded = await load_suggestion(app_engine, suggestion_id)

    assert loaded is not None
    assert loaded.analysis == loaded.draft == UnavailablePart(AiReasonCode.PSEUDONYMIZATION_FAILED)


async def test_load_suggestion_reads_the_order_context_of_the_stored_request(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    await save_request(app_engine, suggestion_id, REQUEST)

    loaded = await load_suggestion(app_engine, suggestion_id)

    assert loaded is not None
    assert loaded.sent_order_context == ORDER_CONTEXT


@pytest.mark.parametrize("spec", OUTSIDE_THE_CONTRACT, ids=OUTSIDE_IDS)
async def test_load_suggestion_of_a_stored_value_outside_the_contract_is_an_unexpected_failure(
    app_engine: AsyncEngine,
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    spec: SuggestionSpec,
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await insert_stored_suggestion(worker_database, builder, ticket_id, spec)

    with pytest.raises(UnexpectedFailureError) as caught:
        await load_suggestion(app_engine, SuggestionId(suggestion_id))

    assert isinstance(caught.value.__cause__, AiServiceContractError)


async def test_cancel_pending_suggestions_cancels_only_the_pending_parts(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    analysis = build_analysis_completion(received_analysis_example("draft"), NOW)
    await complete_parts(app_engine, suggestion_id, analysis)

    await cancel_pending(app_engine, ticket_id)

    assert await load_part_statuses(builder, suggestion_id) == {
        "analysis": "ready",
        "draft": "cancelled",
    }
    assert await builder.scalar(DRAFT_COMPLETED_AT) == CANCELLED_AT


async def test_cancel_pending_suggestions_ends_the_job_of_the_ticket(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    await claim_job(app_engine, NOW)

    await cancel_pending(app_engine, ticket_id)

    assert await load_job_state(builder, suggestion_id) == DONE_AFTER_ONE_CLAIM
    assert await builder.scalar(JOB_TIMES) == [NOW + LEASE, CANCELLED_AT]


async def test_cancel_pending_suggestions_returns_the_suggestions_with_a_pending_part(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    current = await start_suggestion(app_engine, builder, ticket_created(ticket_id))

    cancelled = await cancel_pending(app_engine, ticket_id)

    assert cancelled == (current,)


async def test_cancel_pending_suggestions_leaves_the_suggestions_of_other_tickets(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    other_suggestion_id = await new_suggestion(app_engine, builder)

    await cancel_pending(app_engine, ticket_id)

    assert await load_part_statuses(builder, other_suggestion_id) == BOTH_PENDING
    assert await load_job_state(builder, other_suggestion_id) == QUEUED_JOB

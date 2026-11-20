"""Rows, suggestions, and claims of the ticket workflow for the adapter tests (TEST-05).

Setup that `supportiq_app` cannot do runs as the owner. A suggestion starts the way every use
case starts one: the ticket row is locked first, then the starter cancels the previous
suggestion and inserts the new one. Reads for assertions run as the owner and return one JSON
value, so an assertion compares one dictionary. Every value is synthetic (TEST-18).
"""

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform.adapters.database import create_session_factory
from app.suggestions import (
    AiReasonCode,
    ClaimedJob,
    NewSuggestion,
    PartCompletion,
    QueueSettings,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    SuggestionId,
    SuggestionPart,
    SuggestionRequest,
    SuggestionStart,
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTicketId,
    SuggestionTrigger,
    build_unavailable_completion,
)
from app.suggestions.adapters.ai_service_payloads import (
    parse_analysis_response,
    parse_draft_response,
)
from app.suggestions.adapters.suggestion_store import (
    PostgresSuggestionJobStore,
    PostgresSuggestionStore,
)
from app.tickets.adapters.console_store import PostgresTicketLinks
from tests.integration.accounts.lock_waits import ROW_LOCK_WAITS
from tests.integration.builders import (
    DatabaseBuilder,
    LineSpec,
    OrderSpec,
    RefundSpec,
    TicketSpec,
)
from tests.integration.schema.statements import run_statement
from tests.unit.platform.fakes import (
    FAKE_TRACE_ID,
    FakeClock,
    FixedTraceContext,
    RecordingEventRecorder,
    SequentialIdGenerator,
)
from tests.unit.suggestions.fakes import RecordingProgressNotifier, RecordingSuggestionQueue

EXAMPLES = Path(__file__).parents[4] / "contracts" / "examples"
# The initial values of the queue (backend ticket workflow design, Choice 3).
QUEUE_SETTINGS = QueueSettings(workers_per_replica=5, lease_ms=15_000, max_attempts=3, poll_ms=500)
LEASE = timedelta(milliseconds=QUEUE_SETTINGS.lease_ms)
_PART_STATUSES = (
    "SELECT jsonb_object_agg(part, status) FROM suggestion_parts"
    " WHERE suggestion_id = :suggestion_id"
)
_PART_REASON_CODES = (
    "SELECT jsonb_object_agg(part, reason_codes) FROM suggestion_parts"
    " WHERE suggestion_id = :suggestion_id"
)
_JOB_STATE = (
    "SELECT jsonb_build_object('state', state, 'attempt_number', attempt_number)"
    " FROM suggestion_jobs WHERE suggestion_id = :suggestion_id"
)
_AUTHORITY_FLAG = "SELECT is_authority_required FROM tickets WHERE ticket_id = :ticket_id"
_LEAVE_JOB_RUNNING = """
    UPDATE suggestion_jobs
    SET state = 'running', attempt_number = :attempt_number, lease_expires_at = :lease_expires_at
    WHERE suggestion_id = :suggestion_id
"""
_SET_TICKET_STATUS = """
    UPDATE tickets SET status = :status, closed_at = :closed_at WHERE ticket_id = :ticket_id
"""
_SET_HANDLING_MODE = (
    "UPDATE tickets SET handling_mode = :handling_mode WHERE ticket_id = :ticket_id"
)


async def insert_ticket(
    builder: DatabaseBuilder, spec: TicketSpec | None = None
) -> SuggestionTicketId:
    """Insert a customer with an account, one order, and a ticket about it.

    The order has a refund, so its order context carries `refund_status`, the field that the
    draft examples of the ai-service contract cite.
    """
    _account_id, customer_id = await builder.customer_account()
    product_id = await builder.product()
    order = OrderSpec(lines=(LineSpec(product_id),), refund=RefundSpec())
    order_id = await builder.order(customer_id, order)
    return SuggestionTicketId(await builder.ticket(customer_id, order_id, spec))


async def insert_orders(
    builder: DatabaseBuilder, customer_id: UUID, placed_ats: Sequence[datetime]
) -> tuple[str, ...]:
    """Insert one order of one product for each time, in the given order; return their IDs."""
    product_id = await builder.product()
    order_ids: list[str] = []
    for placed_at in placed_ats:
        spec = OrderSpec(lines=(LineSpec(product_id),), placed_at=placed_at)
        order_ids.append(await builder.order(customer_id, spec))
    return tuple(order_ids)


async def set_ticket_status(
    owner_engine: AsyncEngine, ticket_id: str, status: str, *, closed_at: datetime | None = None
) -> None:
    """Move an open ticket to another status, along the state machine."""
    await run_statement(
        owner_engine, _SET_TICKET_STATUS, status=status, closed_at=closed_at, ticket_id=ticket_id
    )


async def set_handling_mode(owner_engine: AsyncEngine, ticket_id: str, handling_mode: str) -> None:
    """Change the handling mode of a ticket."""
    await run_statement(
        owner_engine, _SET_HANDLING_MODE, handling_mode=handling_mode, ticket_id=ticket_id
    )


def ticket_created(ticket_id: SuggestionTicketId) -> SuggestionStart:
    """Describe the first suggestion of a ticket."""
    return SuggestionStart(ticket_id, SuggestionTrigger.TICKET_CREATED, None, None)


async def start_suggestion(
    engine: AsyncEngine, builder: DatabaseBuilder, start: SuggestionStart
) -> SuggestionId:
    """Start a suggestion as a use case does and commit; return its ID.

    The suggestion gets the next time and the next UUID of the builder.
    """
    starter = SuggestionStarter(
        SuggestionStarterPorts(
            clock=FakeClock(builder.next_time()),
            ids=SequentialIdGenerator(builder.next_number()),
            traces=FixedTraceContext(),
            events=RecordingEventRecorder(),
            queue=RecordingSuggestionQueue(),
            progress=RecordingProgressNotifier(),
        )
    )
    async with create_session_factory(engine)() as session:
        links = PostgresTicketLinks(session)
        await links.lock_ticket(start.ticket_id)
        started = await starter.start(PostgresSuggestionStore(session), links, start)
        await session.commit()
    return started.suggestion.suggestion_id


async def new_suggestion(engine: AsyncEngine, builder: DatabaseBuilder) -> SuggestionId:
    """Insert a ticket and start its first suggestion; return the suggestion ID."""
    ticket_id = await insert_ticket(builder)
    return await start_suggestion(engine, builder, ticket_created(ticket_id))


def build_new_suggestion(
    builder: DatabaseBuilder, ticket_id: SuggestionTicketId, created_at: datetime
) -> NewSuggestion:
    """Build the first suggestion of a ticket with the next UUID of the builder."""
    return NewSuggestion(
        suggestion_id=SuggestionId(str(builder.next_uuid())),
        ticket_id=ticket_id,
        trigger=SuggestionTrigger.TICKET_CREATED,
        intent_override=None,
        requested_by=None,
        created_at=created_at,
        trace_id=FAKE_TRACE_ID,
    )


async def insert_suggestion(engine: AsyncEngine, suggestion: NewSuggestion) -> None:
    """Insert a suggestion with `PostgresSuggestionStore.insert_suggestion` and commit."""
    async with create_session_factory(engine)() as session:
        await PostgresSuggestionStore(session).insert_suggestion(suggestion)
        await session.commit()


async def claim_job(engine: AsyncEngine, now: datetime) -> ClaimedJob:
    """Claim the next job with the lease of `QUEUE_SETTINGS` and commit the claim."""
    async with create_session_factory(engine)() as session:
        job = await PostgresSuggestionJobStore(session).claim_next(now, now + LEASE)
        await session.commit()
    if job is None:
        pytest.fail("No suggestion job was claimable.")
    return job


async def leave_job_running(
    owner_engine: AsyncEngine,
    suggestion_id: SuggestionId,
    *,
    attempt_number: int,
    lease_expires_at: datetime,
) -> None:
    """Set a job `running` after `attempt_number` claims, as a stopped replica leaves it."""
    await run_statement(
        owner_engine,
        _LEAVE_JOB_RUNNING,
        attempt_number=attempt_number,
        lease_expires_at=lease_expires_at,
        suggestion_id=UUID(suggestion_id),
    )


async def complete_parts(
    engine: AsyncEngine, suggestion_id: SuggestionId, *completions: PartCompletion
) -> tuple[bool, ...]:
    """Complete parts in one committed transaction; return what each call returned."""
    written: list[bool] = []
    async with create_session_factory(engine)() as session:
        store = PostgresSuggestionJobStore(session)
        for completion in completions:
            written.append(await store.complete_part(suggestion_id, completion))
        await session.commit()
    return tuple(written)


def build_unavailable_parts(
    reason_code: AiReasonCode, completed_at: datetime
) -> tuple[PartCompletion, ...]:
    """Build the completions of both parts as unavailable with one reason code."""
    return tuple(
        build_unavailable_completion(part, reason_code, completed_at) for part in SuggestionPart
    )


async def save_request(
    engine: AsyncEngine, suggestion_id: SuggestionId, request: SuggestionRequest
) -> None:
    """Save the request of a suggestion and commit."""
    async with create_session_factory(engine)() as session:
        await PostgresSuggestionJobStore(session).save_request(suggestion_id, request)
        await session.commit()


async def load_part_statuses(builder: DatabaseBuilder, suggestion_id: SuggestionId) -> object:
    """Read the status of each part, as `{"analysis": ..., "draft": ...}`."""
    return await builder.scalar(_PART_STATUSES, suggestion_id=UUID(suggestion_id))


async def load_part_reason_codes(builder: DatabaseBuilder, suggestion_id: SuggestionId) -> object:
    """Read the reason codes of each part, as `{"analysis": [...], "draft": [...]}`."""
    return await builder.scalar(_PART_REASON_CODES, suggestion_id=UUID(suggestion_id))


async def load_job_state(builder: DatabaseBuilder, suggestion_id: SuggestionId) -> object:
    """Read the state and the attempt of a job, as `{"state": ..., "attempt_number": ...}`."""
    return await builder.scalar(_JOB_STATE, suggestion_id=UUID(suggestion_id))


async def load_authority_flag(builder: DatabaseBuilder, ticket_id: str) -> object:
    """Read `is_authority_required` of a ticket."""
    return await builder.scalar(_AUTHORITY_FLAG, ticket_id=ticket_id)


async def wait_until_row_lock_waits(
    builder: DatabaseBuilder, count: int, task: asyncio.Task[object]
) -> None:
    """Return once `count` transactions wait for a row lock, while `task` still runs.

    The loop of `tests.integration.accounts.lock_waits`, for a task of any result: each read
    gives the task its turn, and the lock timeout ends a task that waits too long (TEST-14).
    """
    while not task.done():
        if await builder.scalar(ROW_LOCK_WAITS) == count:
            return
    pytest.fail("The task ended before it waited for a row lock.")


def received_analysis_example(name: str) -> ReceivedAnalysis:
    """Parse an example of `createAnalysis` as the client of ai-service parses a response."""
    return parse_analysis_response(_example_body("createAnalysis", name))


def received_draft_example(name: str) -> ReceivedDraftOutcome:
    """Parse an example of `createDraft` as the client of ai-service parses a response."""
    return parse_draft_response(_example_body("createDraft", name))


def _example_body(operation: str, name: str) -> bytes:
    example = json.loads((EXAMPLES / operation / f"{name}.json").read_text(encoding="utf-8"))
    return json.dumps(example["value"]).encode()

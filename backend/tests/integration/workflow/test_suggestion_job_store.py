"""Adapter tests of `PostgresSuggestionJobStore` against PostgreSQL 17 (TEST-01).

The claim takes the oldest claimable job in one statement with `FOR UPDATE SKIP LOCKED`
(ADR-0011, item 2). A request is written once, and a part is written only while it is
`pending`, so a final part never changes (backend ticket workflow design, Tables). Two claims
of one job and the claim of an expired lease are in `test_ticket_workflow_schema.py`.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.suggestions import (
    AiReasonCode,
    ClaimedJob,
    JobState,
    LockedJob,
    SuggestionId,
    SuggestionRequest,
    build_analysis_completion,
    build_draft_completion,
)
from supportiq_backend.suggestions.adapters.ai_service_payloads import to_request_body
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionJobStore
from tests.integration.builders import DatabaseBuilder
from tests.integration.workflow.workflow_rows import (
    LEASE,
    build_new_suggestion,
    build_unavailable_parts,
    claim_job,
    complete_parts,
    insert_suggestion,
    insert_ticket,
    load_job_state,
    load_part_reason_codes,
    new_suggestion,
    received_analysis_example,
    received_draft_example,
    save_request,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

NOW = FAKE_CLOCK_START
COMPLETED_AT = FAKE_CLOCK_START + timedelta(seconds=4)
ONE_MILLISECOND = timedelta(milliseconds=1)
FIRST_ATTEMPT = 1
UNKNOWN_SUGGESTION_ID = SuggestionId("ffffffff-0000-4000-8000-000000000000")
REQUEST = SuggestionRequest(
    message="Where is the parcel of [ORDER_ID_1]?",
    order_context=None,
    as_of=FAKE_CLOCK_START,
    intent_override=None,
)
RUNNING_AFTER_ONE_CLAIM = {"state": "running", "attempt_number": FIRST_ATTEMPT}
DONE_AFTER_ONE_CLAIM = {"state": "done", "attempt_number": FIRST_ATTEMPT}
JOB_TIMES = "SELECT ARRAY[lease_expires_at, updated_at] FROM suggestion_jobs"
STORED_REQUEST = "SELECT request FROM suggestions"
ANALYSIS_COLUMNS = """
    SELECT jsonb_build_object(
        'status', status, 'reason_codes', reason_codes, 'release_id', release_id,
        'versions', versions, 'latency_ms', latency_ms, 'result', result
    )
    FROM suggestion_parts WHERE part = 'analysis'
"""
ANALYSIS_COMPLETED_AT = "SELECT completed_at FROM suggestion_parts WHERE part = 'analysis'"
ANALYSIS_MASKS_ARE_ABSENT = (
    "SELECT mask_count_by_type IS NULL FROM suggestion_parts WHERE part = 'analysis'"
)
PARTS_WITH_A_RESULT_COLUMN = """
    SELECT count(*) FROM suggestion_parts
    WHERE release_id IS NOT NULL OR versions IS NOT NULL OR latency_ms IS NOT NULL
        OR mask_count_by_type IS NOT NULL OR result IS NOT NULL
"""
DRAFT_USAGE = """
    SELECT jsonb_build_object(
        'input', llm_input_token_count, 'output', llm_output_token_count,
        'cost', llm_cost_micro_usd, 'masks', mask_count_by_type
    )
    FROM suggestion_parts WHERE part = 'draft'
"""


async def claim_next(engine: AsyncEngine, now: datetime) -> ClaimedJob | None:
    async with create_session_factory(engine)() as session:
        job = await PostgresSuggestionJobStore(session).claim_next(now, now + LEASE)
        await session.commit()
    return job


async def finish_job(engine: AsyncEngine, suggestion_id: SuggestionId, now: datetime) -> None:
    async with create_session_factory(engine)() as session:
        await PostgresSuggestionJobStore(session).finish_job(suggestion_id, now)
        await session.commit()


async def test_claim_next_claims_the_oldest_job_first(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    newer = build_new_suggestion(builder, await insert_ticket(builder), NOW + ONE_MILLISECOND)
    older = build_new_suggestion(builder, await insert_ticket(builder), NOW)
    await insert_suggestion(app_engine, newer)
    await insert_suggestion(app_engine, older)

    job = await claim_next(app_engine, NOW)

    assert job == ClaimedJob(older.suggestion_id, older.ticket_id, FIRST_ATTEMPT)


async def test_claim_next_sets_the_job_running_under_a_lease(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)

    await claim_next(app_engine, NOW)

    assert await load_job_state(builder, suggestion_id) == RUNNING_AFTER_ONE_CLAIM
    assert await builder.scalar(JOB_TIMES) == [NOW + LEASE, NOW]


async def test_claim_next_finds_nothing_while_the_lease_runs(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    await new_suggestion(app_engine, builder)
    await claim_job(app_engine, NOW)

    again = await claim_next(app_engine, NOW + LEASE - ONE_MILLISECOND)

    assert again is None


async def test_claim_next_never_claims_a_done_job(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    await finish_job(app_engine, suggestion_id, NOW)

    job = await claim_next(app_engine, NOW + LEASE)

    assert job is None


async def test_claim_next_skips_a_job_that_another_transaction_holds(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    held = await new_suggestion(app_engine, builder)
    free = await new_suggestion(app_engine, builder)

    async with create_session_factory(app_engine)() as holder:
        await PostgresSuggestionJobStore(holder).lock_job(held)
        job = await claim_next(app_engine, NOW)

    assert job is not None
    assert job.suggestion_id == free


async def test_lock_job_returns_the_state_and_the_attempt_of_the_job(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    await claim_job(app_engine, NOW)

    async with create_session_factory(app_engine)() as session:
        locked = await PostgresSuggestionJobStore(session).lock_job(suggestion_id)

    assert locked == LockedJob(JobState.RUNNING, FIRST_ATTEMPT)


async def test_lock_job_of_an_unknown_suggestion_is_none(app_engine: AsyncEngine) -> None:
    async with create_session_factory(app_engine)() as session:
        locked = await PostgresSuggestionJobStore(session).lock_job(UNKNOWN_SUGGESTION_ID)

    assert locked is None


async def test_save_request_stores_the_request_as_sent(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)

    await save_request(app_engine, suggestion_id, REQUEST)

    assert await builder.scalar(STORED_REQUEST) == json.loads(to_request_body(REQUEST))


async def test_save_request_keeps_the_first_request(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    await save_request(app_engine, suggestion_id, REQUEST)

    await save_request(app_engine, suggestion_id, replace(REQUEST, message="Another text."))

    assert await builder.scalar(STORED_REQUEST) == json.loads(to_request_body(REQUEST))


async def test_complete_part_writes_a_ready_analysis_as_received(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    received = received_analysis_example("draft")
    body = json.loads(received.body)

    written = await complete_parts(
        app_engine, suggestion_id, build_analysis_completion(received, COMPLETED_AT)
    )

    assert written == (True,)
    assert await builder.scalar(ANALYSIS_COLUMNS) == {
        "status": "ready",
        "reason_codes": body["routing"]["reason_codes"],
        "release_id": body["versions"]["release_id"],
        "versions": body["versions"],
        "latency_ms": body["step_latencies"]["total_ms"],
        "result": body,
    }
    assert await builder.scalar(ANALYSIS_COMPLETED_AT) == COMPLETED_AT


async def test_complete_part_writes_the_llm_usage_and_the_masks_of_a_draft(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    received = received_draft_example("draft-ready")
    body = json.loads(received.body)

    await complete_parts(app_engine, suggestion_id, build_draft_completion(received, COMPLETED_AT))

    assert await builder.scalar(DRAFT_USAGE) == {
        "input": body["llm_usage"]["input_token_count"],
        "output": body["llm_usage"]["output_token_count"],
        "cost": body["llm_usage"]["cost_micro_usd"],
        "masks": body["mask_count_by_type"],
    }


async def test_complete_part_leaves_the_masks_of_an_analysis_absent(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    analysis = build_analysis_completion(received_analysis_example("draft"), COMPLETED_AT)

    await complete_parts(app_engine, suggestion_id, analysis)

    # An analysis masks nothing. Absent is SQL NULL, never the JSON value `null`.
    assert await builder.scalar(ANALYSIS_MASKS_ARE_ABSENT) is True


async def test_complete_part_without_a_result_leaves_the_optional_columns_absent(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    failed = build_unavailable_parts(AiReasonCode.AI_SERVICE_UNAVAILABLE, COMPLETED_AT)

    await complete_parts(app_engine, suggestion_id, *failed)

    # Absent is SQL NULL, never the JSON value `null`, which `IS NOT NULL` matches (design,
    # Tables: "optional").
    assert await builder.scalar(PARTS_WITH_A_RESULT_COLUMN) == 0


async def test_complete_part_never_changes_a_final_part(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    failed = build_unavailable_parts(AiReasonCode.PSEUDONYMIZATION_FAILED, NOW)
    await complete_parts(app_engine, suggestion_id, *failed)
    analysis = build_analysis_completion(received_analysis_example("draft"), COMPLETED_AT)

    written = await complete_parts(app_engine, suggestion_id, analysis)

    assert written == (False,)
    assert await load_part_reason_codes(builder, suggestion_id) == {
        "analysis": ["pseudonymization_failed"],
        "draft": ["pseudonymization_failed"],
    }


async def test_finish_job_sets_the_job_done(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    await claim_job(app_engine, NOW)

    await finish_job(app_engine, suggestion_id, COMPLETED_AT)

    assert await load_job_state(builder, suggestion_id) == DONE_AFTER_ONE_CLAIM
    assert await builder.scalar(JOB_TIMES) == [NOW + LEASE, COMPLETED_AT]

"""The records of the decision-record export tests, with unique strings in every text (SEC-33).

The closed and the escalated ticket carry a text that must never be exported in each place that
holds one: the customer message, the reply body and its note, the escalation note, the AI's staff
note, and the original value of the pseudonym map. The pseudonymized message and the draft
segments are the only texts that the export may write. Every value is synthetic (TEST-18).
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from tests.integration.reports.report_rows import (
    BEFORE_START,
    END_AT,
    START_AT,
    DecisionRowSpec,
    PartRowSpec,
    ReportRows,
    ReportTicketSpec,
    SuggestionRowSpec,
    completed,
)
from tests.integration.tickets.console_requests import (
    PREDICTED_INTENT,
    asset_versions,
    draft_latencies,
    draft_ready_outcome,
    ready_analysis,
)

HOUR = timedelta(hours=1)
SECOND = timedelta(seconds=1)
MAP_VALUE = "ORD-90417"
PSEUDONYM = "[ORDER_ID_1]"
RAW_MESSAGE = f"Where is my order {MAP_VALUE}?"
PSEUDONYMIZED_MESSAGE = f"Where is my order {PSEUDONYM}?"
REPLY_BODY = "Reply-body-marker: your parcel left our warehouse today."
REPLY_NOTE = "Reply-note-marker for the manager."
ESCALATION_NOTE = "Escalation-note-marker for the manager."
AI_STAFF_NOTE = f"AI-staff-note-marker about {PSEUDONYM}."
STUDY_PAIR_ID = "pair-7"
STUDY_BATCH = "A"
UNEXPORTED_TEXTS = (MAP_VALUE, REPLY_BODY, REPLY_NOTE, ESCALATION_NOTE, AI_STAFF_NOTE)


@dataclass(frozen=True, slots=True)
class ExportTickets:
    """The tickets of the scenario, in the order of their ticket numbers.

    Attributes:
        closed: Closed in the period, from its AI draft, with a study pair.
        escalated: Escalated in the period.
        manual: In manual mode, closed in the period.
        failed: Closed in the period after its pseudonymization failed.
        closed_suggestion_id: The current suggestion of `closed`.
        escalated_suggestion_id: The current suggestion of `escalated`.
        failed_suggestion_id: The current suggestion of `failed`.
    """

    closed: str
    escalated: str
    manual: str
    failed: str
    closed_suggestion_id: UUID
    escalated_suggestion_id: UUID
    failed_suggestion_id: UUID


def sent_request() -> dict[str, object]:
    return {
        "message": PSEUDONYMIZED_MESSAGE,
        "order_context": {"order_status": "shipped"},
        "as_of": "2026-11-02T01:00:00Z",
    }


def draft_with_staff_note() -> dict[str, object]:
    return {**draft_ready_outcome(), "staff_note": AI_STAFF_NOTE}


def escalation_outcome() -> dict[str, object]:
    return {
        "status": "escalation_recommended",
        "reason_codes": ["human_agent_requested"],
        "analysis": ready_analysis(),
        "staff_note": AI_STAFF_NOTE,
        "versions": asset_versions(),
        "step_latencies": draft_latencies(),
        "mask_count_by_type": {"email": 0, "phone": 0, "card": 0},
    }


def exported_analysis() -> dict[str, object]:
    """Return the fields of `ready_analysis` that the export keeps: all but the latencies."""
    return {name: value for name, value in ready_analysis().items() if name != "step_latencies"}


async def insert_export_scenario(rows: ReportRows) -> ExportTickets:
    """Insert the four exported tickets and three that the period leaves out."""
    closed, closed_suggestion_id = await _insert_closed(rows)
    escalated, escalated_suggestion_id = await _insert_escalated(rows)
    manual = await rows.ticket(
        ReportTicketSpec(
            created_at=START_AT + 6 * HOUR,
            handling_mode="manual",
            status="closed",
            handling_started_at=START_AT + 6 * HOUR,
            closed_at=START_AT + 7 * HOUR,
            message=RAW_MESSAGE,
        )
    )
    failed, failed_suggestion_id = await _insert_failed_pseudonymization(rows)
    await _insert_tickets_outside_the_period(rows)
    return ExportTickets(
        closed=closed,
        escalated=escalated,
        manual=manual,
        failed=failed,
        closed_suggestion_id=closed_suggestion_id,
        escalated_suggestion_id=escalated_suggestion_id,
        failed_suggestion_id=failed_suggestion_id,
    )


async def _insert_closed(rows: ReportRows) -> tuple[str, UUID]:
    created_at = START_AT + HOUR
    ticket_id = await rows.ticket(
        ReportTicketSpec(
            created_at=created_at,
            status="closed",
            handling_started_at=created_at + HOUR,
            closed_at=created_at + 2 * HOUR,
            study_pair_id=STUDY_PAIR_ID,
            study_batch=STUDY_BATCH,
            message=RAW_MESSAGE,
        )
    )
    await rows.map_entry(ticket_id, PSEUDONYM, MAP_VALUE)
    suggestion_id = await rows.suggestion(
        ticket_id,
        SuggestionRowSpec(
            created_at=created_at,
            analysis=PartRowSpec("ready", created_at + SECOND, result=ready_analysis()),
            draft=PartRowSpec(
                "draft_ready", created_at + 3 * SECOND, result=draft_with_staff_note()
            ),
            request=sent_request(),
        ),
    )
    await rows.reply(ticket_id, suggestion_id, created_at + 2 * HOUR, REPLY_BODY, REPLY_NOTE)
    await rows.decision(
        ticket_id,
        DecisionRowSpec(
            "approve",
            created_at + 2 * HOUR,
            suggestion_id=suggestion_id,
            change_ratio=0,
            final_intent=PREDICTED_INTENT,
        ),
    )
    return ticket_id, suggestion_id


async def _insert_escalated(rows: ReportRows) -> tuple[str, UUID]:
    created_at = START_AT + 4 * HOUR
    ticket_id = await rows.ticket(
        ReportTicketSpec(
            created_at=created_at,
            status="escalated",
            handling_started_at=created_at + HOUR,
            message=RAW_MESSAGE,
        )
    )
    await rows.map_entry(ticket_id, PSEUDONYM, MAP_VALUE)
    draft = PartRowSpec(
        "escalation_recommended",
        created_at + 3 * SECOND,
        ("human_agent_requested",),
        result=escalation_outcome(),
    )
    suggestion_id = await rows.suggestion(
        ticket_id,
        SuggestionRowSpec(
            created_at=created_at,
            analysis=PartRowSpec("ready", created_at + SECOND, result=ready_analysis()),
            draft=draft,
            request=sent_request(),
        ),
    )
    escalated_at = created_at + 2 * HOUR
    await rows.escalation(ticket_id, escalated_at, "case_exception", note=ESCALATION_NOTE)
    await rows.decision(
        ticket_id,
        DecisionRowSpec(
            "escalate",
            escalated_at,
            ("case_exception",),
            suggestion_id=suggestion_id,
            final_intent=PREDICTED_INTENT,
        ),
    )
    return ticket_id, suggestion_id


async def _insert_failed_pseudonymization(rows: ReportRows) -> tuple[str, UUID]:
    created_at = START_AT + 7 * HOUR
    ticket_id = await rows.ticket(
        ReportTicketSpec(
            created_at=created_at,
            status="closed",
            closed_at=created_at + HOUR,
            message=RAW_MESSAGE,
        )
    )
    failure = completed("unavailable", created_at + SECOND, "pseudonymization_failed")
    suggestion_id = await rows.suggestion(
        ticket_id, SuggestionRowSpec(created_at=created_at, analysis=failure, draft=failure)
    )
    return ticket_id, suggestion_id


async def _insert_tickets_outside_the_period(rows: ReportRows) -> None:
    await rows.tickets(
        ReportTicketSpec(created_at=START_AT, message=RAW_MESSAGE),
        ReportTicketSpec(created_at=BEFORE_START, status="closed", closed_at=END_AT),
    )
    early = await rows.ticket(ReportTicketSpec(created_at=BEFORE_START, status="escalated"))
    await rows.escalation(early, BEFORE_START + HOUR, "kb_gap")

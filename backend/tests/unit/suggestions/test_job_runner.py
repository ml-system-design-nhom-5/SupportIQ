"""Tests of `SuggestionJobRunner` with fakes of every port (backend ticket workflow design).

The guardrail tests of TEST-26 are here: no call to ai-service when pseudonymization fails
(SEC-36), and no seeded personal value in any request to ai-service (FR-09, NFR-06).
"""

from dataclasses import dataclass, field, replace

import pytest

from supportiq_backend.audit import AuditEventType
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import EventName
from supportiq_backend.pseudonymization import (
    DetectorError,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
)
from supportiq_backend.suggestions import (
    AiReasonCode,
    AiServiceContractError,
    ClaimedJob,
    JobRunnerPorts,
    JobState,
    JobStores,
    MessagePseudonymizer,
    PartStatus,
    QueueSettings,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    SuggestionJobRunner,
    SuggestionPart,
    SuggestionRequest,
    TicketForSuggestion,
    TicketMessage,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.commerce.fakes import FakeCommerceGateway, build_order
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.pseudonymization.fakes import (
    CONTACT,
    CUSTOMER_ID,
    REFERENCES,
    FakeCustomerRecords,
    FakePseudonymMapStore,
)
from tests.unit.suggestions.builders import (
    ANALYSIS_BODY,
    DRAFT_BODY,
    PREDICTED_INTENT,
    SUGGESTION_ID,
    TICKET_ID,
    build_analysis,
    build_draft_ready,
    build_suggestion,
    received_draft,
)
from tests.unit.suggestions.fakes import (
    FakeAiService,
    FakePseudonymizer,
    FakeSuggestionData,
    FakeSuggestionJobStore,
    FakeSuggestionStore,
    FakeTicketLinks,
)

QUEUE_SETTINGS = QueueSettings(workers_per_replica=5, lease_ms=15_000, max_attempts=3, poll_ms=500)
JOB = ClaimedJob(SUGGESTION_ID, TICKET_ID, attempt_number=1)
MESSAGE = "I am Lan Tran, order ORD-20901, mail lan.tran@example.test, phone +84 90 111 0001."
BOTH_CALLS = 2
OWN_ANALYSIS_BODY = '{"analysis": "from createAnalysis"}'
SEEDED_VALUES = (
    CONTACT.display_name,
    CONTACT.email,
    CONTACT.phone,
    REFERENCES.order_id,
)


@dataclass(slots=True)
class Harness:
    """The runner with its fakes."""

    runner: SuggestionJobRunner
    data: FakeSuggestionData
    links: FakeTicketLinks
    ai_service: FakeAiService
    audit: FakeAuditLog
    events: RecordingEventRecorder


@dataclass(slots=True)
class SupersedingAiService(FakeAiService):
    """An ai-service whose draft call returns after a new suggestion became current."""

    links: FakeTicketLinks = field(default_factory=FakeTicketLinks)

    async def draft(self, request: SuggestionRequest) -> ReceivedDraftOutcome:
        """Supersede the suggestion, then answer."""
        ticket = self.links.tickets[TICKET_ID]
        self.links.tickets[TICKET_ID] = replace(ticket, current_suggestion_id=None)
        return await FakeAiService.draft(self, request)


def build_harness(
    *,
    ai_service: FakeAiService | None = None,
    pseudonymizer: MessagePseudonymizer | None = None,
    attempt_number: int = 1,
    intent_override: bool = False,
) -> Harness:
    data = FakeSuggestionData()
    suggestion = build_suggestion(intent_override=PREDICTED_INTENT if intent_override else None)
    data.add(suggestion, state=JobState.RUNNING)
    data.jobs[SUGGESTION_ID].attempt_number = attempt_number
    data.state_by_body.update(
        {
            ANALYSIS_BODY: build_analysis(),
            OWN_ANALYSIS_BODY: build_analysis(),
            DRAFT_BODY: build_draft_ready(),
        }
    )
    links = FakeTicketLinks(
        tickets={TICKET_ID: TicketForSuggestion(SUGGESTION_ID, True, True, "open")},
        messages={
            TICKET_ID: TicketMessage(
                TICKET_ID, MESSAGE, FAKE_CLOCK_START, CUSTOMER_ID, OrderId(REFERENCES.order_id)
            )
        },
    )
    service = ai_service or FakeAiService(
        analysis_result=ReceivedAnalysis(build_analysis(), OWN_ANALYSIS_BODY),
        draft_result=received_draft(),
    )
    if isinstance(service, SupersedingAiService):
        service.links = links
    audit = FakeAuditLog()
    events = RecordingEventRecorder()
    stores = JobStores(
        jobs=FakeSuggestionJobStore(data),
        suggestions=FakeSuggestionStore(data),
        tickets=links,
        authority=links,
        orders=FakeCommerceGateway(orders={CUSTOMER_ID: (build_order(REFERENCES.order_id),)}),
        audit=audit,
    )
    runner = SuggestionJobRunner(
        FakeTransactionRunner(stores),
        JobRunnerPorts(
            pseudonymizer=pseudonymizer or FakePseudonymizer({"Lan Tran": "[NAME_1]"}),
            ai_service=service,
            clock=FakeClock(),
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=events,
            steps=RecordingStepTracer(),
        ),
        QUEUE_SETTINGS,
    )
    return Harness(runner, data, links, service, audit, events)


def statuses(harness: Harness) -> dict[SuggestionPart, tuple[PartStatus, tuple[AiReasonCode, ...]]]:
    return {
        completion.part: (completion.status, completion.reason_codes)
        for completion in harness.data.completions
    }


def real_pseudonymizer() -> PseudonymizeMessage:
    stores = PseudonymizationStores(FakePseudonymMapStore(), FakeCustomerRecords(), FakeAuditLog())
    return PseudonymizeMessage(
        FakeTransactionRunner(stores),
        PseudonymizationPorts(
            detectors=(LiteralPlaceholderDetector(), KnownValueDetector(), PatternDetector()),
            clock=FakeClock(),
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=RecordingEventRecorder(),
            steps=RecordingStepTracer(),
        ),
    )


@pytest.mark.anyio
async def test_a_failed_pseudonymization_sends_nothing_and_ends_both_parts() -> None:
    harness = build_harness(pseudonymizer=FakePseudonymizer(failure=DetectorError()))

    await harness.runner.run(JOB)

    assert harness.ai_service.requests == ()
    assert statuses(harness) == {
        SuggestionPart.ANALYSIS: (PartStatus.UNAVAILABLE, (AiReasonCode.PSEUDONYMIZATION_FAILED,)),
        SuggestionPart.DRAFT: (PartStatus.UNAVAILABLE, (AiReasonCode.PSEUDONYMIZATION_FAILED,)),
    }
    assert harness.data.jobs[SUGGESTION_ID].state is JobState.DONE


@pytest.mark.anyio
@pytest.mark.parametrize("seeded_value", SEEDED_VALUES)
async def test_no_seeded_personal_value_reaches_a_request_to_ai_service(seeded_value: str) -> None:
    harness = build_harness(pseudonymizer=real_pseudonymizer())

    await harness.runner.run(JOB)

    assert len(harness.ai_service.requests) == BOTH_CALLS
    assert all(seeded_value not in request.message for request in harness.ai_service.requests)


@pytest.mark.anyio
async def test_a_job_stores_the_analysis_and_the_draft_and_ends() -> None:
    harness = build_harness()

    await harness.runner.run(JOB)

    assert statuses(harness) == {
        SuggestionPart.ANALYSIS: (PartStatus.READY, ()),
        SuggestionPart.DRAFT: (PartStatus.DRAFT_READY, ()),
    }
    assert harness.data.completions[0].result_body == OWN_ANALYSIS_BODY
    assert harness.data.jobs[SUGGESTION_ID].state is JobState.DONE
    assert [entry.event_type for entry in harness.audit.entries] == [
        AuditEventType.SUGGESTION_PART_COMPLETED,
        AuditEventType.SUGGESTION_PART_COMPLETED,
    ]


@pytest.mark.anyio
async def test_the_request_uses_the_pseudonymized_text_and_the_tickets_creation_time() -> None:
    harness = build_harness()

    await harness.runner.run(JOB)

    (request,) = harness.ai_service.draft_requests
    assert request.message.startswith("I am [NAME_1]")
    assert request.as_of == FAKE_CLOCK_START
    assert request.intent_override is None
    assert harness.data.requests[SUGGESTION_ID] == request


@pytest.mark.anyio
async def test_a_draft_that_requires_authority_sets_the_flag_in_the_same_transaction() -> None:
    authority = (AiReasonCode.REQUIRES_AUTHORITY,)
    outcome = build_draft_ready(reason_codes=authority)
    harness = build_harness(
        ai_service=FakeAiService(
            analysis_result=AiServiceContractError(), draft_result=received_draft(outcome)
        )
    )
    harness.data.state_by_body[DRAFT_BODY] = outcome

    await harness.runner.run(JOB)

    assert harness.links.authority_required == {TICKET_ID}


@pytest.mark.anyio
async def test_a_failed_analysis_call_takes_the_analysis_of_the_draft() -> None:
    harness = build_harness(
        ai_service=FakeAiService(
            analysis_result=AiServiceContractError(), draft_result=received_draft()
        )
    )

    await harness.runner.run(JOB)

    analysis = next(c for c in harness.data.completions if c.part is SuggestionPart.ANALYSIS)
    assert analysis.status is PartStatus.READY
    assert analysis.result_body == ANALYSIS_BODY
    assert EventName.AI_SERVICE_CONTRACT_VIOLATED in harness.events.names()


@pytest.mark.anyio
async def test_both_calls_failing_end_both_parts_unavailable() -> None:
    harness = build_harness(ai_service=FakeAiService())

    await harness.runner.run(JOB)

    assert statuses(harness) == {
        SuggestionPart.ANALYSIS: (PartStatus.UNAVAILABLE, (AiReasonCode.AI_SERVICE_UNAVAILABLE,)),
        SuggestionPart.DRAFT: (PartStatus.UNAVAILABLE, (AiReasonCode.AI_SERVICE_UNAVAILABLE,)),
    }
    assert EventName.TICKET_MANUAL_HANDLING_STARTED in harness.events.names()


@pytest.mark.anyio
async def test_a_failed_draft_after_a_ready_analysis_keeps_the_analysis() -> None:
    harness = build_harness(
        ai_service=FakeAiService(
            analysis_result=ReceivedAnalysis(build_analysis(), OWN_ANALYSIS_BODY)
        )
    )

    await harness.runner.run(JOB)

    assert statuses(harness) == {
        SuggestionPart.ANALYSIS: (PartStatus.READY, ()),
        SuggestionPart.DRAFT: (PartStatus.UNAVAILABLE, (AiReasonCode.AI_SERVICE_UNAVAILABLE,)),
    }


@pytest.mark.anyio
async def test_an_intent_override_calls_only_the_draft_with_the_chosen_intent() -> None:
    harness = build_harness(intent_override=True)

    await harness.runner.run(JOB)

    assert harness.ai_service.analysis_requests == []
    (request,) = harness.ai_service.draft_requests
    assert request.intent_override is PREDICTED_INTENT


@pytest.mark.anyio
async def test_a_superseded_suggestion_ends_its_job_without_a_call() -> None:
    harness = build_harness()
    harness.links.tickets[TICKET_ID] = TicketForSuggestion(None, True, True, "open")

    await harness.runner.run(JOB)

    assert harness.ai_service.requests == ()
    assert harness.data.completions == []
    assert harness.data.jobs[SUGGESTION_ID].state is JobState.DONE


@pytest.mark.anyio
async def test_a_result_that_arrives_after_the_suggestion_was_superseded_is_discarded() -> None:
    harness = build_harness(
        ai_service=SupersedingAiService(
            analysis_result=AiServiceContractError(), draft_result=received_draft()
        )
    )

    await harness.runner.run(JOB)

    assert harness.data.completions == []


@pytest.mark.anyio
async def test_an_older_attempt_stores_nothing_and_calls_nothing() -> None:
    harness = build_harness(attempt_number=2)

    await harness.runner.run(JOB)

    assert harness.ai_service.requests == ()
    assert harness.data.completions == []


@pytest.mark.anyio
async def test_a_job_out_of_attempts_ends_unavailable_without_a_call() -> None:
    claim = ClaimedJob(SUGGESTION_ID, TICKET_ID, attempt_number=QUEUE_SETTINGS.max_attempts + 1)
    harness = build_harness(attempt_number=claim.attempt_number)

    await harness.runner.run(claim)

    assert harness.ai_service.requests == ()
    assert statuses(harness)[SuggestionPart.DRAFT] == (
        PartStatus.UNAVAILABLE,
        (AiReasonCode.AI_SERVICE_UNAVAILABLE,),
    )
    assert EventName.SUGGESTION_JOB_LEASE_EXPIRED in harness.events.names()


@pytest.mark.anyio
async def test_the_analysis_part_is_stored_once_even_when_the_draft_repeats_it() -> None:
    harness = build_harness()

    await harness.runner.run(JOB)

    parts = [completion.part for completion in harness.data.completions]
    assert parts.count(SuggestionPart.ANALYSIS) == 1

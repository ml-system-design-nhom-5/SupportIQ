"""The pipeline of a release routes first, calls the LLM only for a draft, and never fails a draft.

Every adapter is a fake: the LLM is a writer that answers from a script and keeps each request,
as a fake LLM adapter captures its payload (TEST-26).
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

import pytest

from supportiq_ai_service.drafting import (
    DraftReply,
    DraftRequest,
    LlmCallError,
    LlmFailure,
    TokenPrices,
    TokenUsage,
    UnanswerableRequest,
    WrittenDraft,
)
from supportiq_ai_service.intent import IntentDistribution
from supportiq_ai_service.platform import EventAttributeValue, EventName
from supportiq_ai_service.retrieval import DocumentMatch
from supportiq_ai_service.suggestions.application.release_pipeline import (
    PipelinePorts,
    PipelineValues,
    ReleasePipeline,
)
from supportiq_ai_service.suggestions.domain import (
    AnalysisWarning,
    AuthorityCategory,
    ConfidenceBand,
    DocumentIntents,
    DocumentValidity,
    DraftReady,
    IntentName,
    LlmUsage,
    MaskCounts,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OrderFacts,
    ReasonCode,
    RoutingConfiguration,
    RoutingRecommendation,
    SensitiveTerm,
    StaffIntent,
    StepLatencies,
    SuggestionInput,
)
from tests.unit.intent.fakes import distribution
from tests.unit.platform.fakes import RecordedEvent, RecordingEventRecorder
from tests.unit.release.fakes import EXAMPLE_RELEASE
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT

AS_OF = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
DELIVERY = dataclasses.replace(
    EXAMPLE_DOCUMENT, document_id="DELIVERY", policy_key="delivery", body="Parcels ship daily."
)
# A version that ended before `AS_OF`.
EXPIRED_DELIVERY = dataclasses.replace(
    DELIVERY, document_id="OLD", effective_end_at=datetime(2026, 1, 1, tzinfo=UTC)
)
# Another version in effect with the same policy key, so the two conflict.
SECOND_DELIVERY = dataclasses.replace(
    DELIVERY, document_id="DELIVERY-2", body="Parcels ship weekly."
)
ROUTING = RoutingConfiguration(
    version="routing-sample-1",
    model_version="intent-model-sample-1",
    min_top_probability=0.5,
    min_top_two_gap=0.1,
    rerank_weight=0.2,
    high_band_min_probability=0.9,
    sensitive_intents=frozenset({IntentName("request_refund")}),
    sensitive_intent_min_probability=0.2,
    sensitive_terms=(SensitiveTerm("lawyer", AuthorityCategory.LEGAL_CLAIM),),
)
MAPPING = DocumentIntents(
    MappingProxyType({("DELIVERY", "1.0"): frozenset({IntentName("track_order")})})
)
# Fixture prices, never the prices of the provider.
VALUES = PipelineValues(
    routing=ROUTING,
    mapping=MAPPING,
    top_k_documents=3,
    token_budget_tokens=100,
    uncited_segment_max_chars=40,
    prices=TokenPrices(1_000, 2_000),
)
USAGE = TokenUsage(input_token_count=1_000, output_token_count=500)
CONTRACT_USAGE = LlmUsage(input_token_count=1_000, output_token_count=500, cost_micro_usd=2)
MESSAGE = "Where is my parcel? Mail me at an.example@example.com."
GROUNDED = WrittenDraft(
    text="Parcels ship daily [S1]. Your parcel is in_transit [S2].",
    cited_source_ids=("S1", "S2"),
    is_clarification=False,
    usage=USAGE,
)


@dataclass(slots=True)
class FakeModel:
    """A classifier, a search, and an LLM writer that answer what a test chose."""

    intents: IntentDistribution = field(
        default_factory=lambda: distribution(("track_order", 0.95), ("delivery_time", 0.05))
    )
    matches: tuple[DocumentMatch, ...] = (DocumentMatch(DELIVERY, 0.9, (DELIVERY.body,)),)
    reply: DraftReply | LlmCallError = GROUNDED
    requests: list[DraftRequest] = field(default_factory=list[DraftRequest])
    now: float = 0.0

    def classify(self, message: str) -> IntentDistribution:
        """Return the chosen distribution."""
        del message
        self.now += 0.1
        return self.intents

    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        """Return the chosen matches."""
        del message
        self.now += 0.2
        return self.matches

    def write(self, request: DraftRequest) -> DraftReply:
        """Keep the request, and answer the chosen reply or raise the chosen error.

        Raises:
            LlmCallError: The chosen reply is an error.
        """
        self.requests.append(request)
        self.now += 1.5
        if isinstance(self.reply, LlmCallError):
            raise self.reply
        return self.reply

    def monotonic(self) -> float:
        """Return the time of the fake clock."""
        return self.now


def _pipeline(
    model: FakeModel, events: RecordingEventRecorder | None = None, values: PipelineValues = VALUES
) -> ReleasePipeline:
    ports = PipelinePorts(
        classifier=model,
        search=model,
        writer=model,
        count_tokens=lambda text: len(text.split()),
    )
    return ReleasePipeline(ports, values, events or RecordingEventRecorder(), model.monotonic)


def _request(**changes: object) -> SuggestionInput:
    request = SuggestionInput(
        message=MESSAGE,
        as_of=AS_OF,
        order_facts=OrderFacts(
            shipment_status="in_transit", placed_at=datetime(2026, 11, 1, 23, 0, tzinfo=UTC)
        ),
    )
    return dataclasses.replace(request, **changes)


def _codes(*codes: str) -> tuple[ReasonCode, ...]:
    return tuple(ReasonCode(code) for code in codes)


@pytest.mark.anyio
async def test_an_analysis_ranks_the_documents_and_routes_without_the_llm() -> None:
    model = FakeModel()

    analysis = await _pipeline(model).analyze(_request(), EXAMPLE_RELEASE)

    assert analysis.intent == ModelIntent(IntentName("track_order"), 0.95, ConfidenceBand.HIGH)
    assert analysis.is_in_scope
    (document,) = analysis.documents
    assert (document.document_id, document.validity, document.rank, document.snippet) == (
        "DELIVERY",
        DocumentValidity.VALID,
        1,
        DELIVERY.body,
    )
    assert analysis.routing.recommendation is RoutingRecommendation.DRAFT
    assert analysis.warnings == ()
    assert analysis.versions == EXAMPLE_RELEASE.versions
    assert analysis.step_latencies == StepLatencies(total_ms=300, analysis_ms=300)
    assert model.requests == []


@pytest.mark.anyio
async def test_a_disagreement_is_a_warning_that_lowers_the_band_but_never_abstains() -> None:
    model = FakeModel(intents=distribution(("delivery_time", 0.95), ("track_order", 0.05)))

    analysis = await _pipeline(model).analyze(_request(), EXAMPLE_RELEASE)

    assert analysis.warnings == (AnalysisWarning("warning-1", ReasonCode("signal_disagreement")),)
    assert analysis.intent == ModelIntent(IntentName("delivery_time"), 0.95, ConfidenceBand.MEDIUM)
    assert analysis.routing.recommendation is RoutingRecommendation.DRAFT


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("probability", "band"), [(0.7, ConfidenceBand.MEDIUM), (0.45, ConfidenceBand.LOW)]
)
async def test_a_disagreement_never_raises_the_band(
    probability: float, band: ConfidenceBand
) -> None:
    model = FakeModel(intents=distribution(("delivery_time", probability), ("track_order", 0.05)))

    analysis = await _pipeline(model).analyze(_request(), EXAMPLE_RELEASE)

    assert analysis.warnings == (AnalysisWarning("warning-1", ReasonCode("signal_disagreement")),)
    assert analysis.intent == ModelIntent(IntentName("delivery_time"), probability, band)


@pytest.mark.anyio
async def test_a_staff_choice_reranks_the_documents_and_decides_the_disagreement() -> None:
    # The model leans to `track_order`, the intent of DELIVERY; staff chose `delivery_time`,
    # the intent of SCHEDULE only (ADR-0005, statement 7).
    schedule = dataclasses.replace(DELIVERY, document_id="SCHEDULE", policy_key="schedule")
    model = FakeModel(
        intents=distribution(("track_order", 0.95), ("delivery_time", 0.05)),
        matches=(
            DocumentMatch(DELIVERY, 0.8, (DELIVERY.body,)),
            DocumentMatch(schedule, 0.79, (schedule.body,)),
        ),
    )
    mapping = DocumentIntents(
        MappingProxyType(
            {
                ("DELIVERY", "1.0"): frozenset({IntentName("track_order")}),
                ("SCHEDULE", "1.0"): frozenset({IntentName("delivery_time")}),
            }
        )
    )
    values = dataclasses.replace(VALUES, mapping=mapping, top_k_documents=1)

    analysis = await _pipeline(model, values=values).analyze(
        _request(intent_override=IntentName("delivery_time")), EXAMPLE_RELEASE
    )

    assert [document.document_id for document in analysis.documents] == ["SCHEDULE"]
    assert analysis.warnings == ()


@pytest.mark.anyio
async def test_an_intent_outside_the_scope_is_marked_and_abstains() -> None:
    model = FakeModel(intents=distribution(("store_location", 0.95)))

    analysis = await _pipeline(model).analyze(_request(), EXAMPLE_RELEASE)

    assert not analysis.is_in_scope
    assert analysis.routing.recommendation is RoutingRecommendation.ABSTAIN
    assert ReasonCode("out_of_scope_intent") in analysis.routing.reason_codes


@pytest.mark.anyio
async def test_a_staff_choice_is_the_intent_of_the_draft() -> None:
    # The model alone is not confident enough to draft (ESC-01).
    model = FakeModel(intents=distribution(("delivery_time", 0.4), ("track_order", 0.39)))

    outcome = await _pipeline(model).draft(
        _request(intent_override=IntentName("track_order")), EXAMPLE_RELEASE
    )

    assert isinstance(outcome, DraftReady)
    assert outcome.details.analysis.intent == StaffIntent(IntentName("track_order"))
    assert [request.intent for request in model.requests] == ["track_order"]


@pytest.mark.anyio
async def test_a_sensitive_intent_chosen_by_staff_requires_authority() -> None:
    # The model leans to `track_order`, and the message holds no sensitive term (FR-06).
    model = FakeModel()
    requires_authority = ReasonCode("requires_authority")

    outcome = await _pipeline(model).draft(
        _request(intent_override=IntentName("request_refund")), EXAMPLE_RELEASE
    )

    assert isinstance(outcome, DraftReady)
    assert requires_authority in outcome.details.analysis.routing.reason_codes
    assert requires_authority in outcome.details.reason_codes
    assert [request.requires_authority for request in model.requests] == [True]


@pytest.mark.anyio
async def test_a_staff_choice_has_no_band_and_no_alternatives() -> None:
    model = FakeModel(intents=distribution(("delivery_time", 0.4), ("track_order", 0.39)))

    analysis = await _pipeline(model).analyze(
        _request(intent_override=IntentName("track_order")), EXAMPLE_RELEASE
    )

    assert analysis.intent == StaffIntent(IntentName("track_order"))
    assert analysis.alternatives == ()
    assert analysis.routing.recommendation is RoutingRecommendation.DRAFT


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model", "status", "codes"),
    [
        (FakeModel(matches=()), NoDraftStatus.ABSTAINED, ("no_valid_document",)),
        (
            FakeModel(intents=distribution(("human_agent", 0.95))),
            NoDraftStatus.ESCALATION_RECOMMENDED,
            ("human_agent_requested",),
        ),
        (
            FakeModel(intents=distribution(("track_order", 0.4), ("delivery_time", 0.35))),
            NoDraftStatus.ABSTAINED,
            ("low_confidence",),
        ),
        (
            FakeModel(
                matches=(
                    DocumentMatch(DELIVERY, 0.9, (DELIVERY.body,)),
                    DocumentMatch(SECOND_DELIVERY, 0.85, (SECOND_DELIVERY.body,)),
                )
            ),
            NoDraftStatus.ABSTAINED,
            ("conflicting_sources",),
        ),
        (
            FakeModel(intents=distribution(("store_location", 0.95))),
            NoDraftStatus.ABSTAINED,
            ("out_of_scope_intent",),
        ),
    ],
)
async def test_an_abstention_or_an_escalation_never_calls_the_llm(
    model: FakeModel, status: NoDraftStatus, codes: tuple[str, ...]
) -> None:
    events = RecordingEventRecorder()

    outcome = await _pipeline(model, events).draft(_request(), EXAMPLE_RELEASE)

    assert isinstance(outcome, NoDraft)
    assert outcome.status is status
    assert outcome.details.reason_codes == _codes(*codes)
    assert outcome.details.mask_counts == MaskCounts(email=0, phone=0, card=0)
    assert outcome.details.llm_usage is None
    assert outcome.details.step_latencies.llm_ms is None
    assert model.requests == []
    assert events.of(EventName.PERSONAL_DATA_MASKED) == ()


@pytest.mark.anyio
async def test_a_grounded_draft_is_ready_with_its_usage_masks_and_latencies() -> None:
    model = FakeModel()
    events = RecordingEventRecorder()

    outcome = await _pipeline(model, events).draft(_request(), EXAMPLE_RELEASE)

    assert isinstance(outcome, DraftReady)
    assert [segment.citation_ids for segment in outcome.draft.segments] == [("S1", "S2")]
    assert outcome.details.reason_codes == ()
    assert outcome.details.llm_usage == CONTRACT_USAGE
    assert outcome.details.mask_counts == MaskCounts(email=1, phone=0, card=0)
    assert outcome.details.step_latencies == StepLatencies(
        total_ms=1800, analysis_ms=300, llm_ms=1500
    )
    (request,) = model.requests
    assert request.message == "Where is my parcel? Mail me at [EMAIL]."
    assert [(fact.source_id, fact.field, fact.value) for fact in request.order_facts] == [
        ("S2", "shipment_status", "in_transit"),
        ("S3", "placed_at", "2026-11-01"),
    ]
    (masked,) = events.of(EventName.PERSONAL_DATA_MASKED)
    assert masked.attributes == {"mask_type": "email", "mask_count": 1}


@pytest.mark.anyio
async def test_no_event_holds_the_message_the_prompt_or_the_draft() -> None:
    events = RecordingEventRecorder()

    await _pipeline(FakeModel(), events).draft(_request(), EXAMPLE_RELEASE)

    recorded = " ".join(
        str(value) for event in events.events for value in event.attributes.values()
    )
    for text in (
        MESSAGE,
        "an.example@example.com",
        "Where is my parcel",
        GROUNDED.text,
        DELIVERY.body,
    ):
        assert text not in recorded


@pytest.mark.anyio
async def test_the_authority_flag_of_routing_reaches_the_draft_and_its_prompt() -> None:
    model = FakeModel()

    outcome = await _pipeline(model).draft(
        _request(message="Where is my parcel? My lawyer asks."), EXAMPLE_RELEASE
    )

    assert isinstance(outcome, DraftReady)
    assert outcome.details.analysis.routing.reason_codes == _codes("requires_authority")
    assert outcome.details.reason_codes == _codes("requires_authority")
    assert model.requests[0].requires_authority is True


@pytest.mark.anyio
async def test_the_drafting_step_never_adds_the_authority_flag() -> None:
    model = FakeModel()

    outcome = await _pipeline(model).draft(_request(), EXAMPLE_RELEASE)

    assert ReasonCode("requires_authority") not in outcome.details.reason_codes
    assert model.requests[0].requires_authority is False


@pytest.mark.anyio
async def test_a_clarification_is_ready_with_missing_information() -> None:
    asking = WrittenDraft(
        text="Could you tell us which parcel you mean?",
        cited_source_ids=(),
        is_clarification=True,
        usage=USAGE,
    )

    outcome = await _pipeline(FakeModel(reply=asking)).draft(_request(), EXAMPLE_RELEASE)

    assert isinstance(outcome, DraftReady)
    assert outcome.details.reason_codes == _codes("missing_information")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("reply", "status", "code", "usage"),
    [
        (
            LlmCallError(LlmFailure.UNAVAILABLE),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_unavailable",
            None,
        ),
        (
            LlmCallError(LlmFailure.INVALID_OUTPUT, USAGE),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_invalid_output",
            CONTRACT_USAGE,
        ),
        (
            dataclasses.replace(
                GROUNDED, text="Your parcel is late [S2].", cited_source_ids=("S2",)
            ),
            NoDraftStatus.LLM_UNAVAILABLE,
            "grounding_failed",
            CONTRACT_USAGE,
        ),
        (
            dataclasses.replace(
                GROUNDED, text="Your order [ORDER_ID_9] ships daily [S1].", cited_source_ids=("S1",)
            ),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_invalid_output",
            CONTRACT_USAGE,
        ),
        (
            UnanswerableRequest(usage=USAGE),
            NoDraftStatus.ABSTAINED,
            "no_valid_document",
            CONTRACT_USAGE,
        ),
        (
            dataclasses.replace(GROUNDED, usage=TokenUsage(1_000_001, 0)),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_invalid_output",
            None,
        ),
        (
            LlmCallError(LlmFailure.UNAVAILABLE, TokenUsage(0, 1_000_001)),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_invalid_output",
            None,
        ),
        # The final code chooses the status, so `llm_invalid_output` is never an abstention.
        (
            UnanswerableRequest(usage=TokenUsage(1_000_001, 0)),
            NoDraftStatus.LLM_UNAVAILABLE,
            "llm_invalid_output",
            None,
        ),
    ],
)
async def test_a_failure_of_the_drafting_step_is_an_outcome_with_its_reason(
    reply: DraftReply | LlmCallError, status: NoDraftStatus, code: str, usage: LlmUsage | None
) -> None:
    outcome = await _pipeline(FakeModel(reply=reply)).draft(_request(), EXAMPLE_RELEASE)

    assert isinstance(outcome, NoDraft)
    assert (outcome.status, outcome.details.reason_codes, outcome.details.llm_usage) == (
        status,
        _codes(code),
        usage,
    )
    assert outcome.details.mask_counts == MaskCounts(email=1, phone=0, card=0)
    assert outcome.details.step_latencies.llm_ms == 1500  # noqa: PLR2004  # one fake LLM call


@pytest.mark.anyio
async def test_the_passages_of_a_prompt_stay_within_the_token_budget() -> None:
    long = "word " * 80
    second = dataclasses.replace(DELIVERY, document_id="DELIVERY-B", policy_key="delivery-b")
    model = FakeModel(
        matches=(
            DocumentMatch(DELIVERY, 0.9, (long, "Parcels ship daily.")),
            DocumentMatch(second, 0.8, (long,)),
        )
    )
    values = dataclasses.replace(VALUES, token_budget_tokens=85)

    await _pipeline(model, values=values).draft(_request(), EXAMPLE_RELEASE)

    sources = model.requests[0].policy_sources
    assert [(source.source_id, source.document_id) for source in sources] == [
        ("S1", "DELIVERY"),
        ("S2", "DELIVERY"),
    ]
    assert model.requests[0].order_facts[0].source_id == "S3"


@pytest.mark.anyio
async def test_passages_that_fill_the_token_budget_exactly_are_all_sent() -> None:
    # 60 and 40 words, as the fake encoder counts tokens: exactly the budget of 100.
    model = FakeModel(matches=(DocumentMatch(DELIVERY, 0.9, ("word " * 60, "word " * 40)),))

    await _pipeline(model).draft(_request(), EXAMPLE_RELEASE)

    assert [source.source_id for source in model.requests[0].policy_sources] == ["S1", "S2"]


@pytest.mark.anyio
async def test_a_first_passage_longer_than_the_token_budget_is_still_sent() -> None:
    model = FakeModel(matches=(DocumentMatch(DELIVERY, 0.9, ("word " * 150,)),))

    await _pipeline(model).draft(_request(), EXAMPLE_RELEASE)

    assert [source.source_id for source in model.requests[0].policy_sources] == ["S1"]


@pytest.mark.anyio
async def test_an_expired_version_is_never_sent_to_the_llm() -> None:
    model = FakeModel(
        matches=(
            DocumentMatch(EXPIRED_DELIVERY, 0.95, ("Old text.",)),
            DocumentMatch(DELIVERY, 0.9, (DELIVERY.body,)),
        )
    )

    await _pipeline(model).draft(_request(), EXAMPLE_RELEASE)

    assert [source.document_id for source in model.requests[0].policy_sources] == ["DELIVERY"]


@pytest.mark.anyio
async def test_a_ticket_without_an_order_sends_no_order_fact() -> None:
    model = FakeModel(
        reply=dataclasses.replace(
            GROUNDED, text="Parcels ship daily [S1].", cited_source_ids=("S1",)
        )
    )

    outcome = await _pipeline(model).draft(_request(order_facts=None), EXAMPLE_RELEASE)

    assert isinstance(outcome, DraftReady)
    assert model.requests[0].order_facts == ()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model", "attributes"),
    [
        (
            FakeModel(),
            {
                "recommendation": "draft",
                "reason_codes": "",
                "document_count": 1,
                "warning_count": 0,
                "analysis_ms": 300,
            },
        ),
        # An expired version is a document of the analysis too.
        (
            FakeModel(
                matches=(
                    DocumentMatch(EXPIRED_DELIVERY, 0.95, ("Old text.",)),
                    DocumentMatch(DELIVERY, 0.9, (DELIVERY.body,)),
                )
            ),
            {
                "recommendation": "draft",
                "reason_codes": "",
                "document_count": 2,
                "warning_count": 0,
                "analysis_ms": 300,
            },
        ),
        # Two codes, in the order of the contract, and the warning of a disagreement.
        (
            FakeModel(intents=distribution(("request_refund", 0.45), ("track_order", 0.4))),
            {
                "recommendation": "abstain",
                "reason_codes": "low_confidence,requires_authority",
                "document_count": 1,
                "warning_count": 1,
                "analysis_ms": 300,
            },
        ),
    ],
)
async def test_an_analysis_records_its_recommendation_its_counts_and_its_time(
    model: FakeModel, attributes: dict[str, EventAttributeValue]
) -> None:
    events = RecordingEventRecorder()

    await _pipeline(model, events).analyze(_request(), EXAMPLE_RELEASE)

    assert events.events == [RecordedEvent(EventName.ANALYSIS_COMPLETED, attributes)]


# The events that end a draft step; each step records exactly one (LOG-17, LOG-19).
OUTCOME_EVENTS = frozenset(
    {
        EventName.DRAFT_GENERATED,
        EventName.DRAFT_ABSTAINED,
        EventName.ESCALATION_RECOMMENDED,
        EventName.LLM_CALL_FAILED,
        EventName.GROUNDING_CHECK_FAILED,
    }
)
# The fake model: 0.3 s to analyze, 1.5 s for the LLM.
TOKENS: dict[str, EventAttributeValue] = {"input_token_count": 1_000, "output_token_count": 500}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model", "event", "attributes"),
    [
        (
            FakeModel(),
            EventName.DRAFT_GENERATED,
            {
                "reason_codes": "",
                "segment_count": 1,
                "citation_count": 2,
                **TOKENS,
                "cost_micro_usd": 2,
                "llm_ms": 1_500,
                "total_ms": 1_800,
            },
        ),
        (
            FakeModel(matches=()),
            EventName.DRAFT_ABSTAINED,
            {"reason_codes": "no_valid_document", "total_ms": 300},
        ),
        (
            FakeModel(intents=distribution(("human_agent", 0.95))),
            EventName.ESCALATION_RECOMMENDED,
            {"reason_codes": "human_agent_requested", "total_ms": 300},
        ),
        (
            FakeModel(reply=UnanswerableRequest(usage=USAGE)),
            EventName.DRAFT_ABSTAINED,
            {"reason_codes": "no_valid_document", "total_ms": 1_800, "llm_ms": 1_500},
        ),
        (
            FakeModel(reply=LlmCallError(LlmFailure.UNAVAILABLE)),
            EventName.LLM_CALL_FAILED,
            {"reason_code": "llm_unavailable", "llm_ms": 1_500},
        ),
        # Each code leads to one event: `llm_invalid_output` is an unusable output, whichever
        # check found it (contracts v1 design, Reason codes).
        (
            FakeModel(reply=LlmCallError(LlmFailure.INVALID_OUTPUT, USAGE)),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "llm_invalid_output", "llm_ms": 1_500, **TOKENS},
        ),
        (
            FakeModel(
                reply=dataclasses.replace(
                    GROUNDED,
                    text="Your order [ORDER_ID_9] ships daily [S1].",
                    cited_source_ids=("S1",),
                )
            ),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "llm_invalid_output", "llm_ms": 1_500, **TOKENS},
        ),
        (
            FakeModel(
                reply=dataclasses.replace(
                    GROUNDED, text="Your parcel is late [S2].", cited_source_ids=("S2",)
                )
            ),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "grounding_failed", "llm_ms": 1_500, **TOKENS},
        ),
        # Token counts beyond the caps of the contract are never logged either, and they make
        # the code `llm_invalid_output` on every path.
        (
            FakeModel(reply=dataclasses.replace(GROUNDED, usage=TokenUsage(1_000_001, 0))),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "llm_invalid_output", "llm_ms": 1_500},
        ),
        (
            FakeModel(reply=LlmCallError(LlmFailure.UNAVAILABLE, TokenUsage(0, 1_000_001))),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "llm_invalid_output", "llm_ms": 1_500},
        ),
        (
            FakeModel(reply=UnanswerableRequest(usage=TokenUsage(1_000_001, 0))),
            EventName.GROUNDING_CHECK_FAILED,
            {"reason_code": "llm_invalid_output", "llm_ms": 1_500},
        ),
    ],
)
async def test_each_draft_records_one_outcome_event_with_codes_counts_and_times(
    model: FakeModel, event: EventName, attributes: dict[str, EventAttributeValue]
) -> None:
    events = RecordingEventRecorder()

    await _pipeline(model, events).draft(_request(), EXAMPLE_RELEASE)

    recorded = [recorded for recorded in events.events if recorded.name in OUTCOME_EVENTS]
    assert recorded == [RecordedEvent(event, attributes)]
    assert events.of(EventName.ANALYSIS_COMPLETED)

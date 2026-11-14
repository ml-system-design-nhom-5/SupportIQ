"""In-memory fakes of the suggestions ports, built from the contract's examples (ARCH-27).

`EXAMPLE_ANALYSIS` is `contracts/examples/createAnalysis/draft.json`, `EXAMPLE_DRAFT_READY` is
`createDraft/draft-ready.json`, and `EXAMPLE_LLM_UNAVAILABLE` is `createDraft/llm-unavailable.json`.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.suggestions.domain import (
    Analysis,
    ConfidenceBand,
    DocumentValidity,
    Draft,
    DraftOutcome,
    DraftReady,
    DraftSegment,
    IntentCandidate,
    IntentName,
    KbDocumentCitation,
    LlmUsage,
    MaskCounts,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OrderContextCitation,
    OrderFieldName,
    OutcomeDetails,
    RankedDocument,
    ReasonCode,
    Routing,
    RoutingRecommendation,
    StepLatencies,
    SuggestionInput,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS

SAMPLE_START = datetime(2026, 1, 1, tzinfo=UTC)
SAMPLE_END = datetime(2027, 1, 1, tzinfo=UTC)
SAMPLE_REFUND_SNIPPET = "This is sample text. It is not KB content and not a policy."

EXAMPLE_ANALYSIS = Analysis(
    intent=ModelIntent(
        label=IntentName("refund_status"), probability=0.91, confidence_band=ConfidenceBand.HIGH
    ),
    alternatives=(
        IntentCandidate(label=IntentName("request_refund"), probability=0.05),
        IntentCandidate(label=IntentName("return_product"), probability=0.02),
    ),
    is_in_scope=True,
    documents=(
        RankedDocument(
            document_id="SAMPLE-REFUND-001",
            version="1.0",
            title="Sample refund document",
            policy_key="sample_refund_review",
            effective_start_at=SAMPLE_START,
            effective_end_at=None,
            validity=DocumentValidity.VALID,
            rank=1,
            snippet=SAMPLE_REFUND_SNIPPET,
        ),
        RankedDocument(
            document_id="SAMPLE-RETURN-001",
            version="2.0",
            title="Sample return document",
            policy_key="sample_return_window",
            effective_start_at=SAMPLE_START,
            effective_end_at=SAMPLE_END,
            validity=DocumentValidity.VALID,
            rank=2,
            snippet="This is another sample text. It is not KB content and not a policy.",
        ),
    ),
    routing=Routing(recommendation=RoutingRecommendation.DRAFT, reason_codes=()),
    warnings=(),
    versions=EXAMPLE_VERSIONS,
    step_latencies=StepLatencies(total_ms=176, analysis_ms=176),
)

EXAMPLE_DRAFT_READY = DraftReady(
    details=OutcomeDetails(
        reason_codes=(),
        analysis=EXAMPLE_ANALYSIS,
        versions=EXAMPLE_VERSIONS,
        step_latencies=StepLatencies(total_ms=3420, analysis_ms=176, llm_ms=3205),
        mask_counts=MaskCounts(email=0, phone=0, card=0),
        staff_note="Check each statement against its cited source before you send a reply.",
        llm_usage=LlmUsage(input_token_count=1180, output_token_count=96, cost_micro_usd=210),
    ),
    draft=Draft(
        segments=(
            DraftSegment(
                segment_id="s1",
                paragraph_index=0,
                text="Hello [NAME_1], thank you for your patience.",
                citation_ids=(),
            ),
            DraftSegment(
                segment_id="s2",
                paragraph_index=1,
                text="Your refund request for order [ORDER_ID_1] is under review.",
                citation_ids=("c2",),
            ),
            DraftSegment(
                segment_id="s3",
                paragraph_index=1,
                text=(
                    "This sample sentence stands for a policy statement from the cited document."
                ),
                citation_ids=("c1",),
            ),
        ),
        citations=(
            KbDocumentCitation(
                citation_id="c1",
                document_id="SAMPLE-REFUND-001",
                version="1.0",
                snippet=SAMPLE_REFUND_SNIPPET,
            ),
            OrderContextCitation(citation_id="c2", field=OrderFieldName("refund_status")),
        ),
    ),
)

EXAMPLE_LLM_UNAVAILABLE = NoDraft(
    details=OutcomeDetails(
        reason_codes=(ReasonCode("llm_unavailable"),),
        analysis=EXAMPLE_ANALYSIS,
        versions=EXAMPLE_VERSIONS,
        step_latencies=StepLatencies(total_ms=10190, analysis_ms=176, llm_ms=10000),
        mask_counts=MaskCounts(email=1, phone=0, card=0),
        staff_note=(
            "Draft generation is unavailable. "
            "Review the retrieved sources and write a reply manually."
        ),
    ),
    status=NoDraftStatus.LLM_UNAVAILABLE,
)


@dataclass(slots=True)
class FakePipeline:
    """A pipeline that answers fixed results and keeps every request it received."""

    analysis: Analysis = EXAMPLE_ANALYSIS
    outcome: DraftOutcome = EXAMPLE_DRAFT_READY
    requests: list[tuple[SuggestionInput, LoadedRelease]] = field(
        default_factory=list[tuple[SuggestionInput, LoadedRelease]]
    )

    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        """Keep the request and return the fixed analysis.

        Args:
            request: The validated request.
            release: The loaded release.
        """
        self.requests.append((request, release))
        return self.analysis

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        """Keep the request and return the fixed outcome.

        Args:
            request: The validated request.
            release: The loaded release.
        """
        self.requests.append((request, release))
        return self.outcome


class FailingPipeline:
    """A pipeline that fails unexpectedly, as a defect would."""

    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        """Raise the failure.

        Args:
            request: The validated request.
            release: The loaded release.

        Raises:
            RuntimeError: Always.
        """
        del request, release
        message = "pipeline failed"
        raise RuntimeError(message)

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        """Raise the failure.

        Args:
            request: The validated request.
            release: The loaded release.

        Raises:
            RuntimeError: Always.
        """
        del request, release
        message = "pipeline failed"
        raise RuntimeError(message)

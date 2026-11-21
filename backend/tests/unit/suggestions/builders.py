"""Builders of AI results and suggestions with sensible defaults (TEST-05)."""

from dataclasses import replace
from datetime import UTC, datetime

from app.accounts import AccountId
from app.platform import TraceId
from app.suggestions import (
    AiReasonCode,
    AiWarning,
    Analysis,
    AnalysisState,
    AssetVersions,
    ConfidenceBand,
    Draft,
    DraftOutcomeDetails,
    DraftReady,
    DraftSegment,
    DraftState,
    IntentLabel,
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionTag,
    MaskCounts,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    PendingPart,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    Routing,
    RoutingRecommendation,
    StepLatencies,
    Suggestion,
    SuggestionId,
    SuggestionTicketId,
    SuggestionTrigger,
    UnavailablePart,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

TICKET_ID = SuggestionTicketId("TCK-1042")
SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000001")
TRACE_ID = TraceId("4bf92f3577b34da6a3ce929d0e0e4736")
STAFF_ACCOUNT_ID = AccountId("00000000-0000-4000-8000-0000000000aa")
KB_VERSION = "kb-sample-1"
OTHER_KB_VERSION = "kb-sample-2"
PREDICTED_INTENT = IntentLabel.REFUND_STATUS
ANALYSIS_BODY = '{"analysis": "as received"}'
DRAFT_BODY = '{"draft": "as received"}'
DOCUMENT_ID = KbDocumentId("SAMPLE-REFUND-001")
DOCUMENT_VERSION = KbDocumentVersionTag("1.0")


def build_versions(kb_version: str = KB_VERSION) -> AssetVersions:
    """Build the versions of a sample release."""
    return AssetVersions(
        release_id="release-sample",
        model_version="intent-model-sample-1",
        kb_version=kb_version,
        mapping_version="mapping-sample-1",
        prompt_version="prompts-sample-1",
        routing_version="routing-sample-1",
        index_version="index-sample-1",
    )


def build_kb_document_version() -> KbDocumentVersion:
    """Build an open-ended sample document version; it is not KB content (TEST-18)."""
    return KbDocumentVersion(
        document_id=DOCUMENT_ID,
        version=DOCUMENT_VERSION,
        title="Sample refund document",
        body="This is sample text. It is not KB content and not a policy.",
        policy_key="sample_refund_review",
        effective_start_at=datetime(2026, 1, 1, tzinfo=UTC),
        effective_end_at=None,
        owner="Policy owner",
        source="Sample source document",
        last_reviewed_at=None,
    )


def build_analysis(
    *,
    reason_codes: tuple[AiReasonCode, ...] = (),
    warning_ids: tuple[str, ...] = (),
    kb_version: str = KB_VERSION,
) -> Analysis:
    """Build an analysis of the model that recommends a draft."""
    return Analysis(
        intent=ModelIntent(PREDICTED_INTENT, 0.88, ConfidenceBand.HIGH),
        alternatives=(),
        is_in_scope=True,
        documents=(),
        routing=Routing(RoutingRecommendation.DRAFT, reason_codes),
        warnings=tuple(
            AiWarning(warning_id, AiReasonCode.SOURCE_REVIEW_OVERDUE) for warning_id in warning_ids
        ),
        versions=build_versions(kb_version),
        step_latencies=StepLatencies(total_ms=180, analysis_ms=179, llm_ms=None),
    )


def build_details(
    analysis: Analysis | None = None,
    *,
    reason_codes: tuple[AiReasonCode, ...] = (),
    staff_note: str | None = None,
) -> DraftOutcomeDetails:
    """Build the fields of every draft outcome."""
    embedded = analysis or build_analysis(reason_codes=reason_codes)
    return DraftOutcomeDetails(
        reason_codes=reason_codes,
        analysis=embedded,
        staff_note=staff_note,
        versions=embedded.versions,
        step_latencies=StepLatencies(total_ms=4_200, analysis_ms=180, llm_ms=3_900),
        mask_counts=MaskCounts(0, 0, 0),
        llm_usage=None,
    )


def build_draft_ready(
    *segments: tuple[int, str],
    reason_codes: tuple[AiReasonCode, ...] = (),
    warning_ids: tuple[str, ...] = (),
) -> DraftReady:
    """Build a ready draft from (paragraph index, text) segments."""
    texts = segments or ((0, "Hello [NAME_1], your refund is under review."),)
    analysis = build_analysis(reason_codes=reason_codes, warning_ids=warning_ids)
    return DraftReady(
        build_details(analysis, reason_codes=reason_codes),
        Draft(
            tuple(
                DraftSegment(f"s{index}", paragraph_index, text, ())
                for index, (paragraph_index, text) in enumerate(texts, start=1)
            ),
            (),
        ),
    )


def build_no_draft(
    status: NoDraftStatus, *, reason_codes: tuple[AiReasonCode, ...] = ()
) -> NoDraft:
    """Build a draft outcome without a draft."""
    return NoDraft(status, build_details(reason_codes=reason_codes))


def build_suggestion(
    *,
    analysis: AnalysisState | None = None,
    draft: DraftState | None = None,
    intent_override: IntentLabel | None = None,
    suggestion_id: SuggestionId = SUGGESTION_ID,
) -> Suggestion:
    """Build a suggestion of `TICKET_ID`; both parts are pending by default."""
    return Suggestion(
        suggestion_id=suggestion_id,
        ticket_id=TICKET_ID,
        trigger=(
            SuggestionTrigger.TICKET_CREATED
            if intent_override is None
            else SuggestionTrigger.INTENT_OVERRIDE
        ),
        intent_override=intent_override,
        requested_by=None if intent_override is None else STAFF_ACCOUNT_ID,
        created_at=FAKE_CLOCK_START,
        trace_id=TRACE_ID,
        analysis=analysis or PendingPart(),
        draft=draft or PendingPart(),
        sent_order_context=None,
    )


def build_ready_suggestion(draft: DraftState | None = None) -> Suggestion:
    """Build a suggestion whose analysis is ready and whose draft is ready by default."""
    return build_suggestion(analysis=build_analysis(), draft=draft or build_draft_ready())


def build_failed_suggestion(reason_code: AiReasonCode) -> Suggestion:
    """Build a suggestion whose two parts ended unavailable."""
    return build_suggestion(
        analysis=UnavailablePart(reason_code), draft=UnavailablePart(reason_code)
    )


def received_analysis(analysis: Analysis | None = None) -> ReceivedAnalysis:
    """Wrap an analysis as received from ai-service."""
    return ReceivedAnalysis(analysis or build_analysis(), ANALYSIS_BODY)


def received_draft(outcome: DraftReady | NoDraft | None = None) -> ReceivedDraftOutcome:
    """Wrap a draft outcome as received from ai-service."""
    return ReceivedDraftOutcome(outcome or build_draft_ready(), DRAFT_BODY, ANALYSIS_BODY)


def with_override(suggestion: Suggestion, intent: IntentLabel) -> Suggestion:
    """Return a copy of a suggestion that carries an intent override."""
    return replace(suggestion, intent_override=intent, trigger=SuggestionTrigger.INTENT_OVERRIDE)

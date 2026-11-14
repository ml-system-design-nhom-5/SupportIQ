"""Map a suggestion and its two parts to the contract (`SuggestionView`).

Pseudonyms are already restored in the texts that reach this module (ADR-0010). Only a part
with a result needs the mappings of other features: its asset versions and the citations of
a ready draft. A new suggestion, whose parts are both pending, maps without them.
"""

from typing import assert_never

from pydantic import MISSING

from supportiq_backend.generated import (
    AiItemId,
    AnalysisPart,
    ConsoleDraftSegment,
    ConsoleIntent,
    ConsoleIntentAlternative,
    ConsoleModelIntent,
    ConsoleRouting,
    ConsoleStaffIntent,
    DraftPart,
    KbDocumentId,
    KbDocumentVersionTag,
    NoDraftPart,
    PendingAnalysisPart,
    PendingDraftPart,
    ReadyAnalysisPart,
    ReadyDraftPart,
    SuggestionView,
    UnavailableAnalysisPart,
    UnavailableDraftPart,
)
from supportiq_backend.generated import AiReasonCode as ContractAiReasonCode
from supportiq_backend.generated import ConfidenceBand as ContractConfidenceBand
from supportiq_backend.generated import DocumentValidity as ContractDocumentValidity
from supportiq_backend.generated import IntentLabel as ContractIntentLabel
from supportiq_backend.generated import RankedDocument as ContractRankedDocument
from supportiq_backend.generated import RoutingRecommendation as ContractRoutingRecommendation
from supportiq_backend.generated import StepLatencies as ContractStepLatencies
from supportiq_backend.generated import SuggestionTrigger as ContractSuggestionTrigger
from supportiq_backend.generated import Warning as ContractWarning
from supportiq_backend.platform import UnexpectedFailureError
from supportiq_backend.platform.web import format_optional_timestamp, format_timestamp
from supportiq_backend.suggestions import (
    AiReasonCode,
    Analysis,
    AnalysisIntent,
    AnalysisState,
    CancelledPart,
    DraftReady,
    DraftState,
    ModelIntent,
    NoDraft,
    PendingPart,
    RankedDocument,
    StaffIntent,
    StepLatencies,
    Suggestion,
    UnavailablePart,
)
from supportiq_backend.tickets.api.console_citation_views import to_citation_view
from supportiq_backend.tickets.api.console_view_mappers import ConsoleViewMappers
from supportiq_backend.tickets.domain import RestoredSuggestion

type _AnalysisView = PendingAnalysisPart | ReadyAnalysisPart | UnavailableAnalysisPart
type _DraftView = PendingDraftPart | ReadyDraftPart | NoDraftPart | UnavailableDraftPart


def to_suggestion_view(restored: RestoredSuggestion, views: ConsoleViewMappers) -> SuggestionView:
    """Map a suggestion with its restored texts to the contract.

    Args:
        restored: The suggestion and its restored texts.
        views: The mappings of other features, for the asset versions and the amounts of
            order citations.

    Returns:
        The contract model.

    Raises:
        UnexpectedFailureError: A part is cancelled, or a ready draft lacks its text or a
            cited order fact: a defect.
    """
    suggestion = restored.suggestion
    return _build_suggestion_view(
        suggestion,
        _to_analysis_part(suggestion.analysis, views),
        _to_draft_part(restored, views),
    )


def to_pending_suggestion_view(suggestion: Suggestion) -> SuggestionView:
    """Map a new suggestion, whose two parts wait for their results, as `createSuggestion` answers.

    Args:
        suggestion: The new suggestion.

    Returns:
        The contract model, with both parts `pending`.

    Raises:
        UnexpectedFailureError: A part has a result already: a defect, because the starter
            inserts both parts pending.
    """
    is_new = isinstance(suggestion.analysis, PendingPart) and isinstance(
        suggestion.draft, PendingPart
    )
    if not is_new:
        raise UnexpectedFailureError
    return _build_suggestion_view(
        suggestion,
        PendingAnalysisPart(analysis_status="pending"),
        PendingDraftPart(draft_status="pending"),
    )


def _build_suggestion_view(
    suggestion: Suggestion, analysis: _AnalysisView, draft: _DraftView
) -> SuggestionView:
    return SuggestionView(
        suggestion_id=suggestion.suggestion_id,
        trigger=ContractSuggestionTrigger(suggestion.trigger.value),
        intent_override=(
            MISSING
            if suggestion.intent_override is None
            else ContractIntentLabel(suggestion.intent_override.value)
        ),
        created_at=format_timestamp(suggestion.created_at),
        trace_id=suggestion.trace_id,
        analysis=AnalysisPart(analysis),
        draft=DraftPart(draft),
    )


def _to_analysis_part(state: AnalysisState, views: ConsoleViewMappers) -> _AnalysisView:
    match state:
        case PendingPart():
            return PendingAnalysisPart(analysis_status="pending")
        case UnavailablePart():
            return UnavailableAnalysisPart(
                analysis_status="unavailable",
                reason_codes=[ContractAiReasonCode(state.reason_code.value)],
            )
        case Analysis():
            return _to_ready_analysis(state, views)
        case CancelledPart():
            # Only a superseded suggestion has cancelled parts, and the workspace shows the
            # current one only.
            raise UnexpectedFailureError
        case _:
            assert_never(state)


def _to_ready_analysis(analysis: Analysis, views: ConsoleViewMappers) -> ReadyAnalysisPart:
    return ReadyAnalysisPart(
        analysis_status="ready",
        intent=ConsoleIntent(_to_intent(analysis.intent)),
        alternatives=[
            ConsoleIntentAlternative(
                label=ContractIntentLabel(item.label.value), probability=item.probability
            )
            for item in analysis.alternatives
        ],
        is_in_scope=analysis.is_in_scope,
        documents=[_to_document(document) for document in analysis.documents],
        routing=ConsoleRouting(
            recommendation=ContractRoutingRecommendation(analysis.routing.recommendation.value),
            reason_codes=_to_reason_codes(analysis.routing.reason_codes),
        ),
        warnings=[
            ContractWarning(
                warning_id=AiItemId(item.warning_id),
                reason_code=ContractAiReasonCode(item.reason_code.value),
            )
            for item in analysis.warnings
        ],
        versions=views.to_asset_versions_view(analysis.versions),
        step_latencies=_to_latencies(analysis.step_latencies),
    )


def _to_intent(intent: AnalysisIntent) -> ConsoleModelIntent | ConsoleStaffIntent:
    match intent:
        case ModelIntent():
            return ConsoleModelIntent(
                source="model",
                label=ContractIntentLabel(intent.label.value),
                probability=intent.probability,
                confidence_band=ContractConfidenceBand(intent.confidence_band.value),
            )
        case StaffIntent():
            return ConsoleStaffIntent(source="staff", label=ContractIntentLabel(intent.label.value))
        case _:
            assert_never(intent)


def _to_draft_part(restored: RestoredSuggestion, views: ConsoleViewMappers) -> _DraftView:
    state: DraftState = restored.suggestion.draft
    match state:
        case PendingPart():
            return PendingDraftPart(draft_status="pending")
        case UnavailablePart():
            return UnavailableDraftPart(
                draft_status="unavailable",
                reason_codes=[ContractAiReasonCode(state.reason_code.value)],
            )
        case DraftReady():
            return _to_ready_draft(restored, state, views)
        case NoDraft():
            return NoDraftPart(
                draft_status=state.status.value,
                reason_codes=_to_reason_codes(state.details.reason_codes),
                staff_note=MISSING if restored.staff_note is None else restored.staff_note,
                versions=views.to_asset_versions_view(state.details.versions),
                step_latencies=_to_latencies(state.details.step_latencies),
            )
        case CancelledPart():
            raise UnexpectedFailureError
        case _:
            assert_never(state)


def _to_ready_draft(
    restored: RestoredSuggestion, draft: DraftReady, views: ConsoleViewMappers
) -> ReadyDraftPart:
    sent_context = restored.suggestion.sent_order_context
    if restored.draft_text is None:
        raise UnexpectedFailureError
    return ReadyDraftPart(
        draft_status="draft_ready",
        segments=[
            ConsoleDraftSegment(
                segment_id=AiItemId(segment.segment_id),
                paragraph_index=segment.paragraph_index,
                text=text,
                citation_ids=[AiItemId(citation_id) for citation_id in segment.citation_ids],
            )
            for segment, text in zip(draft.draft.segments, restored.segment_texts, strict=True)
        ],
        citations=[
            to_citation_view(citation, sent_context, views.orders)
            for citation in draft.draft.citations
        ],
        text=restored.draft_text,
        reason_codes=_to_reason_codes(draft.details.reason_codes),
        staff_note=MISSING if restored.staff_note is None else restored.staff_note,
        versions=views.to_asset_versions_view(draft.details.versions),
        step_latencies=_to_latencies(draft.details.step_latencies),
    )


def _to_document(document: RankedDocument) -> ContractRankedDocument:
    return ContractRankedDocument(
        document_id=KbDocumentId(document.document_id),
        version=KbDocumentVersionTag(document.version),
        title=document.title,
        policy_key=document.policy_key,
        effective_start_at=format_timestamp(document.effective_start_at),
        effective_end_at=format_optional_timestamp(document.effective_end_at),
        validity=ContractDocumentValidity(document.validity.value),
        rank=document.rank,
        snippet=document.snippet,
    )


def _to_latencies(latencies: StepLatencies) -> ContractStepLatencies:
    return ContractStepLatencies(
        total_ms=latencies.total_ms,
        analysis_ms=latencies.analysis_ms,
        llm_ms=MISSING if latencies.llm_ms is None else latencies.llm_ms,
    )


def _to_reason_codes(codes: tuple[AiReasonCode, ...]) -> list[ContractAiReasonCode]:
    return [ContractAiReasonCode(code.value) for code in codes]

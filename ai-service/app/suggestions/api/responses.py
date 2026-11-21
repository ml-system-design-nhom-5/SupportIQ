"""The mapping from the domain results to the contract's `Analysis` and `DraftOutcome`.

An optional field that the domain leaves as None stays absent, never `null` (CON-08), and no
field outside the contract is sent (CON-21). A value that the contract does not allow, such
as an unknown intent label, fails here as a defect and becomes `500 internal-error`.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import MISSING

from app import generated as contract
from app.platform.web import format_timestamp
from app.release.api import asset_versions_body
from app.suggestions.domain import (
    Analysis,
    AnalysisWarning,
    Citation,
    Draft,
    DraftOutcome,
    DraftReady,
    IntentCandidate,
    KbDocumentCitation,
    LlmUsage,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OutcomeDetails,
    RankedDocument,
    ReasonCode,
    StaffIntent,
    StepLatencies,
)

type NoDraftStatusValue = Literal["abstained", "escalation_recommended", "llm_unavailable"]

_NO_DRAFT_STATUS_VALUES: Mapping[NoDraftStatus, NoDraftStatusValue] = MappingProxyType(
    {
        NoDraftStatus.ABSTAINED: "abstained",
        NoDraftStatus.ESCALATION_RECOMMENDED: "escalation_recommended",
        NoDraftStatus.LLM_UNAVAILABLE: "llm_unavailable",
    }
)


def analysis_body(analysis: Analysis) -> contract.Analysis:
    """Map an analysis to the contract's `Analysis`.

    Args:
        analysis: The analysis.

    Returns:
        The body of `createAnalysis`, also embedded in every draft outcome.
    """
    return contract.Analysis(
        intent=contract.AnalysisIntent(_intent_body(analysis.intent)),
        alternatives=[_alternative_body(candidate) for candidate in analysis.alternatives],
        is_in_scope=analysis.is_in_scope,
        documents=[_document_body(document) for document in analysis.documents],
        routing=contract.Routing(
            recommendation=contract.RoutingRecommendation(analysis.routing.recommendation.value),
            reason_codes=_reason_codes_body(analysis.routing.reason_codes),
        ),
        warnings=[_warning_body(warning) for warning in analysis.warnings],
        versions=asset_versions_body(analysis.versions),
        step_latencies=_latencies_body(analysis.step_latencies),
    )


def draft_outcome_body(outcome: DraftOutcome) -> contract.DraftOutcome:
    """Map a draft outcome to the contract's `DraftOutcome`.

    Args:
        outcome: The draft outcome.

    Returns:
        The body of `createDraft`. Only `draft_ready` carries a draft.
    """
    details = outcome.details
    match outcome:
        case DraftReady():
            return contract.DraftOutcome(
                contract.DraftReadyOutcome(
                    status="draft_ready",
                    draft=_draft_body(outcome.draft),
                    reason_codes=_reason_codes_body(details.reason_codes),
                    analysis=analysis_body(details.analysis),
                    staff_note=_staff_note_body(details),
                    versions=asset_versions_body(details.versions),
                    step_latencies=_latencies_body(details.step_latencies),
                    mask_count_by_type=_mask_counts_body(details),
                    llm_usage=_llm_usage_body(details.llm_usage),
                )
            )
        case NoDraft():
            return contract.DraftOutcome(
                contract.NoDraftOutcome(
                    status=_NO_DRAFT_STATUS_VALUES[outcome.status],
                    reason_codes=_reason_codes_body(details.reason_codes),
                    analysis=analysis_body(details.analysis),
                    staff_note=_staff_note_body(details),
                    versions=asset_versions_body(details.versions),
                    step_latencies=_latencies_body(details.step_latencies),
                    mask_count_by_type=_mask_counts_body(details),
                    llm_usage=_llm_usage_body(details.llm_usage),
                )
            )


def _intent_body(intent: ModelIntent | StaffIntent) -> contract.ModelIntent | contract.StaffIntent:
    match intent:
        case ModelIntent():
            return contract.ModelIntent(
                source="model",
                label=contract.IntentLabel(intent.label),
                probability=intent.probability,
                confidence_band=contract.ConfidenceBand(intent.confidence_band.value),
            )
        case StaffIntent():
            return contract.StaffIntent(source="staff", label=contract.IntentLabel(intent.label))


def _alternative_body(candidate: IntentCandidate) -> contract.IntentAlternative:
    return contract.IntentAlternative(
        label=contract.IntentLabel(candidate.label), probability=candidate.probability
    )


def _document_body(document: RankedDocument) -> contract.RankedDocument:
    end = document.effective_end_at
    return contract.RankedDocument(
        document_id=contract.KbDocumentId(document.document_id),
        version=contract.KbDocumentVersionTag(document.version),
        title=document.title,
        policy_key=document.policy_key,
        effective_start_at=format_timestamp(document.effective_start_at),
        effective_end_at=MISSING if end is None else format_timestamp(end),
        validity=contract.DocumentValidity(document.validity.value),
        rank=document.rank,
        snippet=document.snippet,
    )


def _reason_codes_body(codes: tuple[ReasonCode, ...]) -> list[contract.AiServiceReasonCode]:
    return [contract.AiServiceReasonCode(code) for code in codes]


def _warning_body(warning: AnalysisWarning) -> contract.Warning:
    return contract.Warning(
        warning_id=contract.AiItemId(warning.warning_id),
        reason_code=contract.AiReasonCode(warning.reason_code),
    )


def _latencies_body(latencies: StepLatencies) -> contract.StepLatencies:
    llm_ms = latencies.llm_ms
    return contract.StepLatencies(
        total_ms=latencies.total_ms,
        analysis_ms=latencies.analysis_ms,
        llm_ms=MISSING if llm_ms is None else llm_ms,
    )


def _draft_body(draft: Draft) -> contract.Draft:
    return contract.Draft(
        segments=[
            contract.DraftSegment(
                segment_id=contract.AiItemId(segment.segment_id),
                paragraph_index=segment.paragraph_index,
                text=segment.text,
                citation_ids=[contract.AiItemId(citation) for citation in segment.citation_ids],
            )
            for segment in draft.segments
        ],
        citations=[_citation_body(citation) for citation in draft.citations],
    )


def _citation_body(citation: Citation) -> contract.Citation:
    if isinstance(citation, KbDocumentCitation):
        return contract.Citation(
            contract.KbDocumentCitation(
                source_type="kb_document",
                citation_id=contract.AiItemId(citation.citation_id),
                document_id=contract.KbDocumentId(citation.document_id),
                version=contract.KbDocumentVersionTag(citation.version),
                snippet=citation.snippet,
            )
        )
    return contract.Citation(
        contract.OrderContextCitation(
            source_type="order_context",
            citation_id=contract.AiItemId(citation.citation_id),
            field=contract.OrderContextField(citation.field),
        )
    )


def _staff_note_body(details: OutcomeDetails) -> str | MISSING:
    return MISSING if details.staff_note is None else details.staff_note


def _mask_counts_body(details: OutcomeDetails) -> contract.MaskCountByType:
    counts = details.mask_counts
    return contract.MaskCountByType(email=counts.email, phone=counts.phone, card=counts.card)


def _llm_usage_body(usage: LlmUsage | None) -> contract.LlmUsage | MISSING:
    if usage is None:
        return MISSING
    return contract.LlmUsage(
        input_token_count=usage.input_token_count,
        output_token_count=usage.output_token_count,
        cost_micro_usd=usage.cost_micro_usd,
    )

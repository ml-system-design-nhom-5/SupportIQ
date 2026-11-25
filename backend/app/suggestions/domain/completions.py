"""What storing one part writes, and the audit data of `suggestion.part_completed`.

The audit data holds identifiers, statuses, reason codes, versions, and numbers only, never
AI text (SEC-39, contracts v1 design, Audit log).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from app.suggestions.domain.ai_results import (
    Analysis,
    AssetVersions,
    DraftReady,
    LlmUsage,
    MaskCounts,
    NoDraft,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
)
from app.suggestions.domain.labels import AiReasonCode
from app.suggestions.domain.suggestions import (
    PartStatus,
    SuggestionId,
    SuggestionPart,
)

# Reason codes join into one audit value, because audit values are scalars (SEC-39).
REASON_CODE_SEPARATOR = ","

type AuditDataValue = str | int | bool


@dataclass(frozen=True, slots=True, repr=False)
class PartCompletion:
    """The final state of one part, written once (backend ticket workflow design, Tables).

    Attributes:
        part: The part.
        status: Its final status.
        reason_codes: Its reason codes.
        versions: The versions that produced it; absent without a result.
        latency_ms: The time of the call; absent without a result.
        llm_usage: The LLM usage of a draft call, when the LLM answered.
        mask_counts: The masks of a draft call.
        result_body: The response of ai-service as received; absent without a result.
            Confidential.
        completed_at: When the part left `pending`.
    """

    part: SuggestionPart
    status: PartStatus
    reason_codes: tuple[AiReasonCode, ...]
    versions: AssetVersions | None
    latency_ms: int | None
    llm_usage: LlmUsage | None
    mask_counts: MaskCounts | None
    result_body: str | None
    completed_at: datetime

    @property
    def is_authority_required(self) -> bool:
        """Tell whether this result sets the ticket's authority flag (FR-06)."""
        return AiReasonCode.REQUIRES_AUTHORITY in self.reason_codes


def build_analysis_completion(received: ReceivedAnalysis, completed_at: datetime) -> PartCompletion:
    """Describe a ready analysis from a `createAnalysis` response.

    Args:
        received: The analysis and its response body.
        completed_at: When it arrived.

    Returns:
        The completion of the analysis part.
    """
    return _ready_analysis(received.analysis, received.body, completed_at)


def build_embedded_analysis_completion(
    received: ReceivedDraftOutcome, completed_at: datetime
) -> PartCompletion:
    """Describe the analysis part from the analysis that a draft outcome embeds.

    Args:
        received: The draft outcome and its response bodies.
        completed_at: When it arrived.

    Returns:
        The completion of the analysis part.
    """
    return _ready_analysis(received.outcome.details.analysis, received.analysis_body, completed_at)


def build_draft_completion(
    received: ReceivedDraftOutcome, completed_at: datetime
) -> PartCompletion:
    """Describe the draft part from a `createDraft` response.

    Args:
        received: The draft outcome and its response body.
        completed_at: When it arrived.

    Returns:
        The completion of the draft part.
    """
    outcome = received.outcome
    match outcome:
        case DraftReady():
            status = PartStatus.DRAFT_READY
        case NoDraft():
            status = PartStatus(outcome.status.value)
        case _:
            assert_never(outcome)
    details = outcome.details
    return PartCompletion(
        part=SuggestionPart.DRAFT,
        status=status,
        reason_codes=details.reason_codes,
        versions=details.versions,
        latency_ms=details.step_latencies.total_ms,
        llm_usage=details.llm_usage,
        mask_counts=details.mask_counts,
        result_body=received.body,
        completed_at=completed_at,
    )


def build_unavailable_completion(
    part: SuggestionPart, reason_code: AiReasonCode, completed_at: datetime
) -> PartCompletion:
    """Describe a part that backend could not get from ai-service.

    Args:
        part: The part.
        reason_code: `ai_service_unavailable` or `pseudonymization_failed`.
        completed_at: When backend gave up.

    Returns:
        The completion, without a result.
    """
    return PartCompletion(
        part=part,
        status=PartStatus.UNAVAILABLE,
        reason_codes=(reason_code,),
        versions=None,
        latency_ms=None,
        llm_usage=None,
        mask_counts=None,
        result_body=None,
        completed_at=completed_at,
    )


def build_part_audit_data(
    suggestion_id: SuggestionId, completion: PartCompletion
) -> Mapping[str, AuditDataValue]:
    """Build the data of `suggestion.part_completed`.

    Args:
        suggestion_id: The suggestion.
        completion: The completion of the part.

    Returns:
        The data: suggestion ID, part, status, reason codes, versions, latency, LLM usage, and
        masks by type, each when present.
    """
    data: dict[str, AuditDataValue] = {
        "suggestion_id": suggestion_id,
        "part": completion.part.value,
        "status": completion.status.value,
        "reason_codes": REASON_CODE_SEPARATOR.join(code.value for code in completion.reason_codes),
    }
    if completion.versions is not None:
        data.update(_versions_data(completion.versions))
    if completion.latency_ms is not None:
        data["latency_ms"] = completion.latency_ms
    if completion.llm_usage is not None:
        data["llm_input_token_count"] = completion.llm_usage.input_token_count
        data["llm_output_token_count"] = completion.llm_usage.output_token_count
        data["llm_cost_micro_usd"] = completion.llm_usage.cost_micro_usd
    if completion.mask_counts is not None:
        data["email_mask_count"] = completion.mask_counts.email
        data["phone_mask_count"] = completion.mask_counts.phone
        data["card_mask_count"] = completion.mask_counts.card
    return data


def _ready_analysis(analysis: Analysis, body: str, completed_at: datetime) -> PartCompletion:
    return PartCompletion(
        part=SuggestionPart.ANALYSIS,
        status=PartStatus.READY,
        reason_codes=analysis.routing.reason_codes,
        versions=analysis.versions,
        latency_ms=analysis.step_latencies.total_ms,
        llm_usage=None,
        mask_counts=None,
        result_body=body,
        completed_at=completed_at,
    )


def _versions_data(versions: AssetVersions) -> Mapping[str, AuditDataValue]:
    return {
        "release_id": versions.release_id,
        "model_version": versions.model_version,
        "kb_version": versions.kb_version,
        "mapping_version": versions.mapping_version,
        "prompt_version": versions.prompt_version,
        "routing_version": versions.routing_version,
        "index_version": versions.index_version,
    }

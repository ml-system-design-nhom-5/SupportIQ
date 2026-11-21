"""The draft outcome: the result of the whole pipeline (ADR-0005).

These types hold the shape of the contract's `DraftOutcome`: a draft exists only when it is
ready (CODE-29). How each value is computed belongs to the pipeline, not to these types. A
draft is a suggestion for staff and is never sent to a customer without a staff action
(FR-04).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from app.release import AssetVersions
from app.suggestions.domain.analysis import Analysis, ReasonCode, StepLatencies

# One field name of the contract's `OrderContextField`. Internal.
OrderFieldName = NewType("OrderFieldName", str)


class NoDraftStatus(StrEnum):
    """Why an outcome carries no draft."""

    ABSTAINED = "abstained"
    ESCALATION_RECOMMENDED = "escalation_recommended"
    LLM_UNAVAILABLE = "llm_unavailable"


@dataclass(frozen=True, slots=True)
class DraftSegment:
    """One segment of a draft.

    Attributes:
        segment_id: The identifier of the segment.
        paragraph_index: The paragraph of the segment, from 0, never decreasing.
        text: The text, with only the placeholders of the prompt (ADR-0010).
        citation_ids: The citations that support the segment.
    """

    segment_id: str
    paragraph_index: int
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KbDocumentCitation:
    """A citation of one KB document version.

    Attributes:
        citation_id: The identifier of the citation.
        document_id: The document.
        version: The version of the document.
        snippet: The supporting snippet.
    """

    citation_id: str
    document_id: str
    version: str
    snippet: str


@dataclass(frozen=True, slots=True)
class OrderContextCitation:
    """A citation of one field of the order context, never of its value (ADR-0014).

    Attributes:
        citation_id: The identifier of the citation.
        field: The field of the order context.
    """

    citation_id: str
    field: OrderFieldName


type Citation = KbDocumentCitation | OrderContextCitation


@dataclass(frozen=True, slots=True)
class Draft:
    """A draft reply with its citations.

    Attributes:
        segments: The segments, in order.
        citations: The citations that the segments name.
    """

    segments: tuple[DraftSegment, ...]
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class MaskCounts:
    """The masks that ai-service applied before the LLM call, by type (SEC-06).

    Attributes:
        email: The number of `[EMAIL]` masks.
        phone: The number of `[PHONE]` masks.
        card: The number of `[CARD]` masks.
    """

    email: int
    phone: int
    card: int


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """What the LLM calls of one draft used.

    Attributes:
        input_token_count: The input tokens.
        output_token_count: The output tokens.
        cost_micro_usd: The cost, in millionths of a US dollar.
    """

    input_token_count: int
    output_token_count: int
    cost_micro_usd: int


@dataclass(frozen=True, slots=True)
class OutcomeDetails:
    """What every draft outcome carries, with or without a draft.

    Attributes:
        reason_codes: The reason codes of the routing and of the drafting step.
        analysis: The embedded analysis.
        versions: The release and asset versions that produced the outcome.
        step_latencies: How long the whole call took.
        mask_counts: The masks applied before the LLM call.
        staff_note: A note for staff only; None when there is none.
        llm_usage: What the LLM used; None when it never answered.
    """

    reason_codes: tuple[ReasonCode, ...]
    analysis: Analysis
    versions: AssetVersions
    step_latencies: StepLatencies
    mask_counts: MaskCounts
    staff_note: str | None = None
    llm_usage: LlmUsage | None = None


@dataclass(frozen=True, slots=True)
class DraftReady:
    """An outcome with a draft.

    Attributes:
        details: What every outcome carries.
        draft: The draft.
    """

    details: OutcomeDetails
    draft: Draft


@dataclass(frozen=True, slots=True)
class NoDraft:
    """An outcome without a draft.

    Attributes:
        details: What every outcome carries.
        status: Why there is no draft.
    """

    details: OutcomeDetails
    status: NoDraftStatus


type DraftOutcome = DraftReady | NoDraft

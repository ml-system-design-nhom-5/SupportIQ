"""What backend sends to ai-service and what it receives, as domain values (ARCH-15).

The `ai-service` contract 1.0.0 defines every field. Text fields of a draft and the staff note
are Confidential AI text with placeholders, so the classes that hold them have no generated
`repr` (LOG-29).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from supportiq_backend.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from supportiq_backend.suggestions.domain.kb_documents import KbDocumentId, KbDocumentVersionTag
from supportiq_backend.suggestions.domain.labels import (
    AiReasonCode,
    ConfidenceBand,
    DocumentValidity,
    IntentLabel,
    OrderContextField,
    RoutingRecommendation,
)


class NoDraftStatus(StrEnum):
    """The statuses of a draft outcome without a draft."""

    ABSTAINED = "abstained"
    ESCALATION_RECOMMENDED = "escalation_recommended"
    LLM_UNAVAILABLE = "llm_unavailable"


@dataclass(frozen=True, slots=True, repr=False)
class OrderContext:
    """The allow-listed facts of a ticket's order, without identifiers or an address.

    Every field is optional: absence means not applicable or unknown. Confidential.

    Attributes:
        order_status: The order status.
        placed_at: When it was placed.
        order_total: The total paid.
        shipping_cost: The shipping cost.
        shipment_status: The shipment status.
        estimated_delivery_at: The estimated delivery.
        delivered_at: When it was delivered.
        refund_status: The refund status.
        refund_amount: The refund amount.
        refund_requested_at: When the refund was requested.
    """

    order_status: OrderStatus | None = None
    placed_at: datetime | None = None
    order_total: Money | None = None
    shipping_cost: Money | None = None
    shipment_status: ShipmentStatus | None = None
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    refund_status: RefundStatus | None = None
    refund_amount: Money | None = None
    refund_requested_at: datetime | None = None


@dataclass(frozen=True, slots=True, repr=False)
class SuggestionRequest:
    """The body of `createAnalysis` and `createDraft`. Confidential.

    It carries no ticket ID and no identity (SEC-04), and `kb_version` is never sent, so
    `ai-service` uses the KB version it has loaded.

    Attributes:
        message: The pseudonymized message.
        order_context: The order facts; absent for a ticket without an order.
        as_of: The ticket's `created_at`.
        intent_override: The intent that staff chose, when they chose one.
    """

    message: str
    order_context: OrderContext | None
    as_of: datetime
    intent_override: IntentLabel | None


@dataclass(frozen=True, slots=True)
class AssetVersions:
    """The release and the asset versions that produced a result (DATA-56).

    Attributes:
        release_id: The release manifest.
        model_version: The intent model.
        kb_version: The KB.
        mapping_version: The document-to-intent mapping.
        prompt_version: The prompts.
        routing_version: The routing configuration.
        index_version: The retrieval index.
    """

    release_id: str
    model_version: str
    kb_version: str
    mapping_version: str
    prompt_version: str
    routing_version: str
    index_version: str


@dataclass(frozen=True, slots=True)
class StepLatencies:
    """The time of each step of one call, in milliseconds.

    Attributes:
        total_ms: The whole call.
        analysis_ms: The steps up to routing.
        llm_ms: The LLM step; absent when the LLM was not called.
    """

    total_ms: int
    analysis_ms: int
    llm_ms: int | None


@dataclass(frozen=True, slots=True)
class ModelIntent:
    """The top intent of the model, with its calibrated probability.

    Attributes:
        label: The intent.
        probability: The calibrated probability, in [0, 1].
        confidence_band: Its band.
    """

    label: IntentLabel
    probability: float
    confidence_band: ConfidenceBand


@dataclass(frozen=True, slots=True)
class StaffIntent:
    """An intent that staff chose, without a probability.

    Attributes:
        label: The intent.
    """

    label: IntentLabel


type AnalysisIntent = ModelIntent | StaffIntent


@dataclass(frozen=True, slots=True)
class IntentAlternative:
    """A further candidate intent of the model.

    Attributes:
        label: The intent.
        probability: The calibrated probability, in [0, 1].
    """

    label: IntentLabel
    probability: float


@dataclass(frozen=True, slots=True)
class RankedDocument:
    """A KB document version that retrieval found.

    Attributes:
        document_id: The document.
        version: The version.
        title: The title.
        policy_key: The policy key.
        effective_start_at: When the version takes effect.
        effective_end_at: When it stops; absent when open-ended.
        validity: Whether it supports a claim at `as_of`.
        rank: The rank, from 1.
        snippet: The supporting snippet.
    """

    document_id: KbDocumentId
    version: KbDocumentVersionTag
    title: str
    policy_key: str
    effective_start_at: datetime
    effective_end_at: datetime | None
    validity: DocumentValidity
    rank: int
    snippet: str


@dataclass(frozen=True, slots=True)
class Routing:
    """The routing recommendation and its reason codes.

    Attributes:
        recommendation: The recommended next step.
        reason_codes: The reason codes, without repeats.
    """

    recommendation: RoutingRecommendation
    reason_codes: tuple[AiReasonCode, ...]


@dataclass(frozen=True, slots=True)
class AiWarning:
    """A condition that allows a draft but needs staff attention.

    Attributes:
        warning_id: Unique within its suggestion.
        reason_code: Why.
    """

    warning_id: str
    reason_code: AiReasonCode


@dataclass(frozen=True, slots=True)
class Analysis:
    """The result of the pipeline up to routing (ADR-0005).

    Attributes:
        intent: The intent that the pipeline used.
        alternatives: The next most likely intents.
        is_in_scope: Whether the intent is in scope.
        documents: The ranked documents.
        routing: The routing recommendation.
        warnings: The warnings.
        versions: The versions that produced it.
        step_latencies: The time of each step.
    """

    intent: AnalysisIntent
    alternatives: tuple[IntentAlternative, ...]
    is_in_scope: bool
    documents: tuple[RankedDocument, ...]
    routing: Routing
    warnings: tuple[AiWarning, ...]
    versions: AssetVersions
    step_latencies: StepLatencies


@dataclass(frozen=True, slots=True, repr=False)
class DraftSegment:
    """One segment of a draft. Its text is Confidential AI text with placeholders.

    Attributes:
        segment_id: Unique within the draft.
        paragraph_index: The paragraph, from 0, never decreasing.
        text: The text.
        citation_ids: The citations that support it.
    """

    segment_id: str
    paragraph_index: int
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True, repr=False)
class KbDocumentCitation:
    """A citation of a KB document version.

    Attributes:
        citation_id: Unique within the draft.
        document_id: The document.
        version: The version.
        snippet: The supporting snippet.
    """

    citation_id: str
    document_id: KbDocumentId
    version: KbDocumentVersionTag
    snippet: str


@dataclass(frozen=True, slots=True)
class OrderContextCitation:
    """A citation of a field of the order context, never of its value (ADR-0014).

    Attributes:
        citation_id: Unique within the draft.
        field: The field.
    """

    citation_id: str
    field: OrderContextField


type Citation = KbDocumentCitation | OrderContextCitation


@dataclass(frozen=True, slots=True, repr=False)
class Draft:
    """An AI-proposed reply, made of segments with citations. Confidential.

    Attributes:
        segments: The segments in reading order.
        citations: The sources that the segments cite.
    """

    segments: tuple[DraftSegment, ...]
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class MaskCounts:
    """The masks that the second layer of ai-service applied, by type (ADR-0010).

    Attributes:
        email: `[EMAIL]` masks.
        phone: `[PHONE]` masks.
        card: `[CARD]` masks.
    """

    email: int
    phone: int
    card: int


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """What the LLM requests of one call used.

    Attributes:
        input_token_count: Input tokens, retries included.
        output_token_count: Output tokens, retries included.
        cost_micro_usd: The cost, in millionths of a US dollar.
    """

    input_token_count: int
    output_token_count: int
    cost_micro_usd: int


@dataclass(frozen=True, slots=True, repr=False)
class DraftOutcomeDetails:
    """The fields that every draft outcome carries, whatever its status.

    Attributes:
        reason_codes: The routing codes plus the codes of the drafting step.
        analysis: The analysis computed in the same call.
        staff_note: AI text for staff only, with placeholders; absent when empty.
        versions: The versions that produced the outcome.
        step_latencies: The time of each step of the call.
        mask_counts: The masks applied before the LLM call.
        llm_usage: The LLM usage, when the LLM answered.
    """

    reason_codes: tuple[AiReasonCode, ...]
    analysis: Analysis
    staff_note: str | None
    versions: AssetVersions
    step_latencies: StepLatencies
    mask_counts: MaskCounts
    llm_usage: LlmUsage | None


@dataclass(frozen=True, slots=True, repr=False)
class DraftReady:
    """A draft outcome with a draft.

    Attributes:
        details: The fields of every outcome.
        draft: The draft.
    """

    details: DraftOutcomeDetails
    draft: Draft


@dataclass(frozen=True, slots=True, repr=False)
class NoDraft:
    """A draft outcome without a draft.

    Attributes:
        status: Why there is no draft.
        details: The fields of every outcome.
    """

    status: NoDraftStatus
    details: DraftOutcomeDetails


type DraftOutcome = DraftReady | NoDraft


@dataclass(frozen=True, slots=True, repr=False)
class ReceivedAnalysis:
    """An analysis and the response body it came from, stored as received (ADR-0010).

    Attributes:
        analysis: The parsed analysis.
        body: The JSON text of the response. Internal.
    """

    analysis: Analysis
    body: str


@dataclass(frozen=True, slots=True, repr=False)
class ReceivedDraftOutcome:
    """A draft outcome and the response body it came from, stored as received.

    Attributes:
        outcome: The parsed outcome.
        body: The JSON text of the response. Confidential.
        analysis_body: The JSON text of its embedded `analysis`, stored as the analysis part
            when the `createAnalysis` call of the same suggestion failed or was not made.
    """

    outcome: DraftOutcome
    body: str
    analysis_body: str

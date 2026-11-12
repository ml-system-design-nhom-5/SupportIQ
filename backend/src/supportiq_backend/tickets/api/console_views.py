"""Map the console's domain values to the models of `backend` contract 1.2.0, and back.

Pseudonyms are already restored in the texts that reach this module (ADR-0010). An
`order_context` citation gets the value of its field from the request that the suggestion
sent, so staff see what the draft was written from (contracts v1 design, `SuggestionView`).
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import assert_never
from uuid import UUID

from pydantic import MISSING

from supportiq_backend.commerce import AddressedOrder, Money, Order
from supportiq_backend.commerce.api.shop import to_money, to_order_view
from supportiq_backend.generated import (
    AiDraftReplyRequest,
    AiItemId,
    AnalysisPart,
    AssetVersion,
    CitationView,
    ConsoleCustomerView,
    ConsoleDraftSegment,
    ConsoleIntent,
    ConsoleIntentAlternative,
    ConsoleMessageView,
    ConsoleModelIntent,
    ConsoleOrderContextCitation,
    ConsoleOrderView,
    ConsoleOtherOrderView,
    ConsoleReplyView,
    ConsoleRouting,
    ConsoleStaffIntent,
    ConsoleTicketStatus,
    DraftPart,
    KbDocumentId,
    KbDocumentVersionTag,
    MessageText,
    NoAiDraftReplyRequest,
    NoDraftPart,
    OrderFactValue,
    PendingAnalysisPart,
    PendingDraftPart,
    ReadyAnalysisPart,
    ReadyDraftPart,
    RejectedAiDraftReplyRequest,
    ReplyBody,
    ReplyProposalReplyRequest,
    StaffMemberView,
    SuggestionView,
    TicketSummaryIntent,
    UnavailableAnalysisPart,
    UnavailableDraftPart,
)
from supportiq_backend.generated import (
    AiReasonCode as ContractAiReasonCode,
)
from supportiq_backend.generated import (
    AssetVersions as ContractAssetVersions,
)
from supportiq_backend.generated import (
    ConfidenceBand as ContractConfidenceBand,
)
from supportiq_backend.generated import (
    DocumentValidity as ContractDocumentValidity,
)
from supportiq_backend.generated import (
    DraftStatus as ContractDraftStatus,
)
from supportiq_backend.generated import (
    HandlingMode as ContractHandlingMode,
)
from supportiq_backend.generated import (
    IntentLabel as ContractIntentLabel,
)
from supportiq_backend.generated import (
    KbDocumentCitation as ContractKbDocumentCitation,
)
from supportiq_backend.generated import (
    OrderContextField as ContractOrderContextField,
)
from supportiq_backend.generated import (
    OrderStatus as ContractOrderStatus,
)
from supportiq_backend.generated import (
    RankedDocument as ContractRankedDocument,
)
from supportiq_backend.generated import (
    RefundStatus as ContractRefundStatus,
)
from supportiq_backend.generated import (
    ReplyBasis as ContractReplyBasis,
)
from supportiq_backend.generated import (
    RoutingRecommendation as ContractRoutingRecommendation,
)
from supportiq_backend.generated import (
    ShipmentStatus as ContractShipmentStatus,
)
from supportiq_backend.generated import (
    StepLatencies as ContractStepLatencies,
)
from supportiq_backend.generated import (
    SuggestionTrigger as ContractSuggestionTrigger,
)
from supportiq_backend.generated import (
    TicketAction as ContractTicketAction,
)
from supportiq_backend.generated import (
    TicketSummary as ContractTicketSummary,
)
from supportiq_backend.generated import (
    TicketWorkspace as ContractTicketWorkspace,
)
from supportiq_backend.generated import (
    Warning as ContractWarning,
)
from supportiq_backend.platform import (
    RequestContractError,
    UnexpectedFailureError,
    is_storable_text,
)
from supportiq_backend.platform.web import format_timestamp
from supportiq_backend.suggestions import (
    AiReasonCode,
    Analysis,
    AnalysisIntent,
    AnalysisState,
    AssetVersions,
    CancelledPart,
    Citation,
    DraftReady,
    DraftState,
    KbDocumentCitation,
    ModelIntent,
    NoDraft,
    OrderContext,
    OrderContextCitation,
    OrderContextField,
    PendingPart,
    RankedDocument,
    StaffIntent,
    StepLatencies,
    Suggestion,
    SuggestionId,
    UnavailablePart,
    get_part_status,
)
from supportiq_backend.tickets.domain import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalId,
    ProposalReply,
    RejectedAiDraftReply,
    ReplyRecord,
    ReplyRequest,
    RestoredSuggestion,
    StaffReasonCode,
    TicketSummary,
    TicketWorkspace,
)

_BODY_LOCATION = "body.body"
_PROPOSAL_LOCATION = "body.proposal_id"
_NOTE_LOCATION = "body.note"

type _ParsedReplyBody = (
    AiDraftReplyRequest
    | RejectedAiDraftReplyRequest
    | NoAiDraftReplyRequest
    | ReplyProposalReplyRequest
)


def to_ticket_summary(summary: TicketSummary) -> ContractTicketSummary:
    """Map one ticket of a queue to the contract.

    Args:
        summary: The ticket, its customer's name, and its current suggestion.

    Returns:
        The contract model; the draft status is absent in manual mode, and the predicted
        intent is absent without a model analysis.
    """
    ticket = summary.ticket
    suggestion = summary.suggestion
    predicted = None if suggestion is None else suggestion.predicted_intent
    return ContractTicketSummary(
        ticket_id=ticket.ticket_id,
        created_at=format_timestamp(ticket.created_at),
        status=ConsoleTicketStatus(ticket.status.value),
        handling_mode=ContractHandlingMode(ticket.handling_mode.value),
        is_authority_required=ticket.is_authority_required,
        handling_started_at=_optional_time(ticket.handling_started_at),
        closed_at=_optional_time(ticket.closed_at),
        customer=ConsoleCustomerView(display_name=summary.customer_display_name),
        message_excerpt=ticket.message_excerpt,
        draft_status=(
            MISSING
            if suggestion is None
            else ContractDraftStatus(get_part_status(suggestion.draft).value)
        ),
        predicted_intent=(
            MISSING
            if predicted is None
            else TicketSummaryIntent(
                label=ContractIntentLabel(predicted.label.value),
                probability=predicted.probability,
                confidence_band=ContractConfidenceBand(predicted.confidence_band.value),
            )
        ),
    )


def to_workspace(workspace: TicketWorkspace) -> ContractTicketWorkspace:
    """Map the ticket workspace to the contract.

    Args:
        workspace: The workspace, with the AI text restored.

    Returns:
        The contract model.
    """
    ticket = workspace.ticket
    return ContractTicketWorkspace(
        ticket_id=ticket.ticket_id,
        status=ConsoleTicketStatus(ticket.status.value),
        handling_mode=ContractHandlingMode(ticket.handling_mode.value),
        is_authority_required=ticket.is_authority_required,
        created_at=format_timestamp(ticket.created_at),
        handling_started_at=_optional_time(ticket.handling_started_at),
        closed_at=_optional_time(ticket.closed_at),
        customer=ConsoleCustomerView(display_name=workspace.customer_display_name),
        message=ConsoleMessageView(
            body=MessageText(ticket.message), created_at=format_timestamp(ticket.created_at)
        ),
        order=MISSING if workspace.order is None else _to_order(workspace.order),
        other_orders=(
            [_to_other_order(order) for order in workspace.other_orders]
            if workspace.other_orders
            else MISSING
        ),
        suggestion=MISSING
        if workspace.suggestion is None
        else to_suggestion_view(workspace.suggestion),
        reply=MISSING if workspace.reply is None else to_reply_view(workspace.reply),
        allowed_actions=sorted(
            (ContractTicketAction(action.value) for action in workspace.allowed_actions),
            key=lambda action: action.value,
        ),
    )


def to_suggestion_view(restored: RestoredSuggestion) -> SuggestionView:
    """Map a suggestion with its restored texts to the contract.

    Args:
        restored: The suggestion and its restored texts.

    Returns:
        The contract model.
    """
    suggestion = restored.suggestion
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
        analysis=AnalysisPart(_to_analysis_part(suggestion.analysis)),
        draft=DraftPart(_to_draft_part(restored)),
    )


def to_pending_suggestion_view(suggestion: Suggestion) -> SuggestionView:
    """Map a suggestion that has no result yet, as `createSuggestion` answers it.

    Args:
        suggestion: The new suggestion.

    Returns:
        The contract model.
    """
    return to_suggestion_view(RestoredSuggestion(suggestion, (), None, None))


def to_reply_view(record: ReplyRecord) -> ConsoleReplyView:
    """Map a sent reply to the contract.

    Args:
        record: The reply and its sender's name.

    Returns:
        The contract model.
    """
    reply = record.reply
    return ConsoleReplyView(
        reply_id=str(reply.reply_id),
        basis=ContractReplyBasis(reply.basis.value),
        body=ReplyBody(MessageText(reply.body)),
        suggestion_id=MISSING if reply.suggestion_id is None else reply.suggestion_id,
        proposal_id=MISSING if reply.proposal_id is None else str(reply.proposal_id),
        sent_by=StaffMemberView(account_id=reply.sent_by, display_name=record.sent_by_display_name),
        sent_at=format_timestamp(reply.sent_at),
    )


def to_reply_request(body: _ParsedReplyBody) -> ReplyRequest:
    """Turn a reply body of the contract into the domain request (CODE-32).

    Args:
        body: The parsed body, discriminated by `basis`.

    Returns:
        The domain request.

    Raises:
        RequestContractError: A text cannot be stored, or the proposal ID is not a UUID.
    """
    text = _storable(body.body.root.root, _BODY_LOCATION)
    match body:
        case AiDraftReplyRequest():
            return AiDraftReply(
                body=text,
                suggestion_id=SuggestionId(body.suggestion_id),
                acknowledged_warning_ids=frozenset(
                    item.root for item in body.acknowledged_warning_ids
                ),
                staff_reason_codes=(
                    ()
                    if body.staff_reason_codes is MISSING
                    else tuple(StaffReasonCode(code.value) for code in body.staff_reason_codes)
                ),
                note=None if body.note is MISSING else _storable(body.note.root, _NOTE_LOCATION),
            )
        case RejectedAiDraftReplyRequest():
            return RejectedAiDraftReply(
                body=text,
                suggestion_id=SuggestionId(body.suggestion_id),
                staff_reason_codes=tuple(
                    StaffReasonCode(code.value) for code in body.staff_reason_codes
                ),
                note=None if body.note is MISSING else _storable(body.note.root, _NOTE_LOCATION),
            )
        case NoAiDraftReplyRequest():
            return NoAiDraftReply(
                text, None if body.suggestion_id is MISSING else SuggestionId(body.suggestion_id)
            )
        case ReplyProposalReplyRequest():
            return ProposalReply(text, _to_proposal_id(body.proposal_id))
        case _:
            assert_never(body)


def _to_analysis_part(
    state: AnalysisState,
) -> PendingAnalysisPart | ReadyAnalysisPart | UnavailableAnalysisPart:
    match state:
        case PendingPart():
            return PendingAnalysisPart(analysis_status="pending")
        case UnavailablePart():
            return UnavailableAnalysisPart(
                analysis_status="unavailable",
                reason_codes=[ContractAiReasonCode(state.reason_code.value)],
            )
        case Analysis():
            return _to_ready_analysis(state)
        case CancelledPart():
            # Only a superseded suggestion has cancelled parts, and the workspace shows the
            # current one only.
            raise UnexpectedFailureError
        case _:
            assert_never(state)


def _to_ready_analysis(analysis: Analysis) -> ReadyAnalysisPart:
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
        versions=_to_versions(analysis.versions),
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


def _to_draft_part(
    restored: RestoredSuggestion,
) -> PendingDraftPart | ReadyDraftPart | NoDraftPart | UnavailableDraftPart:
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
            return _to_ready_draft(restored, state)
        case NoDraft():
            return NoDraftPart(
                draft_status=state.status.value,
                reason_codes=_to_reason_codes(state.details.reason_codes),
                staff_note=MISSING if restored.staff_note is None else restored.staff_note,
                versions=_to_versions(state.details.versions),
                step_latencies=_to_latencies(state.details.step_latencies),
            )
        case CancelledPart():
            raise UnexpectedFailureError
        case _:
            assert_never(state)


def _to_ready_draft(restored: RestoredSuggestion, draft: DraftReady) -> ReadyDraftPart:
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
        citations=[_to_citation(citation, sent_context) for citation in draft.draft.citations],
        text=restored.draft_text,
        reason_codes=_to_reason_codes(draft.details.reason_codes),
        staff_note=MISSING if restored.staff_note is None else restored.staff_note,
        versions=_to_versions(draft.details.versions),
        step_latencies=_to_latencies(draft.details.step_latencies),
    )


def _to_citation(citation: Citation, sent_context: OrderContext | None) -> CitationView:
    match citation:
        case KbDocumentCitation():
            return CitationView(
                ContractKbDocumentCitation(
                    source_type="kb_document",
                    citation_id=AiItemId(citation.citation_id),
                    document_id=KbDocumentId(citation.document_id),
                    version=KbDocumentVersionTag(citation.version),
                    snippet=citation.snippet,
                )
            )
        case OrderContextCitation():
            return CitationView(
                ConsoleOrderContextCitation(
                    source_type="order_context",
                    citation_id=AiItemId(citation.citation_id),
                    field=ContractOrderContextField(citation.field.value),
                    value=_order_fact(sent_context, citation.field),
                )
            )
        case _:
            assert_never(citation)


def _order_fact(context: OrderContext | None, field: OrderContextField) -> OrderFactValue:
    # The grounding check of ai-service makes every order citation name a field that the
    # request sent (ADR-0014, statement 4), so a missing value is a defect.
    value = None if context is None else _FACT_READERS[field](context)
    if value is None:
        raise UnexpectedFailureError
    return value


def _time_fact(moment: datetime | None) -> OrderFactValue | None:
    return None if moment is None else OrderFactValue(format_timestamp(moment))


def _money_fact(money: Money | None) -> OrderFactValue | None:
    return None if money is None else OrderFactValue(to_money(money))


_FACT_READERS: Mapping[OrderContextField, Callable[[OrderContext], OrderFactValue | None]] = (
    MappingProxyType(
        {
            OrderContextField.ORDER_STATUS: lambda context: (
                None
                if context.order_status is None
                else OrderFactValue(ContractOrderStatus(context.order_status.value))
            ),
            OrderContextField.PLACED_AT: lambda context: _time_fact(context.placed_at),
            OrderContextField.ORDER_TOTAL: lambda context: _money_fact(context.order_total),
            OrderContextField.SHIPPING_COST: lambda context: _money_fact(context.shipping_cost),
            OrderContextField.SHIPMENT_STATUS: lambda context: (
                None
                if context.shipment_status is None
                else OrderFactValue(ContractShipmentStatus(context.shipment_status.value))
            ),
            OrderContextField.ESTIMATED_DELIVERY_AT: lambda context: _time_fact(
                context.estimated_delivery_at
            ),
            OrderContextField.DELIVERED_AT: lambda context: _time_fact(context.delivered_at),
            OrderContextField.REFUND_STATUS: lambda context: (
                None
                if context.refund_status is None
                else OrderFactValue(ContractRefundStatus(context.refund_status.value))
            ),
            OrderContextField.REFUND_AMOUNT: lambda context: _money_fact(context.refund_amount),
            OrderContextField.REFUND_REQUESTED_AT: lambda context: _time_fact(
                context.refund_requested_at
            ),
        }
    )
)


def _to_document(document: RankedDocument) -> ContractRankedDocument:
    return ContractRankedDocument(
        document_id=KbDocumentId(document.document_id),
        version=KbDocumentVersionTag(document.version),
        title=document.title,
        policy_key=document.policy_key,
        effective_start_at=format_timestamp(document.effective_start_at),
        effective_end_at=_optional_time(document.effective_end_at),
        validity=ContractDocumentValidity(document.validity.value),
        rank=document.rank,
        snippet=document.snippet,
    )


def _to_versions(versions: AssetVersions) -> ContractAssetVersions:
    return ContractAssetVersions(
        release_id=versions.release_id,
        model_version=AssetVersion(versions.model_version),
        kb_version=AssetVersion(versions.kb_version),
        mapping_version=AssetVersion(versions.mapping_version),
        prompt_version=AssetVersion(versions.prompt_version),
        routing_version=AssetVersion(versions.routing_version),
        index_version=AssetVersion(versions.index_version),
    )


def _to_latencies(latencies: StepLatencies) -> ContractStepLatencies:
    return ContractStepLatencies(
        total_ms=latencies.total_ms,
        analysis_ms=latencies.analysis_ms,
        llm_ms=MISSING if latencies.llm_ms is None else latencies.llm_ms,
    )


def _to_reason_codes(codes: tuple[AiReasonCode, ...]) -> list[ContractAiReasonCode]:
    return [ContractAiReasonCode(code.value) for code in codes]


def _to_order(addressed: AddressedOrder) -> ConsoleOrderView:
    shop_view = to_order_view(addressed.order)
    return ConsoleOrderView(
        order_id=shop_view.order_id,
        order_status=shop_view.order_status,
        placed_at=shop_view.placed_at,
        order_total=shop_view.order_total,
        shipping_cost=shop_view.shipping_cost,
        lines=shop_view.lines,
        shipment=shop_view.shipment,
        refund=shop_view.refund,
        shipping_address=addressed.shipping_address,
    )


def _to_other_order(order: Order) -> ConsoleOtherOrderView:
    shop_view = to_order_view(order)
    return ConsoleOtherOrderView(
        order_id=shop_view.order_id,
        order_status=shop_view.order_status,
        shipment_status=ContractShipmentStatus(order.shipment.status.value),
        refund_status=(
            MISSING if order.refund is None else ContractRefundStatus(order.refund.status.value)
        ),
        placed_at=shop_view.placed_at,
        order_total=shop_view.order_total,
        lines=shop_view.lines,
    )


def _optional_time(moment: datetime | None) -> str | MISSING:
    return MISSING if moment is None else format_timestamp(moment)


def _storable(text: str, location: str) -> str:
    if not is_storable_text(text):
        raise RequestContractError((location,))
    return text


def _to_proposal_id(raw: str) -> ProposalId:
    try:
        return ProposalId(UUID(raw))
    except ValueError as error:
        raise RequestContractError((_PROPOSAL_LOCATION,)) from error

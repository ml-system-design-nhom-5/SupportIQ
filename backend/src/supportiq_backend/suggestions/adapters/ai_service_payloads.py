"""The bodies of `ai-service` contract 1.0.0, mapped to and from the domain (ARCH-15).

Responses are parsed in strict mode with the generated models. A value outside the contract,
such as an unknown status or reason code, is a contract error: the part becomes `unavailable`,
because an unknown reason code could be one that requires authority (CON-22). Three rules of
the contract that the generator cannot express are checked here: `ai-service` never sends the
reason codes that only backend sets, an outcome without a draft never carries `draft`, and a
KB document version is the one that its path named.
"""

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import assert_never

from pydantic import MISSING, BaseModel, ConfigDict, JsonValue, ValidationError

from supportiq_backend.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from supportiq_backend.platform import NonUtcTimestampError, format_timestamp, parse_timestamp
from supportiq_backend.suggestions.adapters import generated as contract
from supportiq_backend.suggestions.domain import (
    AiReasonCode,
    AiServiceContractError,
    AiWarning,
    Analysis,
    AnalysisIntent,
    AssetVersions,
    Citation,
    ConfidenceBand,
    DocumentValidity,
    Draft,
    DraftOutcome,
    DraftOutcomeDetails,
    DraftReady,
    DraftSegment,
    IntentAlternative,
    IntentLabel,
    KbDocumentCitation,
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionTag,
    LlmUsage,
    MaskCounts,
    ModelIntent,
    NoDraft,
    NoDraftStatus,
    OrderContext,
    OrderContextCitation,
    OrderContextField,
    RankedDocument,
    ReceivedAnalysis,
    ReceivedDraftOutcome,
    Routing,
    RoutingRecommendation,
    StaffIntent,
    StepLatencies,
    SuggestionRequest,
)

# The reason codes that only backend sets (`AiServiceReasonCode` in the contract).
_BACKEND_ONLY_REASON_CODES = frozenset(
    {AiReasonCode.AI_SERVICE_UNAVAILABLE, AiReasonCode.PSEUDONYMIZATION_FAILED}
)


class _RawDraftOutcome(BaseModel):
    # The two members that must be read as received, whatever the generated model keeps.
    model_config = ConfigDict(extra="allow")

    analysis: JsonValue
    draft: JsonValue | MISSING = MISSING


def to_request_body(request: SuggestionRequest) -> str:
    """Write the body of `createAnalysis` and `createDraft`.

    The same text is sent and stored in `suggestions.request`, so the record is exactly what
    left backend (backend ticket workflow design, Tables).

    Args:
        request: The request.

    Returns:
        The JSON text, without absent fields (CON-08).
    """
    model = contract.SuggestionRequest(
        message=contract.PseudonymizedText(request.message),
        order_context=(
            MISSING
            if request.order_context is None
            else _to_contract_order_context(request.order_context)
        ),
        as_of=format_timestamp(request.as_of),
        intent_override=(
            MISSING
            if request.intent_override is None
            else contract.IntentLabel(request.intent_override.value)
        ),
    )
    return model.model_dump_json(exclude_none=True, by_alias=True)


def parse_analysis_response(body: bytes) -> ReceivedAnalysis:
    """Parse the `200` body of `createAnalysis`.

    Args:
        body: The response body.

    Returns:
        The analysis and the body as received.

    Raises:
        AiServiceContractError: The body does not match the contract.
    """
    model = _validate(contract.Analysis, body)
    return ReceivedAnalysis(_to_analysis(model), body.decode())


def parse_draft_response(body: bytes) -> ReceivedDraftOutcome:
    """Parse the `200` body of `createDraft`.

    Args:
        body: The response body.

    Returns:
        The draft outcome, the body, and the body of its embedded analysis.

    Raises:
        AiServiceContractError: The body does not match the contract.
    """
    model = _validate(contract.DraftOutcome, body)
    raw = _validate(_RawDraftOutcome, body)
    if not isinstance(model.root, contract.DraftReadyOutcome) and raw.draft is not MISSING:
        raise AiServiceContractError
    return ReceivedDraftOutcome(
        _to_draft_outcome(model), body.decode(), json.dumps(raw.analysis, ensure_ascii=False)
    )


def parse_asset_versions_response(body: bytes) -> AssetVersions:
    """Parse the `200` body of `getAssetVersions`.

    Args:
        body: The response body.

    Returns:
        The versions.

    Raises:
        AiServiceContractError: The body does not match the contract.
    """
    return _to_versions(_validate(contract.AssetVersions, body))


def parse_kb_document_version_response(
    body: bytes, document_id: KbDocumentId, version: KbDocumentVersionTag
) -> KbDocumentVersion:
    """Parse the `200` body of `getKbDocumentVersion`.

    Args:
        body: The response body.
        document_id: The KB document that the path named.
        version: The version that the path named.

    Returns:
        The document version.

    Raises:
        AiServiceContractError: The body does not match the contract, or it holds another
            document version than the path named, which the citation view must never show.
    """
    model = _validate(contract.KbDocumentVersion, body)
    if model.document_id.root != document_id or model.version.root != version:
        raise AiServiceContractError
    return KbDocumentVersion(
        document_id=document_id,
        version=version,
        title=model.title,
        body=model.body,
        policy_key=model.policy_key,
        effective_start_at=_to_time(model.effective_start_at),
        effective_end_at=_optional(model.effective_end_at, _to_time),
        owner=model.owner,
        source=model.source,
        last_reviewed_at=_optional(model.last_reviewed_at, _to_time),
    )


def parse_stored_analysis(result: object) -> Analysis:
    """Read an analysis that the suggestion store kept as received.

    Args:
        result: The JSON value of `suggestion_parts.result`.

    Returns:
        The analysis.

    Raises:
        AiServiceContractError: The stored value no longer matches the contract: a defect.
    """
    return _to_analysis(_validate(contract.Analysis, _dump(result)))


def parse_stored_draft_outcome(result: object) -> DraftOutcome:
    """Read a draft outcome that the suggestion store kept as received.

    Args:
        result: The JSON value of `suggestion_parts.result`.

    Returns:
        The draft outcome.

    Raises:
        AiServiceContractError: The stored value no longer matches the contract: a defect.
    """
    return _to_draft_outcome(_validate(contract.DraftOutcome, _dump(result)))


def parse_stored_order_context(request: object) -> OrderContext | None:
    """Read the order context of a stored request, for the values of order citations.

    Args:
        request: The JSON value of `suggestions.request`.

    Returns:
        The order context that was sent, or None when the request had none.

    Raises:
        AiServiceContractError: The stored value no longer matches the contract: a defect.
    """
    model = _validate(contract.SuggestionRequest, _dump(request))
    if model.order_context is MISSING:
        return None
    return _to_order_context(model.order_context)


def _validate[ModelT: BaseModel](model_type: type[ModelT], body: bytes) -> ModelT:
    try:
        return model_type.model_validate_json(body, strict=True)
    except ValidationError as error:
        raise AiServiceContractError from error


def _dump(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def _to_analysis(model: contract.Analysis) -> Analysis:
    return Analysis(
        intent=_to_intent(model.intent.root),
        alternatives=tuple(
            IntentAlternative(IntentLabel(item.label.value), item.probability)
            for item in model.alternatives
        ),
        is_in_scope=model.is_in_scope,
        documents=tuple(_to_document(document) for document in model.documents),
        routing=Routing(
            RoutingRecommendation(model.routing.recommendation.value),
            _to_reason_codes(model.routing.reason_codes),
        ),
        warnings=tuple(
            AiWarning(item.warning_id.root, _to_reason_code(item.reason_code))
            for item in model.warnings
        ),
        versions=_to_versions(model.versions),
        step_latencies=_to_latencies(model.step_latencies),
    )


def _to_intent(model: contract.ModelIntent | contract.StaffIntent) -> AnalysisIntent:
    match model:
        case contract.ModelIntent():
            return ModelIntent(
                IntentLabel(model.label.value),
                model.probability,
                ConfidenceBand(model.confidence_band.value),
            )
        case contract.StaffIntent():
            return StaffIntent(IntentLabel(model.label.value))
        case _:
            assert_never(model)


def _to_document(model: contract.RankedDocument) -> RankedDocument:
    return RankedDocument(
        document_id=model.document_id.root,
        version=model.version.root,
        title=model.title,
        policy_key=model.policy_key,
        effective_start_at=_to_time(model.effective_start_at),
        effective_end_at=(
            None if model.effective_end_at is MISSING else _to_time(model.effective_end_at)
        ),
        validity=DocumentValidity(model.validity.value),
        rank=model.rank,
        snippet=model.snippet,
    )


def _to_draft_outcome(model: contract.DraftOutcome) -> DraftOutcome:
    outcome = model.root
    details = DraftOutcomeDetails(
        reason_codes=_to_reason_codes(outcome.reason_codes),
        analysis=_to_analysis(outcome.analysis),
        staff_note=None if outcome.staff_note is MISSING else outcome.staff_note,
        versions=_to_versions(outcome.versions),
        step_latencies=_to_latencies(outcome.step_latencies),
        mask_counts=MaskCounts(
            outcome.mask_count_by_type.email,
            outcome.mask_count_by_type.phone,
            outcome.mask_count_by_type.card,
        ),
        llm_usage=(
            None
            if outcome.llm_usage is MISSING
            else LlmUsage(
                outcome.llm_usage.input_token_count,
                outcome.llm_usage.output_token_count,
                outcome.llm_usage.cost_micro_usd,
            )
        ),
    )
    match outcome:
        case contract.DraftReadyOutcome():
            return DraftReady(details, _to_draft(outcome.draft))
        case contract.NoDraftOutcome():
            return NoDraft(NoDraftStatus(outcome.status), details)
        case _:
            assert_never(outcome)


def _to_draft(model: contract.Draft) -> Draft:
    return Draft(
        segments=tuple(
            DraftSegment(
                segment.segment_id.root,
                segment.paragraph_index,
                segment.text,
                tuple(citation_id.root for citation_id in segment.citation_ids),
            )
            for segment in model.segments
        ),
        citations=tuple(_to_citation(citation.root) for citation in model.citations),
    )


def _to_citation(
    model: contract.KbDocumentCitation | contract.OrderContextCitation,
) -> Citation:
    match model:
        case contract.KbDocumentCitation():
            return KbDocumentCitation(
                model.citation_id.root, model.document_id.root, model.version.root, model.snippet
            )
        case contract.OrderContextCitation():
            return OrderContextCitation(
                model.citation_id.root, OrderContextField(model.field.value)
            )
        case _:
            assert_never(model)


def _to_versions(model: contract.AssetVersions) -> AssetVersions:
    return AssetVersions(
        release_id=model.release_id,
        model_version=model.model_version.root,
        kb_version=model.kb_version.root,
        mapping_version=model.mapping_version.root,
        prompt_version=model.prompt_version.root,
        routing_version=model.routing_version.root,
        index_version=model.index_version.root,
    )


def _to_latencies(model: contract.StepLatencies) -> StepLatencies:
    return StepLatencies(
        total_ms=model.total_ms,
        analysis_ms=model.analysis_ms,
        llm_ms=None if model.llm_ms is MISSING else model.llm_ms,
    )


def _to_reason_codes(
    codes: Iterable[contract.AiServiceReasonCode],
) -> tuple[AiReasonCode, ...]:
    return tuple(_to_reason_code(code) for code in codes)


def _to_reason_code(code: contract.AiServiceReasonCode | contract.AiReasonCode) -> AiReasonCode:
    reason_code = AiReasonCode(code.value)
    if reason_code in _BACKEND_ONLY_REASON_CODES:
        raise AiServiceContractError
    return reason_code


def _to_time(text: str) -> datetime:
    try:
        return parse_timestamp(text)
    except NonUtcTimestampError as error:
        raise AiServiceContractError from error


def _to_order_context(model: contract.OrderContext) -> OrderContext:
    return OrderContext(
        order_status=_optional(model.order_status, lambda value: OrderStatus(value.value)),
        placed_at=_optional(model.placed_at, _to_time),
        order_total=_optional(model.order_total, _to_money),
        shipping_cost=_optional(model.shipping_cost, _to_money),
        shipment_status=_optional(model.shipment_status, lambda value: ShipmentStatus(value.value)),
        estimated_delivery_at=_optional(model.estimated_delivery_at, _to_time),
        delivered_at=_optional(model.delivered_at, _to_time),
        refund_status=_optional(model.refund_status, lambda value: RefundStatus(value.value)),
        refund_amount=_optional(model.refund_amount, _to_money),
        refund_requested_at=_optional(model.refund_requested_at, _to_time),
    )


def _to_contract_order_context(context: OrderContext) -> contract.OrderContext:
    fields: Mapping[str, object] = {
        "order_status": _optional_value(context.order_status, contract.OrderStatus),
        "placed_at": _optional_value(context.placed_at, format_timestamp),
        "order_total": _optional_value(context.order_total, _to_contract_money),
        "shipping_cost": _optional_value(context.shipping_cost, _to_contract_money),
        "shipment_status": _optional_value(context.shipment_status, contract.ShipmentStatus),
        "estimated_delivery_at": _optional_value(context.estimated_delivery_at, format_timestamp),
        "delivered_at": _optional_value(context.delivered_at, format_timestamp),
        "refund_status": _optional_value(context.refund_status, contract.RefundStatus),
        "refund_amount": _optional_value(context.refund_amount, _to_contract_money),
        "refund_requested_at": _optional_value(context.refund_requested_at, format_timestamp),
    }
    return contract.OrderContext.model_validate(
        {name: value for name, value in fields.items() if value is not None}
    )


def _to_money(model: contract.Money) -> Money:
    return Money(model.amount_minor, model.currency)


def _to_contract_money(money: Money) -> contract.Money:
    return contract.Money(amount_minor=money.amount_minor, currency=money.currency)


def _optional[SourceT, TargetT](
    value: SourceT | MISSING, convert: Callable[[SourceT], TargetT]
) -> TargetT | None:
    return None if value is MISSING else convert(value)


def _optional_value[SourceT, TargetT](
    value: SourceT | None, convert: Callable[[SourceT], TargetT]
) -> TargetT | None:
    return None if value is None else convert(value)

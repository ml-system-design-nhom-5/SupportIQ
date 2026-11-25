"""Map the citations of a ready draft to the contract, with the values of the order facts.

An `order_context` citation gets the value of its field from the request that the suggestion
sent, so staff see what the draft was written from (contracts v1 design, `SuggestionView`).
An amount reaches the contract through the order mappings of commerce, which the composition
root passes in (ARCH-17, ARCH-21, ARCH-22).
"""

from datetime import datetime
from typing import assert_never

from app.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from app.generated import (
    AiItemId,
    CitationView,
    ConsoleOrderContextCitation,
    KbDocumentId,
    KbDocumentVersionTag,
    OrderFactValue,
)
from app.generated import KbDocumentCitation as ContractKbDocumentCitation
from app.generated import OrderContextField as ContractOrderContextField
from app.generated import OrderStatus as ContractOrderStatus
from app.generated import RefundStatus as ContractRefundStatus
from app.generated import ShipmentStatus as ContractShipmentStatus
from app.platform import UnexpectedFailureError
from app.platform.web import format_timestamp
from app.suggestions import (
    Citation,
    KbDocumentCitation,
    OrderContext,
    OrderContextCitation,
    OrderContextField,
    OrderFact,
    read_order_fact,
)
from app.tickets.api.order_views import OrderViewMappers


def to_citation_view(
    citation: Citation, sent_context: OrderContext | None, order_views: OrderViewMappers
) -> CitationView:
    """Map one citation of a ready draft to the contract.

    Args:
        citation: The citation of a KB document version or of an order field.
        sent_context: The order context that the suggestion sent, when it sent one.
        order_views: The order mappings of commerce, for an amount.

    Returns:
        The contract model; an order citation carries the value of its field.

    Raises:
        UnexpectedFailureError: An order citation names a field that the request did not
            send: a defect.
    """
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
                    value=_to_fact_value(_read_fact(sent_context, citation.field), order_views),
                )
            )
        case _:
            assert_never(citation)


def _read_fact(context: OrderContext | None, field: OrderContextField) -> OrderFact:
    # The job runner stores no draft that cites a field the request did not send, so a
    # missing value is a defect.
    fact = None if context is None else read_order_fact(context, field)
    if fact is None:
        raise UnexpectedFailureError
    return fact


def _to_fact_value(fact: OrderFact, order_views: OrderViewMappers) -> OrderFactValue:
    match fact:
        case datetime():
            value = format_timestamp(fact)
        case Money():
            value = order_views.to_money(fact)
        case OrderStatus():
            value = ContractOrderStatus(fact.value)
        case ShipmentStatus():
            value = ContractShipmentStatus(fact.value)
        case RefundStatus():
            value = ContractRefundStatus(fact.value)
        case _:
            assert_never(fact)
    return OrderFactValue(value)

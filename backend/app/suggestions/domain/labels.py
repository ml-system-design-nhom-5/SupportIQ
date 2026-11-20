"""The closed sets that the AI results use, with the values of the contracts (PY-10, CODE-30).

They mirror the shared schemas `IntentLabel`, `AiReasonCode`, `ConfidenceBand`,
`DocumentValidity`, and `OrderContextField`, so contract models never enter the domain
(ARCH-15). A value that the contract does not list never reaches this module: the adapter
treats it as a response outside the contract (CON-22).
"""

from enum import StrEnum


class IntentLabel(StrEnum):
    """One of the 46 Bitext intents (contracts v1 design, Common elements)."""

    ADD_PRODUCT = "add_product"
    AVAILABILITY = "availability"
    AVAILABILITY_IN_STORE = "availability_in_store"
    AVAILABILITY_ONLINE = "availability_online"
    CANCEL_ORDER = "cancel_order"
    CHANGE_ACCOUNT = "change_account"
    CHANGE_ORDER = "change_order"
    CLOSE_ACCOUNT = "close_account"
    CUSTOMER_SERVICE = "customer_service"
    DAMAGED_DELIVERY = "damaged_delivery"
    DELIVERY_ISSUE = "delivery_issue"
    DELIVERY_TIME = "delivery_time"
    EXCHANGE_PRODUCT = "exchange_product"
    EXCHANGE_PRODUCT_IN_STORE = "exchange_product_in_store"
    HUMAN_AGENT = "human_agent"
    MISSING_ITEM = "missing_item"
    OPEN_ACCOUNT = "open_account"
    ORDER_HISTORY = "order_history"
    PAY = "pay"
    PAYMENT_ISSUE = "payment_issue"
    PAYMENT_METHODS = "payment_methods"
    PRODUCT_INFORMATION = "product_information"
    PRODUCT_ISSUE = "product_issue"
    RECOVER_PASSWORD = "recover_password"  # noqa: S105  # an intent label
    REFUND_POLICY = "refund_policy"
    REFUND_STATUS = "refund_status"
    REMOVE_PRODUCT = "remove_product"
    REQUEST_INVOICE = "request_invoice"
    REQUEST_REFUND = "request_refund"
    REQUEST_RIGHT_TO_RECTIFICATION = "request_right_to_rectification"
    RETURN_POLICY = "return_policy"
    RETURN_PRODUCT = "return_product"
    RETURN_PRODUCT_IN_STORE = "return_product_in_store"
    RETURN_PRODUCT_ONLINE = "return_product_online"
    SALES_PERIOD = "sales_period"
    SHIPPING_COSTS = "shipping_costs"
    STORE_LOCATION = "store_location"
    STORE_OPENING_HOURS = "store_opening_hours"
    SUBMIT_FEEDBACK = "submit_feedback"
    SUBMIT_PRODUCT_FEEDBACK = "submit_product_feedback"
    SUBMIT_PRODUCT_IDEA = "submit_product_idea"
    TECHNICAL_ISSUE = "technical_issue"
    TRACK_DELIVERY = "track_delivery"
    TRACK_ORDER = "track_order"
    USE_APP = "use_app"
    WRONG_ITEM = "wrong_item"


class AiReasonCode(StrEnum):
    """A reason code of an AI result; the last two are set only by backend."""

    LOW_CONFIDENCE = "low_confidence"
    SIGNAL_DISAGREEMENT = "signal_disagreement"
    OUT_OF_SCOPE_INTENT = "out_of_scope_intent"
    HUMAN_AGENT_REQUESTED = "human_agent_requested"
    REQUIRES_AUTHORITY = "requires_authority"
    NO_VALID_DOCUMENT = "no_valid_document"
    ONLY_EXPIRED_DOCUMENTS = "only_expired_documents"
    CONFLICTING_SOURCES = "conflicting_sources"
    MISSING_INFORMATION = "missing_information"
    SOURCE_REVIEW_OVERDUE = "source_review_overdue"
    GROUNDING_FAILED = "grounding_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    AI_SERVICE_UNAVAILABLE = "ai_service_unavailable"
    PSEUDONYMIZATION_FAILED = "pseudonymization_failed"


class ConfidenceBand(StrEnum):
    """The band of a calibrated probability, computed by ai-service."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentValidity(StrEnum):
    """Whether a KB document version supports a claim at `as_of`."""

    VALID = "valid"
    EXPIRED = "expired"
    CONFLICTING = "conflicting"


class RoutingRecommendation(StrEnum):
    """What the pipeline recommends for a ticket (ADR-0005)."""

    DRAFT = "draft"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"


class OrderContextField(StrEnum):
    """The name of one field of the order context, as an order citation names it (ADR-0014)."""

    ORDER_STATUS = "order_status"
    PLACED_AT = "placed_at"
    ORDER_TOTAL = "order_total"
    SHIPPING_COST = "shipping_cost"
    SHIPMENT_STATUS = "shipment_status"
    ESTIMATED_DELIVERY_AT = "estimated_delivery_at"
    DELIVERED_AT = "delivered_at"
    REFUND_STATUS = "refund_status"
    REFUND_AMOUNT = "refund_amount"
    REFUND_REQUESTED_AT = "refund_requested_at"

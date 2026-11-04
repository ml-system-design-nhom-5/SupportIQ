import json
import math
from pathlib import Path
from typing import Optional
from apps.core_backend.intent.schemas import (
    IntentPrediction,
    RoutingContext,
    RouteDecision,
    IntentPolicy,
)

SUPPORTED_12_INTENTS = [
    "track_order",
    "cancel_order",
    "delivery_time",
    "delivery_issue",
    "shipping_costs",
    "return_policy",
    "return_product",
    "refund_policy",
    "request_refund",
    "refund_status",
    "payment_issue",
    "human_agent",
]

INTENT_TO_QUEUE_MAP = {
    # 34 Escalated intents
    "customer_service": "general_support",
    "change_account": "account_support",
    "close_account": "account_support",
    "open_account": "account_support",
    "order_history": "account_support",
    "recover_password": "account_support",
    "technical_issue": "technical_support",
    "use_app": "technical_support",
    "add_product": "order_support",
    "remove_product": "order_support",
    "change_order": "order_support",
    "request_invoice": "order_support",
    "damaged_delivery": "delivery_support",
    "missing_item": "delivery_support",
    "track_delivery": "delivery_support",
    "wrong_item": "delivery_support",
    "submit_feedback": "feedback_support",
    "submit_product_feedback": "feedback_support",
    "submit_product_idea": "feedback_support",
    "pay": "payments_support",
    "payment_methods": "payments_support",
    "availability": "product_support",
    "availability_in_store": "product_support",
    "availability_online": "product_support",
    "exchange_product": "product_support",
    "exchange_product_in_store": "product_support",
    "product_information": "product_support",
    "product_issue": "product_support",
    "return_product_in_store": "returns_support",
    "return_product_online": "returns_support",
    "sales_period": "sales_support",
    "store_location": "store_support",
    "store_opening_hours": "store_support",
    "request_right_to_rectification": "privacy_support",
    # 12 Supported intents
    "track_order": "order_support",
    "cancel_order": "order_support",
    "delivery_time": "delivery_support",
    "delivery_issue": "delivery_support",
    "shipping_costs": "delivery_support",
    "return_policy": "returns_support",
    "return_product": "returns_support",
    "refund_policy": "payments_support",
    "request_refund": "payments_support",
    "refund_status": "payments_support",
    "payment_issue": "payments_support",
    "human_agent": "general_support",
}

ESCALATED_34_INTENTS = [k for k in INTENT_TO_QUEUE_MAP.keys() if k not in SUPPORTED_12_INTENTS]
STANDARD_INTENTS_46 = sorted(SUPPORTED_12_INTENTS + ESCALATED_34_INTENTS)

# Intents that require an order_id slot when processing individual customer inquiries
SLOT_ORDER_REQUIRED = {
    "track_order",
    "cancel_order",
    "delivery_issue",
    "return_product",
    "request_refund",
    "refund_status",
    "payment_issue",
}

def load_policy_v2(path: Optional[str] = None) -> IntentPolicy:
    if path is None:
        p = Path(__file__).resolve().parent.parent / "config" / "policies" / "intent_policy.v2.json"
    else:
        p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return IntentPolicy(**data)

def decide_route(
    prediction: IntentPrediction,
    context: RoutingContext,
    policy: IntentPolicy,
) -> RouteDecision:
    """Deterministic routing decision following strict gate priority order:
    1. Check for ML / output validity (NaN, score out of range, error, unknown label) -> manual_fallback
    2. Check explicit human request rule -> escalate to general_support
    3. Check confidence and margin threshold -> clarify or escalate if max clarify reached
    4. Check if intent is among 34 out-of-scope intents -> escalate to designated team
    5. Check if intent is human_agent -> escalate to general_support
    6. Check required slots for supported self-service -> missing -> clarify
    7. All gates passed -> retrieve_draft
    """
    predicted = prediction.intent
    final_intent = context.intent_override or predicted
    model_ver = prediction.model_version
    pol_ver = policy.version

    # Gate 1: Check ML failure or invalid score / unmapped label
    if (
        prediction.error
        or math.isnan(prediction.confidence)
        or math.isinf(prediction.confidence)
        or prediction.confidence < 0.0
        or prediction.confidence > 1.0
        or final_intent not in STANDARD_INTENTS_46
    ):
        return RouteDecision(
            action="manual_fallback",
            predicted_intent=predicted,
            final_intent="unknown" if final_intent not in STANDARD_INTENTS_46 else final_intent,
            requested_team="general_support",
            target_queue="standard",
            reason_codes=["invalid_model_output"] if not prediction.error else ["ml_unavailable"],
            model_version=model_ver,
            policy_version=pol_ver,
        )

    team = INTENT_TO_QUEUE_MAP.get(final_intent, "general_support")

    # Gate 2: Explicit human request rule
    if context.is_explicit_human_request:
        return RouteDecision(
            action="escalate",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team="general_support",
            target_queue="standard",
            reason_codes=["explicit_human_request"],
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 3: Confidence and margin check before any sensitive/slot execution
    conf_thresh = policy.confidence_thresholds.get(final_intent, policy.default_confidence_threshold)
    margin_thresh = policy.margin_thresholds.get(final_intent, policy.default_margin_threshold)

    is_low_conf = prediction.confidence < conf_thresh
    is_low_margin = prediction.margin is not None and prediction.margin < margin_thresh

    if is_low_conf or is_low_margin:
        reasons = []
        if is_low_conf:
            reasons.append("low_confidence")
        if is_low_margin:
            reasons.append("low_margin")

        if context.clarify_count >= 1:
            reasons.append("max_clarify_reached")
            return RouteDecision(
                action="escalate",
                predicted_intent=predicted,
                final_intent=final_intent,
                requested_team=team,
                target_queue="manager" if final_intent in policy.sensitive_action_intents else "standard",
                reason_codes=reasons,
                model_version=model_ver,
                policy_version=pol_ver,
            )
        return RouteDecision(
            action="clarify",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team=team,
            target_queue="standard",
            reason_codes=reasons,
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 4: 34 Escalated intents
    if final_intent in ESCALATED_34_INTENTS:
        return RouteDecision(
            action="escalate",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team=team,
            target_queue="standard",
            reason_codes=["recognized_outside_product_scope"],
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 5: human_agent intent
    if final_intent == "human_agent":
        return RouteDecision(
            action="escalate",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team="general_support",
            target_queue="standard",
            reason_codes=["human_agent_requested"],
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 6: Required slots for remaining 11 supported intents
    required_slots = []
    missing_slots = []
    if final_intent in SLOT_ORDER_REQUIRED:
        required_slots.append("order_id")
        if not context.extracted_slots.get("order_id"):
            missing_slots.append("order_id")

    if missing_slots:
        return RouteDecision(
            action="clarify",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team=team,
            target_queue="standard",
            reason_codes=["missing_order_id"],
            required_slots=required_slots,
            missing_slots=missing_slots,
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 7: All passed -> retrieve_draft
    return RouteDecision(
        action="retrieve_draft",
        predicted_intent=predicted,
        final_intent=final_intent,
        requested_team=team,
        target_queue="manager" if final_intent in policy.sensitive_action_intents else "standard",
        reason_codes=[],
        required_slots=required_slots,
        missing_slots=[],
        must_human_approve=True,
        can_execute_transaction=False,
        model_version=model_ver,
        policy_version=pol_ver,
    )

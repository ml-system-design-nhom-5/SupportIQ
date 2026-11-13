import json
import math
from pathlib import Path
from typing import Any, Optional
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

# Intents that require an order_id slot when processing personal customer requests
PERSONAL_ORDER_REQUIRED = {
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

def _is_invalid_finite_range(
    value: Any,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    *,
    strictly_positive: bool = False,
) -> bool:
    if value is None:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return True
    num = float(value)
    if not math.isfinite(num):
        return True
    if strictly_positive and num <= 0.0:
        return True
    if min_value is not None and num < min_value:
        return True
    if max_value is not None and num > max_value:
        return True
    return False


def _is_invalid_optional_bool(value: Any) -> bool:
    return value is not None and type(value) is not bool


def _is_invalid_rejector_decision(value: Any) -> bool:
    if value is None:
        return False
    return not isinstance(value, str) or value.lower() not in {"accept", "reject"}


def decide_route(
    prediction: IntentPrediction,
    context: RoutingContext,
    policy: IntentPolicy,
) -> RouteDecision:
    """Deterministic routing decision following strict gate priority order."""
    predicted = prediction.intent
    model_ver = prediction.model_version
    pol_ver = policy.version

    # Gate 0: Validate override provenance and actor scope
    final_intent = predicted
    has_valid_override = False
    if context.intent_override:
        can_override = "intent:override" in context.verified_scope
        has_provenance = (
            context.override_provenance
            and "actor_id" in context.override_provenance
            and "reason" in context.override_provenance
        )
        if can_override and has_provenance:
            final_intent = context.intent_override
            has_valid_override = True
        else:
            # Unauthorized or unprovenanced override is rejected; keep predicted intent
            final_intent = predicted

    # Gate 1: Check ML failure or invalid score / unmapped label / invalid margin / malformed control fields
    is_invalid_confidence = _is_invalid_finite_range(prediction.confidence, 0.0, 1.0)
    is_invalid_margin = _is_invalid_finite_range(prediction.margin, -1.0, 1.0)
    is_invalid_controls = (
        _is_invalid_optional_bool(getattr(prediction, "selective_accepted", None))
        or _is_invalid_optional_bool(getattr(prediction, "rejected_by_experimental_adapter", None))
        or _is_invalid_optional_bool(getattr(prediction, "verified", None))
        or _is_invalid_rejector_decision(getattr(prediction, "rejector_decision", None))
        or _is_invalid_finite_range(getattr(prediction, "selective_score", None), 0.0, 1.0)
        or _is_invalid_finite_range(getattr(prediction, "selective_threshold", None), 0.0, 1.0)
        or _is_invalid_finite_range(getattr(prediction, "raw_confidence", None), 0.0, 1.0)
        or _is_invalid_finite_range(getattr(prediction, "raw_margin", None), -1.0, 1.0)
        or _is_invalid_finite_range(getattr(prediction, "calibration_temperature", None), strictly_positive=True)
    )

    # Gate 1: Explicit human request rule (Verified human request overrides ML errors or classification)
    is_human_requested = getattr(context, "is_explicit_human_request", False) or getattr(context, "is_human_agent_requested", False)
    if is_human_requested:
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

    # Gate 1b: Fail-closed on invalid ML output or ML service error
    if (
        prediction.error
        or is_invalid_confidence
        or is_invalid_margin
        or is_invalid_controls
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

    # Gate 2b: human_agent intent always escalates immediately to general_support
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

    # Gate 2c: 34 Escalated intents outside product scope always escalate
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

    conf_thresh = policy.confidence_thresholds.get(final_intent, policy.default_confidence_threshold)
    margin_thresh = policy.margin_thresholds.get(final_intent, policy.default_margin_threshold)

    is_low_conf = prediction.confidence < conf_thresh
    is_low_margin = prediction.margin is not None and prediction.margin < margin_thresh
    is_sensitive = (
        final_intent in policy.sensitive_action_intents
        or predicted in policy.sensitive_action_intents
    )

    # Gate 2d: Explicit selective rejector veto blocks automatic retrieve_draft
    selective_accepted = getattr(prediction, "selective_accepted", None)
    rejected_flag = getattr(prediction, "rejected_by_experimental_adapter", None)
    rejector_decision = getattr(prediction, "rejector_decision", None)
    is_selective_rejected = (
        (selective_accepted is False)
        or (rejected_flag is True)
        or (isinstance(rejector_decision, str) and rejector_decision.lower() == "reject")
    )
    if not has_valid_override and is_selective_rejected:
        reasons = ["selective_rejected"]
        if is_low_conf:
            reasons.append("low_confidence")
        if is_low_margin:
            reasons.append("low_margin")
        if is_sensitive:
            reasons.append("requires_authority")
        return RouteDecision(
            action="manual_fallback",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team=team,
            target_queue="manager" if is_sensitive else "standard",
            reason_codes=reasons,
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 3: Confidence and margin check for the 11 supported product intents
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

    # Gate 6: Required slots for remaining 11 supported intents
    # Distinguish personal order lookup vs general policy questions:
    # Only require order_id when inquiry is marked as personal or contains order slots
    required_slots = []
    missing_slots = []
    needs_order = final_intent in PERSONAL_ORDER_REQUIRED and (
        context.is_personal_lookup or "order_id" in context.extracted_slots or final_intent == "track_order"
    )

    if needs_order:
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

    # Gate 7: Policy approval check - if policy not formally approved, fail-closed to manual_fallback / human review
    if not policy.approved:
        return RouteDecision(
            action="manual_fallback",
            predicted_intent=predicted,
            final_intent=final_intent,
            requested_team=team,
            target_queue="standard",
            reason_codes=["policy_not_approved"],
            model_version=model_ver,
            policy_version=pol_ver,
        )

    # Gate 8: All passed -> retrieve_draft
    return RouteDecision(
        action="retrieve_draft",
        predicted_intent=predicted,
        final_intent=final_intent,
        requested_team=team,
        target_queue="manager" if is_sensitive else "standard",
        reason_codes=["requires_authority"] if is_sensitive else [],
        required_slots=required_slots,
        missing_slots=[],
        must_human_approve=True,
        can_execute_transaction=False,
        model_version=model_ver,
        policy_version=pol_ver,
    )

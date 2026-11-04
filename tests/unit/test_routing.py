import math
import pytest
from apps.core_backend.intent.schemas import IntentPrediction, RouteDecision, RoutingContext
from apps.core_backend.intent.routing import (
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    ESCALATED_34_INTENTS,
    INTENT_TO_QUEUE_MAP,
    decide_route,
    load_policy_v2,
)

def test_taxonomy_covers_46_exactly():
    """Assert taxonomy has 46 items, 12 supported and 34 escalated are disjoint and union to 46."""
    assert len(STANDARD_INTENTS_46) == 46
    assert len(SUPPORTED_12_INTENTS) == 12
    assert len(ESCALATED_34_INTENTS) == 34
    assert set(SUPPORTED_12_INTENTS).isdisjoint(set(ESCALATED_34_INTENTS))
    assert set(SUPPORTED_12_INTENTS) | set(ESCALATED_34_INTENTS) == set(STANDARD_INTENTS_46)


def test_each_34_maps_to_expected_team():
    """Assert all 34 escalation intents map to expected team/queue and action is escalate."""
    policy = load_policy_v2()
    for intent in ESCALATED_34_INTENTS:
        expected_team = INTENT_TO_QUEUE_MAP[intent]
        pred = IntentPrediction(intent=intent, confidence=0.95, model_version="v2.0.0")
        ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")
        decision = decide_route(pred, ctx, policy)
        assert decision.action == "escalate"
        assert decision.requested_team == expected_team
        assert "recognized_outside_product_scope" in decision.reason_codes
        assert decision.final_intent == intent
        assert decision.must_human_approve is True
        assert decision.can_execute_transaction is False


def test_each_12_has_action():
    """Assert each of the 12 intents has valid action (retrieve_draft, clarify, or escalate for human_agent)."""
    policy = load_policy_v2()
    # 1. human_agent always escalates directly
    pred_human = IntentPrediction(intent="human_agent", confidence=0.90, model_version="v2.0.0")
    ctx_human = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")
    dec_human = decide_route(pred_human, ctx_human, policy)
    assert dec_human.action == "escalate"
    assert dec_human.requested_team == "general_support"

    # 2. General queries (e.g. delivery_time, return_policy, refund_policy) don't require order_id
    pred_deliv = IntentPrediction(intent="delivery_time", confidence=0.90, model_version="v2.0.0")
    dec_deliv = decide_route(pred_deliv, ctx_human, policy)
    assert dec_deliv.action == "retrieve_draft"

    # 3. Personal order queries require order_id slot; missing -> clarify
    pred_track = IntentPrediction(intent="track_order", confidence=0.90, model_version="v2.0.0")
    dec_track_no_slot = decide_route(pred_track, ctx_human, policy)
    assert dec_track_no_slot.action == "clarify"
    assert "missing_order_id" in dec_track_no_slot.reason_codes

    # With order_id slot -> retrieve_draft
    ctx_with_slot = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        extracted_slots={"order_id": "ORD-123"}
    )
    dec_track_with_slot = decide_route(pred_track, ctx_with_slot, policy)
    assert dec_track_with_slot.action == "retrieve_draft"


def test_low_confidence_sensitive_cannot_bypass():
    """Confidence and margin must be checked before sensitive/slot processing."""
    policy = load_policy_v2()
    # Low confidence on sensitive intent (e.g. request_refund) -> clarify (or escalate if max clarify reached)
    pred_low = IntentPrediction(intent="request_refund", confidence=0.40, margin=0.05, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        extracted_slots={"order_id": "ORD-123"},
        clarify_count=0
    )
    decision = decide_route(pred_low, ctx, policy)
    assert decision.action == "clarify"
    assert "low_confidence" in decision.reason_codes

    # If already clarified once -> escalate
    ctx_clarified = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        extracted_slots={"order_id": "ORD-123"},
        clarify_count=1
    )
    decision_clarified = decide_route(pred_low, ctx_clarified, policy)
    assert decision_clarified.action == "escalate"
    assert "max_clarify_reached" in decision_clarified.reason_codes


def test_human_request_escalates():
    """Explicit human request rule triggers direct escalation without relying on ML score."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="track_order", confidence=0.95, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        is_explicit_human_request=True
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "escalate"
    assert "explicit_human_request" in decision.reason_codes
    assert decision.requested_team == "general_support"


def test_queue_does_not_change_actor_role():
    """Target queue or manager queue does not grant transaction capability or change role."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="cancel_order", confidence=0.92, margin=0.5, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        extracted_slots={"order_id": "ORD-123"}
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.can_execute_transaction is False
    assert decision.must_human_approve is True


def test_invalid_or_failed_model_output():
    """NaN, infinite, unknown labels, or ml errors route to manual_fallback."""
    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")

    pred_nan = IntentPrediction(intent="track_order", confidence=math.nan, model_version="v2.0.0")
    dec_nan = decide_route(pred_nan, ctx, policy)
    assert dec_nan.action == "manual_fallback"
    assert "invalid_model_output" in dec_nan.reason_codes

    pred_unknown = IntentPrediction(intent="random_invented_intent", confidence=0.99, model_version="v2.0.0")
    dec_unknown = decide_route(pred_unknown, ctx, policy)
    assert dec_unknown.action == "manual_fallback"
    assert "invalid_model_output" in dec_unknown.reason_codes

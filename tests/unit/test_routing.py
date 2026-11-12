import math
import pytest
from apps.core_backend.intent.schemas import IntentPrediction, IntentPolicy, RouteDecision, RoutingContext
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
        pred = IntentPrediction(intent=intent, confidence=0.95, margin=0.5, model_version="v2.0.0")
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
    pred_human = IntentPrediction(intent="human_agent", confidence=0.90, margin=0.5, model_version="v2.0.0")
    ctx_human = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")
    dec_human = decide_route(pred_human, ctx_human, policy)
    assert dec_human.action == "escalate"
    assert dec_human.requested_team == "general_support"

    # 2. General queries (e.g. delivery_time, return_policy, refund_policy) don't require order_id
    pred_deliv = IntentPrediction(intent="delivery_time", confidence=0.90, margin=0.5, model_version="v2.0.0")
    dec_deliv = decide_route(pred_deliv, ctx_human, policy)
    assert dec_deliv.action == "retrieve_draft"

    # 3. Personal order queries require order_id slot; missing -> clarify
    pred_track = IntentPrediction(intent="track_order", confidence=0.90, margin=0.5, model_version="v2.0.0")
    ctx_personal = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        is_personal_lookup=True
    )
    dec_track_no_slot = decide_route(pred_track, ctx_personal, policy)
    assert dec_track_no_slot.action == "clarify"
    assert "missing_order_id" in dec_track_no_slot.reason_codes

    # With order_id slot -> retrieve_draft
    ctx_with_slot = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        is_personal_lookup=True,
        extracted_slots={"order_id": "ORD-123"}
    )
    dec_track_with_slot = decide_route(pred_track, ctx_with_slot, policy)
    assert dec_track_with_slot.action == "retrieve_draft"


def test_general_inquiry_does_not_require_order_id():
    """General inquiry on return_product or cancel_order without personal lookup does not force order_id."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="return_product", confidence=0.92, margin=0.5, model_version="v2.0.0")
    ctx_general = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        is_personal_lookup=False
    )
    decision = decide_route(pred, ctx_general, policy)
    assert decision.action == "retrieve_draft"
    assert decision.missing_slots == []


def test_unapproved_policy_fails_closed():
    """Policy without approval must fail-closed to manual_fallback / human review."""
    policy = load_policy_v2()
    policy.approved = False
    pred = IntentPrediction(intent="return_policy", confidence=0.95, margin=0.5, model_version="v2.0.0")
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "manual_fallback"
    assert "policy_not_approved" in decision.reason_codes


def test_override_requires_provenance_and_scope():
    """Override without intent:override scope or without provenance is ignored."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="close_account", confidence=0.95, margin=0.5, model_version="v2.0.0")

    # Unauthorized scope trying to override to return_policy
    ctx_unauth = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        intent_override="return_policy",
        override_provenance={"actor_id": "user1", "reason": "test"}
    )
    dec_unauth = decide_route(pred, ctx_unauth, policy)
    assert dec_unauth.action == "escalate"
    assert dec_unauth.final_intent == "close_account"

    # Authorized scope with valid provenance applies override
    ctx_auth = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_123",
        intent_override="return_policy",
        override_provenance={"actor_id": "supervisor_1", "reason": "customer misclassified by model"}
    )
    dec_auth = decide_route(pred, ctx_auth, policy)
    assert dec_auth.action == "retrieve_draft"
    assert dec_auth.final_intent == "return_policy"


def test_low_confidence_sensitive_cannot_bypass():
    """Confidence and margin must be checked before sensitive/slot processing."""
    policy = load_policy_v2()
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
    pred = IntentPrediction(intent="track_order", confidence=0.95, margin=0.5, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read",
        ticket_customer_id="cust_123",
        is_explicit_human_request=True
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "escalate"
    assert "explicit_human_request" in decision.reason_codes
    assert decision.requested_team == "general_support"


def test_invalid_or_failed_model_output_and_margin():
    """NaN, infinite margin/confidence, or ml errors route to manual_fallback."""
    policy = load_policy_v2()
    ctx = RoutingContext(verified_scope="ticket:read", ticket_customer_id="cust_123")

    # Invalid margin
    pred_nan_margin = IntentPrediction(intent="track_order", confidence=0.90, margin=math.nan, model_version="v2.0.0")
    dec_nan_margin = decide_route(pred_nan_margin, ctx, policy)
    assert dec_nan_margin.action == "manual_fallback"
    assert "invalid_model_output" in dec_nan_margin.reason_codes

    pred_inf_margin = IntentPrediction(intent="track_order", confidence=0.90, margin=math.inf, model_version="v2.0.0")
    dec_inf_margin = decide_route(pred_inf_margin, ctx, policy)
    assert dec_inf_margin.action == "manual_fallback"
    assert "invalid_model_output" in dec_inf_margin.reason_codes


def test_sticky_manager_authority_retained_on_override():
    """Overriding sensitive predicted intent (request_refund) to non-sensitive (track_order) retains manager queue & authority."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="request_refund", confidence=0.95, margin=0.5, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_123",
        intent_override="track_order",
        override_provenance={"actor_id": "supervisor_1", "reason": "corrected intent"},
        extracted_slots={"order_id": "ORD-999"},
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "retrieve_draft"
    assert decision.final_intent == "track_order"
    assert decision.target_queue == "manager"
    assert "requires_authority" in decision.reason_codes


def test_sensitive_override_activates_manager_authority():
    """Overriding non-sensitive predicted intent (track_order) to sensitive (cancel_order) activates manager queue & authority."""
    policy = load_policy_v2()
    pred = IntentPrediction(intent="track_order", confidence=0.95, margin=0.5, model_version="v2.0.0")
    ctx = RoutingContext(
        verified_scope="ticket:read intent:override",
        ticket_customer_id="cust_123",
        intent_override="cancel_order",
        override_provenance={"actor_id": "supervisor_1", "reason": "customer wants cancellation"},
        extracted_slots={"order_id": "ORD-999"},
    )
    decision = decide_route(pred, ctx, policy)
    assert decision.action == "retrieve_draft"
    assert decision.final_intent == "cancel_order"
    assert decision.target_queue == "manager"
    assert "requires_authority" in decision.reason_codes


"""Gate 2d: multiple requests (docs/design/multi-request-detection.md)."""
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.schemas import ClausePrediction, IntentPrediction, MultiRequestPolicy, RoutingContext


def _policy(enabled=True):
    policy = load_policy_v2()
    policy.multi_request = MultiRequestPolicy(enabled=enabled, min_clause_confidence=0.6)
    return policy


def _pred(intent, clauses, confidence=0.95):
    return IntentPrediction(intent=intent, confidence=confidence, margin=0.9, model_version="v1.1.0",
                            clauses=[ClausePrediction(intent=i, confidence=c) for i, c in clauses])


def _ctx(**kw):
    return RoutingContext(ticket_customer_id="c1", **kw)


def test_two_supported_requests_are_clarified_once_then_escalated():
    pred = _pred("refund_policy", [("refund_policy", 0.9), ("shipping_costs", 0.8)])
    first = decide_route(pred, _ctx(), _policy())
    assert first.action == "clarify" and first.reason_codes == ["multiple_requests"]
    assert first.clause_intents == ["refund_policy", "shipping_costs"]
    second = decide_route(pred, _ctx(clarify_count=1), _policy())
    assert second.action == "escalate"
    assert second.reason_codes == ["multiple_requests", "max_clarify_reached"]


def test_authority_or_out_of_scope_clause_escalates_to_its_team():
    pred = _pred("track_order", [("track_order", 0.9), ("cancel_order", 0.85)])
    d = decide_route(pred, _ctx(), _policy())
    assert d.action == "escalate" and d.requested_team == "order_support" and d.target_queue == "manager"
    pred = _pred("refund_policy", [("refund_policy", 0.9), ("store_location", 0.9)])
    d = decide_route(pred, _ctx(), _policy())
    assert d.action == "escalate" and d.requested_team == "store_support"


def test_same_intent_or_low_confidence_clauses_do_not_trigger():
    same = _pred("delivery_time", [("delivery_time", 0.9), ("delivery_time", 0.7)])
    assert "multiple_requests" not in decide_route(same, _ctx(), _policy()).reason_codes
    weak = _pred("delivery_time", [("delivery_time", 0.9), ("shipping_costs", 0.4)])
    assert decide_route(weak, _ctx(), _policy()).action == "retrieve_draft"


def test_gate_is_off_without_policy_block_or_when_disabled():
    pred = _pred("refund_policy", [("refund_policy", 0.9), ("shipping_costs", 0.8)])
    no_block = load_policy_v2()
    assert no_block.multi_request is None
    assert decide_route(pred, _ctx(), no_block).action == "retrieve_draft"
    assert decide_route(pred, _ctx(), _policy(enabled=False)).action == "retrieve_draft"


def test_whole_message_escalation_is_unchanged():
    pred = _pred("store_location", [("refund_policy", 0.9), ("shipping_costs", 0.8)])
    d = decide_route(pred, _ctx(), _policy())
    assert d.action == "escalate" and d.reason_codes == ["recognized_outside_product_scope"]


def test_invalid_clause_fails_closed():
    pred = _pred("refund_policy", [("refund_policy", 0.9), ("not_a_label", 0.8)])
    assert decide_route(pred, _ctx(), _policy()).action == "manual_fallback"
    pred = _pred("refund_policy", [("refund_policy", 0.9), ("shipping_costs", float("nan"))])
    assert decide_route(pred, _ctx(), _policy()).action == "manual_fallback"

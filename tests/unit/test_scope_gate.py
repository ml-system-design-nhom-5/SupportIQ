"""Gate 2f: scope probability (docs/design/intent-model-v1.2.md)."""
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext


def _policy(min_scope=0.8):
    policy = load_policy_v2()
    policy.min_scope_probability = min_scope
    return policy


def _pred(intent="return_policy", scope=0.5):
    return IntentPrediction(intent=intent, confidence=0.97, margin=0.9, model_version="v1.2.0", scope_probability=scope)


def test_low_scope_clarifies_once_then_escalates():
    first = decide_route(_pred(), RoutingContext(ticket_customer_id="c"), _policy())
    assert first.action == "clarify" and first.reason_codes == ["low_scope_probability"]
    second = decide_route(_pred(), RoutingContext(ticket_customer_id="c", clarify_count=1), _policy())
    assert second.action == "escalate" and second.reason_codes == ["low_scope_probability", "max_clarify_reached"]


def test_high_scope_or_gate_off_or_missing_scope_drafts():
    ctx = RoutingContext(ticket_customer_id="c")
    assert decide_route(_pred(scope=0.95), ctx, _policy()).action == "retrieve_draft"
    assert decide_route(_pred(), ctx, _policy(None)).action == "retrieve_draft"
    assert decide_route(_pred(scope=None), ctx, _policy()).action == "retrieve_draft"
    assert decide_route(_pred(scope=float("nan")), ctx, _policy()).action == "retrieve_draft"


def test_escalated_intents_and_human_agent_are_unchanged():
    ctx = RoutingContext(ticket_customer_id="c")
    assert decide_route(_pred("store_location"), ctx, _policy()).reason_codes == ["recognized_outside_product_scope"]
    assert decide_route(_pred("human_agent"), ctx, _policy()).reason_codes == ["human_agent_requested"]

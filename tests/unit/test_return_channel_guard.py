"""Gate 2e: return channel named (docs/design/return-channel-guard.md, label definitions D2)."""
import pytest

from apps.core_backend.intent.channels import names_return_channel
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext


@pytest.mark.parametrize("text", [
    "Can I return the jeans at your shop?", "I want to hand it in at a branch", "Return it at the store counter",
    "I'll mail it back", "Can a courier pick up my return?", "Will someone collect the parcel?",
    "I'd like to post the lamp back", "Use the website return form", "Can I return it online?",
    "Could I walk in and give it back in person?",
])
def test_channel_cues(text):
    assert names_return_channel(text)


@pytest.mark.parametrize("text", [
    "I want to return the sweater", "Can I get store credit instead of a refund?", "It is in the app store",
    "How do I start a return for [ORDER_ID]?", "Please send back my deposit", "",
])
def test_no_channel(text):
    assert not names_return_channel(text)


def _policy(guard=True):
    policy = load_policy_v2()
    policy.return_channel_guard = guard
    return policy


def _pred(intent):
    return IntentPrediction(intent=intent, confidence=0.97, margin=0.9, model_version="v1.1.0")


@pytest.mark.parametrize("intent", ["return_product", "return_policy"])
def test_return_family_with_channel_escalates_to_returns(intent):
    d = decide_route(_pred(intent), RoutingContext(ticket_customer_id="c", return_channel_named=True), _policy())
    assert d.action == "escalate" and d.requested_team == "returns_support"
    assert d.reason_codes == ["return_channel_named"] and d.final_intent == intent


def test_other_intents_and_no_channel_are_unchanged():
    ctx = RoutingContext(ticket_customer_id="c", return_channel_named=True)
    assert decide_route(_pred("shipping_costs"), ctx, _policy()).action == "retrieve_draft"
    plain = RoutingContext(ticket_customer_id="c")
    assert decide_route(_pred("return_policy"), plain, _policy()).action == "retrieve_draft"


def test_guard_off_by_default_and_skipped_on_override():
    ctx = RoutingContext(ticket_customer_id="c", return_channel_named=True)
    assert load_policy_v2().return_channel_guard is False
    assert decide_route(_pred("return_policy"), ctx, load_policy_v2()).action == "retrieve_draft"
    override = RoutingContext(ticket_customer_id="c", return_channel_named=True, intent_override="return_policy",
                              verified_scope="ticket:read intent:override",
                              override_provenance={"actor_id": "s1", "reason": "staff checked"})
    assert decide_route(_pred("return_policy"), override, _policy()).action == "retrieve_draft"

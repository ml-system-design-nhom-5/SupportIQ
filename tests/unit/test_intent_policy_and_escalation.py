import math
import pytest
from apps.core_backend.intent.schemas import IntentPrediction, IntentPolicy
from apps.core_backend.intent.routing import (
    load_policy_v2,
    decide_route,
    RoutingContext,
)

def test_46_labels_contract_and_12_supported_intents():
    policy: IntentPolicy = load_policy_v2()
    assert len(policy.all_46_labels) == 46
    assert len(policy.supported_12_intents) == 12

    # Out-of-scope Bitext label (e.g., 'create_account' or other 34 intent) -> recognized_outside_product_scope / escalate
    pred_oos = IntentPrediction(intent="close_account", confidence=0.96, margin=0.5, model_version="v1.0.0")
    ctx = RoutingContext(ticket_customer_id="cust_1")
    dec_oos = decide_route(pred_oos, ctx, policy)
    assert dec_oos.action == "escalate"
    assert "recognized_outside_product_scope" in dec_oos.reason_codes

    # Unknown label outside 46 labels -> invalid_model_output
    pred_bad = IntentPrediction(intent="invented_label", confidence=0.90, margin=0.5, model_version="v1.0.0")
    dec_bad = decide_route(pred_bad, ctx, policy)
    assert dec_bad.action == "manual_fallback"
    assert "invalid_model_output" in dec_bad.reason_codes

    # Sensitive action intent ('request_refund') -> routes to manager queue with sensitive action
    pred_refund = IntentPrediction(intent="request_refund", confidence=0.94, margin=0.5, model_version="v1.0.0")
    ctx_refund = RoutingContext(ticket_customer_id="cust_1", extracted_slots={"order_id": "ORD-123"}, is_personal_lookup=True)
    dec_refund = decide_route(pred_refund, ctx_refund, policy)
    assert dec_refund.target_queue == "manager"

    # NaN confidence -> invalid_model_output
    pred_nan = IntentPrediction(intent="track_order", confidence=math.nan, model_version="v1.0.0")
    dec_nan = decide_route(pred_nan, ctx, policy)
    assert "invalid_model_output" in dec_nan.reason_codes

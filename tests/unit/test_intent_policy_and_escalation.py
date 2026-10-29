import math
import pytest
from src.modules.intent.schemas import IntentPrediction, IntentPolicy
from src.modules.escalation.service import evaluate_intent_gates, load_policy

def test_46_labels_contract_and_12_supported_intents():
    policy: IntentPolicy = load_policy("apps/core-backend/config/policies/intent_policy.v1.json")
    assert len(policy.all_46_labels) == 46
    assert len(policy.supported_12_intents) == 12

    # Out-of-scope Bitext label (e.g., 'create_account') -> unsupported_intent
    pred_oos = IntentPrediction(intent="create_account", confidence=0.96, model_version="v1.0.0")
    gate_oos = evaluate_intent_gates(pred_oos, intent_override=None, policy=policy)
    assert gate_oos.allowed is False
    assert "unsupported_intent" in gate_oos.reason_codes

    # Unknown label outside 46 labels -> invalid_model_output
    pred_bad = IntentPrediction(intent="invented_label", confidence=0.90, model_version="v1.0.0")
    gate_bad = evaluate_intent_gates(pred_bad, intent_override=None, policy=policy)
    assert gate_bad.allowed is False
    assert "invalid_model_output" in gate_bad.reason_codes

    # Sensitive action intent ('request_refund') -> routes to manager queue with sensitive_request
    pred_refund = IntentPrediction(intent="request_refund", confidence=0.94, model_version="v1.0.0")
    gate_refund = evaluate_intent_gates(pred_refund, intent_override=None, policy=policy)
    assert gate_refund.target_queue == "manager"
    assert "sensitive_request" in gate_refund.reason_codes

    # NaN confidence -> invalid_model_output
    pred_nan = IntentPrediction(intent="track_order", confidence=math.nan, model_version="v1.0.0")
    gate_nan = evaluate_intent_gates(pred_nan, intent_override=None, policy=policy)
    assert "invalid_model_output" in gate_nan.reason_codes

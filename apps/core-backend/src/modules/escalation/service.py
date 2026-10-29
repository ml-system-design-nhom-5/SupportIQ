import json
import math
from pathlib import Path
from src.modules.intent.schemas import IntentPrediction, IntentPolicy, GateDecision

def load_policy(policy_path: str) -> IntentPolicy:
    p = Path(policy_path)
    if not p.exists():
        # Fallback to relative from project root
        p = Path(__file__).resolve().parent.parent.parent.parent / policy_path
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    return IntentPolicy(**data)

def evaluate_intent_gates(
    prediction: IntentPrediction,
    intent_override: str | None,
    policy: IntentPolicy,
) -> GateDecision:
    intent = intent_override or prediction.intent

    # Check for NaN / invalid confidence values
    if math.isnan(prediction.confidence) or prediction.confidence < 0.0 or prediction.confidence > 1.0:
        return GateDecision(
            allowed=False,
            final_intent="unknown",
            target_queue="standard",
            reason_codes=["invalid_model_output"],
        )

    # Check if recognized by 46 labels
    if intent not in policy.all_46_labels:
        return GateDecision(
            allowed=False,
            final_intent="unknown",
            target_queue="standard",
            reason_codes=["invalid_model_output"],
        )

    # Check if supported by product (12 supported intents)
    if intent not in policy.supported_12_intents:
        return GateDecision(
            allowed=False,
            final_intent=intent,
            target_queue="standard",
            reason_codes=["unsupported_intent"],
        )

    # Check sensitivity
    if intent in policy.sensitive_action_intents:
        return GateDecision(
            allowed=True,
            final_intent=intent,
            target_queue="manager",
            reason_codes=["sensitive_request"],
        )

    # Check confidence threshold
    threshold = policy.confidence_thresholds.get(intent, policy.default_confidence_threshold)
    if prediction.confidence < threshold:
        return GateDecision(
            allowed=False,
            final_intent=intent,
            target_queue="standard",
            reason_codes=["low_confidence"],
        )

    return GateDecision(
        allowed=True,
        final_intent=intent,
        target_queue="standard",
        reason_codes=[],
    )

from typing import Literal
from pydantic import BaseModel

class IntentPrediction(BaseModel):
    intent: str
    confidence: float
    model_version: str

class IntentPolicy(BaseModel):
    version: str
    supported_12_intents: list[str]
    sensitive_action_intents: list[str]
    default_confidence_threshold: float
    confidence_thresholds: dict[str, float]
    all_46_labels: list[str]

class GateDecision(BaseModel):
    allowed: bool
    final_intent: str
    target_queue: Literal["standard", "manager"]
    reason_codes: list[str]

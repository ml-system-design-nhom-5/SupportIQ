import math
from datetime import datetime
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field, StrictBool, ValidationInfo, field_validator


def _validate_numeric_not_bool(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric, got {value!r}")
    return float(value)


def _validate_finite_float(
    value: Any,
    field_name: str,
    *,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    strictly_positive: bool = False,
) -> Optional[float]:
    if value is None:
        return None
    num = _validate_numeric_not_bool(value, field_name)
    if not math.isfinite(num):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    if strictly_positive and num <= 0.0:
        raise ValueError(f"{field_name} must be > 0.0, got {num!r}")
    if min_value is not None and num < min_value:
        raise ValueError(f"{field_name} must be >= {min_value}, got {num!r}")
    if max_value is not None and num > max_value:
        raise ValueError(f"{field_name} must be <= {max_value}, got {num!r}")
    return num


class IntentPrediction(BaseModel):
    intent: str
    confidence: float
    model_version: str
    margin: Optional[float] = None
    top_k: Optional[List[Dict[str, Any]]] = None
    score_kind: Optional[str] = "uncalibrated_softmax"
    request_id: Optional[str] = None
    model_checksum: Optional[str] = None
    tokenizer_checksum: Optional[str] = None
    model_mode: Optional[str] = None
    verified: Optional[StrictBool] = None
    raw_confidence: Optional[float] = None
    raw_margin: Optional[float] = None
    raw_score_kind: Optional[str] = None
    calibration_temperature: Optional[float] = None
    calibration_schema_version: Optional[str] = None
    calibration_checksum: Optional[str] = None
    selective_accepted: Optional[StrictBool] = None
    selective_score: Optional[float] = None
    selective_threshold: Optional[float] = None
    rejected_by_experimental_adapter: Optional[StrictBool] = None
    rejector_decision: Optional[str] = None
    error: Optional[str] = None
    failure_code: Optional[Literal["ml_timeout", "ml_error", "ml_unavailable", "invalid_model_output"]] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence_type(cls, value: Any) -> float:
        return _validate_numeric_not_bool(value, "confidence")

    @field_validator("margin", mode="before")
    @classmethod
    def _validate_margin_type(cls, value: Any) -> Optional[float]:
        if value is None:
            return None
        return _validate_numeric_not_bool(value, "margin")

    @field_validator("raw_confidence", "selective_score", "selective_threshold", mode="before")
    @classmethod
    def _validate_unit_interval_score(cls, value: Any, info: ValidationInfo) -> Optional[float]:
        return _validate_finite_float(value, info.field_name, min_value=0.0, max_value=1.0)

    @field_validator("raw_margin", mode="before")
    @classmethod
    def _validate_raw_margin_range(cls, value: Any) -> Optional[float]:
        return _validate_finite_float(value, "raw_margin", min_value=-1.0, max_value=1.0)

    @field_validator("calibration_temperature", mode="before")
    @classmethod
    def _validate_calibration_temperature(cls, value: Any) -> Optional[float]:
        return _validate_finite_float(value, "calibration_temperature", strictly_positive=True)

    @field_validator("rejector_decision", mode="before")
    @classmethod
    def _validate_rejector_decision(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str) or value.lower() not in {"accept", "reject"}:
            raise ValueError(f"rejector_decision must be 'accept' or 'reject', got {value!r}")
        return value

class RoutingContext(BaseModel):
    verified_scope: str = "ticket:read"
    ticket_customer_id: str
    is_explicit_human_request: bool = False
    is_human_agent_requested: bool = False
    is_personal_lookup: bool = False  # Differentiates general policy vs personal order inquiry
    extracted_slots: Dict[str, Any] = Field(default_factory=dict)
    clarify_count: int = 0
    intent_override: Optional[str] = None
    override_provenance: Optional[Dict[str, Any]] = None
    role: str = "agent"
    as_of: Optional[datetime] = None

class RouteDecision(BaseModel):
    decision_id: Optional[str] = None
    action: Literal["retrieve_draft", "clarify", "escalate", "manual_fallback"]
    predicted_intent: str
    final_intent: str
    requested_team: str
    target_queue: Literal["standard", "manager"] = "standard"
    reason_codes: List[str] = Field(default_factory=list)
    required_slots: List[str] = Field(default_factory=list)
    missing_slots: List[str] = Field(default_factory=list)
    must_human_approve: bool = True
    can_execute_transaction: bool = False
    model_version: Optional[str] = None
    policy_version: Optional[str] = None

class IntentPolicy(BaseModel):
    version: str
    approved: bool = False
    approved_by: Optional[str] = None
    approval_date: Optional[str] = None
    supported_12_intents: List[str]
    sensitive_action_intents: List[str]
    default_confidence_threshold: float
    confidence_thresholds: Dict[str, float]
    all_46_labels: List[str]
    default_margin_threshold: float = 0.10
    margin_thresholds: Dict[str, float] = Field(default_factory=dict)
    team_mapping: Dict[str, str] = Field(default_factory=dict)

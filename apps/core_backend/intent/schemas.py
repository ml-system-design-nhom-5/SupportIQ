from datetime import datetime
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ClausePrediction(BaseModel):
    intent: str
    confidence: float

class IntentPrediction(BaseModel):
    intent: str
    confidence: float
    model_version: str
    margin: Optional[float] = None
    top_k: Optional[List[Dict[str, Any]]] = None
    score_kind: Optional[str] = "uncalibrated_softmax"
    error: Optional[str] = None
    clauses: Optional[List[ClausePrediction]] = None  # multi-request detection; None = not computed
    scope_probability: Optional[float] = None  # P(draftable request); None = not provided

class RoutingContext(BaseModel):
    verified_scope: str = "ticket:read"
    ticket_customer_id: str
    is_explicit_human_request: bool = False
    is_human_agent_requested: bool = False
    is_personal_lookup: bool = False  # Differentiates general policy vs personal order inquiry
    extracted_slots: Dict[str, Any] = Field(default_factory=dict)
    clarify_count: int = 0
    return_channel_named: bool = False  # set from the message text (docs/design/return-channel-guard.md)
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
    clause_intents: List[str] = Field(default_factory=list)  # set only with reason multiple_requests

class MultiRequestPolicy(BaseModel):
    """Gate 2d settings (docs/design/multi-request-detection.md); tuned on dev data only (DATA-58)."""
    enabled: bool = True
    min_clause_confidence: float = Field(ge=0.0, le=1.0)
    min_words: int = Field(default=3, ge=1, le=20)
    max_clauses: int = Field(default=4, ge=2, le=4)
    request_clauses_only: bool = False  # keep only request clauses unless an additive cue is present

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
    multi_request: Optional[MultiRequestPolicy] = None
    return_channel_guard: bool = False
    min_scope_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)  # gate 2f; None = off

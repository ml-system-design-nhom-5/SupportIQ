import logging
import uuid
from typing import Optional, Dict, Any

from apps.core_backend.intent.schemas import RoutingContext, RouteDecision, IntentPolicy
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.client import IntentClient

logger = logging.getLogger("pipeline_runner")

# Mock commerce store for order ownership checking
ORDERS_DB = {
    "ORD-123": {"customer_id": "cust_1", "status": "in_transit"},
    "ORD_OTHER": {"customer_id": "cust_999", "status": "delivered"},
}

class PipelineRunner:
    def __init__(self, intent_client: Optional[Any] = None, policy: Optional[IntentPolicy] = None):
        self.intent_client = intent_client or IntentClient()
        self.policy = policy or load_policy_v2()
        self.processed_runs: Dict[str, Dict[str, Any]] = {}

    def run(
        self,
        text: str,
        context: RoutingContext,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute intake routing, scope checks, and idempotency tracking."""
        actual_run_id = run_id or str(uuid.uuid4())

        # Check idempotency
        if actual_run_id in self.processed_runs:
            existing = self.processed_runs[actual_run_id].copy()
            existing["is_duplicate_run"] = True
            return existing

        # 1. Intent classification
        prediction = self.intent_client.classify_intent(text, request_id=actual_run_id)

        # 2. Gate routing decision
        decision: RouteDecision = decide_route(prediction, context, self.policy)
        decision.decision_id = str(uuid.uuid4())

        # 3. Scope validation for commerce lookup if slot order_id is present
        order_id = context.extracted_slots.get("order_id")
        if order_id and decision.action in ["retrieve_draft", "clarify"]:
            order = ORDERS_DB.get(order_id)
            if not order or order["customer_id"] != context.ticket_customer_id:
                # Unauthorized order access or customer mismatch -> escalate immediately
                decision.action = "escalate"
                decision.reason_codes.append("unauthorized_order_scope")
                decision.requested_team = "order_support"

        # Construct result payload
        result = {
            "run_id": actual_run_id,
            "decision_id": decision.decision_id,
            "action": decision.action,
            "predicted_intent": decision.predicted_intent,
            "final_intent": decision.final_intent,
            "requested_team": decision.requested_team,
            "target_queue": decision.target_queue,
            "reason_codes": decision.reason_codes,
            "must_human_approve": decision.must_human_approve,
            "can_execute_transaction": decision.can_execute_transaction,
            "model_version": decision.model_version,
            "policy_version": decision.policy_version,
            "is_duplicate_run": False,
            "llm_called": False, # Escalated and clarified tickets never trigger unnecessary LLM generation
        }

        # If action is retrieve_draft, LLM draft generator would be called here after evidence retrieval
        if decision.action == "retrieve_draft":
            result["evidence_retrieved"] = True
            # In full pipeline, LLM generates draft here with human review required

        self.processed_runs[actual_run_id] = result
        return result

import logging
import uuid
from typing import Optional, Dict, Any

from apps.core_backend.intent.schemas import RoutingContext, RouteDecision, IntentPolicy
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.orchestration.store import PersistentStore

logger = logging.getLogger("pipeline_runner")

class PipelineRunner:
    def __init__(
        self,
        intent_client: Optional[Any] = None,
        policy: Optional[IntentPolicy] = None,
        commerce_adapter: Optional[CommerceAdapter] = None,
        retrieval_adapter: Optional[RetrievalAdapter] = None,
        store: Optional[PersistentStore] = None,
    ):
        self.intent_client = intent_client or IntentClient()
        self.policy = policy or load_policy_v2()
        self.commerce = commerce_adapter or CommerceAdapter()
        self.retrieval = retrieval_adapter or RetrievalAdapter()
        self.store = store or PersistentStore()

    def run(
        self,
        text: str,
        context: RoutingContext,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute intake routing, scope checks, retrieval, draft generation, and persistent escalation."""
        actual_run_id = run_id or str(uuid.uuid4())

        # 1. Fast check if run is already stored
        existing_run = self.store.get_run(actual_run_id)
        if existing_run:
            dup = existing_run.copy()
            dup["is_duplicate_run"] = True
            return dup

        # 2. Intent classification
        prediction = self.intent_client.classify_intent(text, request_id=actual_run_id)

        # 3. Gate routing decision
        decision: RouteDecision = decide_route(prediction, context, self.policy)
        decision.decision_id = str(uuid.uuid4())

        # 4. Commerce authorization and lookup if slot order_id is present
        order_id = context.extracted_slots.get("order_id")
        if order_id and decision.action in ["retrieve_draft", "clarify"]:
            commerce_result = self.commerce.lookup_order(
                order_id=order_id,
                ticket_customer_id=context.ticket_customer_id,
                verified_scope=context.verified_scope
            )
            if not commerce_result["authorized"]:
                decision.action = "escalate"
                decision.reason_codes.append(f"commerce_{commerce_result['error']}")
                decision.requested_team = "order_support"

        # 5. Handling retrieval & drafting ONLY when action is retrieve_draft
        evidence_retrieved = False
        draft_response = None
        evidence_list = []

        if decision.action == "retrieve_draft":
            ret_res = self.retrieval.retrieve(text, decision.final_intent)
            if ret_res["status"] == "success" and ret_res["evidence"]:
                evidence_retrieved = True
                evidence_list = ret_res["evidence"]
                draft_response = f"Thank you for contacting us regarding {decision.final_intent}. Based on policy: {evidence_list[0]['title']}."
            else:
                # Evidence missing, stale, or conflicting -> Escalate according to spec Gate 7
                decision.action = "escalate"
                decision.reason_codes.append("insufficient_evidence")

        # 6. Prepare escalation info if action is escalate
        escalate_info = None
        if decision.action == "escalate":
            escalate_info = {
                "decision_id": decision.decision_id,
                "target_team": decision.requested_team,
                "target_queue": decision.target_queue,
                "reason_codes": decision.reason_codes,
            }

        # 7. Construct result
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
            "evidence_retrieved": evidence_retrieved,
            "evidence_count": len(evidence_list),
            "draft_body": draft_response,
            "is_duplicate_run": False,
            "llm_called": evidence_retrieved,
        }

        # 8. Atomically save run and enqueue escalation
        saved = self.store.save_run_and_escalate_atomic(
            run_id=actual_run_id,
            result=result,
            escalate_info=escalate_info
        )
        if not saved:
            # Another concurrent runner saved this run first; fetch and return existing
            concurrent_run = self.store.get_run(actual_run_id)
            if concurrent_run:
                dup = concurrent_run.copy()
                dup["is_duplicate_run"] = True
                return dup

        return result

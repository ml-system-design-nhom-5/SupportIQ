import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Sequence

from apps.core_backend.intent.schemas import RoutingContext, RouteDecision, IntentPolicy
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError, prepare_llm_input
from apps.core_backend.safety import (
    classify_ml_prediction_fault,
    classify_retrieval_fault,
    evaluate_evidence_scope,
    evaluate_text_safety,
    validate_generated_draft,
)

logger = logging.getLogger("pipeline_runner")


def _append_reason_codes(decision: RouteDecision, codes: Sequence[str]) -> None:
    for code in codes:
        if code not in decision.reason_codes:
            decision.reason_codes.append(code)

class PipelineRunner:
    def __init__(
        self,
        intent_client: Optional[Any] = None,
        policy: Optional[IntentPolicy] = None,
        commerce_adapter: Optional[CommerceAdapter] = None,
        retrieval_adapter: Optional[RetrievalAdapter] = None,
        store: Optional[PersistentStore] = None,
        llm_client: Optional[Any] = None,
        clock: Optional[Any] = None,
        observer: Optional[Any] = None,
    ):
        self.intent_client = intent_client or IntentClient()
        self.policy = policy or load_policy_v2()
        self.commerce = commerce_adapter or CommerceAdapter()
        self.retrieval = retrieval_adapter or RetrievalAdapter()
        self.store = store or PersistentStore()
        self.llm_client = llm_client if llm_client is not None else GeminiDraftClient()
        self.clock = clock
        self.observer = observer

    def run(
        self,
        text: str,
        context: RoutingContext,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute intake routing, scope checks, retrieval, draft generation, and persistent escalation."""
        t_start = time.perf_counter()
        actual_run_id = run_id or str(uuid.uuid4())
        stage_elapsed_ms: Dict[str, float] = {}

        now = (self.clock() if callable(self.clock) else self.clock) or getattr(context, "as_of", None) or datetime.now(timezone.utc)
        caller_role = getattr(context, "role", "agent") or "agent"

        # 1. Fast check if run is already stored
        existing_run = self.store.get_run(actual_run_id)
        if existing_run:
            dup = existing_run.copy()
            dup["is_duplicate_run"] = True
            return dup

        # 2. Intent classification
        t_classify = time.perf_counter()
        prediction = self.intent_client.classify_intent(text, request_id=actual_run_id)
        stage_elapsed_ms["classify_ms"] = round((time.perf_counter() - t_classify) * 1000.0, 2)

        # 3. Gate routing decision
        t_route = time.perf_counter()
        decision: RouteDecision = decide_route(prediction, context, self.policy)
        decision.decision_id = str(uuid.uuid4())
        ml_fault_codes = classify_ml_prediction_fault(prediction)
        if ml_fault_codes:
            _append_reason_codes(decision, ml_fault_codes)
        initial_routing_action = decision.action
        stage_elapsed_ms["route_ms"] = round((time.perf_counter() - t_route) * 1000.0, 2)

        # 4. Commerce authorization and lookup if slot order_id is present
        order_id = context.extracted_slots.get("order_id")
        order_facts = None
        if order_id and decision.action in ["retrieve_draft", "clarify"]:
            t_comm = time.perf_counter()
            commerce_result = self.commerce.lookup_order(
                order_id=order_id,
                ticket_customer_id=context.ticket_customer_id,
                verified_scope=context.verified_scope
            )
            stage_elapsed_ms["commerce_ms"] = round((time.perf_counter() - t_comm) * 1000.0, 2)
            if not commerce_result["authorized"]:
                decision.action = "escalate"
                decision.reason_codes.append(f"commerce_{commerce_result['error']}")
                decision.requested_team = "order_support"
            else:
                order_facts = commerce_result.get("order")

        # 4b. Pre-generation shared text safety guard (blocks clarify & abstention bypass, preserves commerce denial)
        text_safety = evaluate_text_safety(text)
        if text_safety["action"] == "escalate":
            decision.action = "escalate"
            _append_reason_codes(decision, text_safety["reason_codes"])
            if text_safety["target_queue"]:
                decision.target_queue = text_safety["target_queue"]
            if text_safety["human_agent_requested"] and not text_safety["requires_authority"]:
                if not any(code.startswith("commerce_") for code in decision.reason_codes):
                    decision.requested_team = text_safety["requested_team"] or decision.requested_team
            elif text_safety["requested_team"] and not decision.requested_team:
                decision.requested_team = text_safety["requested_team"]
        elif text_safety["action"] == "manual_fallback" and decision.action in ("retrieve_draft", "clarify"):
            decision.action = "manual_fallback"
            _append_reason_codes(decision, text_safety["reason_codes"])

        # 5. Handling retrieval & drafting ONLY when action is retrieve_draft
        evidence_retrieved = False
        draft_response = None
        evidence_list = []
        llm_called = False
        llm_result = None
        draft_kind = None
        llm_input_snapshot = None
        grounding_provenance = None

        if decision.action == "retrieve_draft":
            t_ret = time.perf_counter()
            ret_res = self.retrieval.retrieve(text, decision.final_intent, role=caller_role, current_time=now)
            stage_elapsed_ms["retrieval_ms"] = round((time.perf_counter() - t_ret) * 1000.0, 2)
            if ret_res["status"] == "success" and ret_res["evidence"]:
                ev_guard = evaluate_evidence_scope(
                    text,
                    ret_res,
                    ret_res["evidence"],
                    getattr(self.retrieval, "eligible_versions", None) or (),
                )
                if ev_guard is not None:
                    guard_action, guard_codes = ev_guard
                    decision.action = guard_action
                    _append_reason_codes(decision, guard_codes)
                else:
                    evidence_retrieved = True
                    evidence_list = ret_res["evidence"]
                    llm_input_snapshot = prepare_llm_input(text, decision.final_intent, evidence_list, order_facts)
                    self.store.save_input_snapshot(actual_run_id, llm_input_snapshot)
                    try:
                        llm_called = bool(getattr(self.llm_client, "configured", False))
                        t_llm = time.perf_counter()
                        raw_llm_result = self.llm_client.generate(
                            text,
                            decision.final_intent,
                            evidence_list,
                            business_context=order_facts,
                        )
                        stage_elapsed_ms["llm_ms"] = round((time.perf_counter() - t_llm) * 1000.0, 2)
                        valid_draft, post_codes, provenance = validate_generated_draft(
                            text,
                            raw_llm_result,
                            llm_input_snapshot.get("sources") or [],
                        )
                        if valid_draft:
                            llm_result = raw_llm_result
                            draft_response = llm_result["body"]
                            if llm_result.get("input_snapshot"):
                                evidence_list = llm_result["input_snapshot"]["sources"]
                            draft_kind = "llm"
                            grounding_provenance = provenance
                        else:
                            decision.action = "manual_fallback"
                            _append_reason_codes(decision, post_codes)
                    except LLMError as exc:
                        decision.action = "escalate" if exc.code == "llm_insufficient_evidence" else "manual_fallback"
                        decision.reason_codes.append(exc.code)
            else:
                # Evidence missing, stale, conflicting, or encoder unavailable/failure -> Escalate
                decision.action = "escalate"
                fault_codes = classify_retrieval_fault(ret_res)
                if fault_codes:
                    _append_reason_codes(decision, fault_codes)
                else:
                    ret_status = ret_res.get("status", "insufficient_evidence")
                    _append_reason_codes(decision, ["insufficient_evidence"])
                    if ret_status and ret_status not in ("insufficient_evidence", "success"):
                        _append_reason_codes(decision, [ret_status])
                    for ret_code in (ret_res.get("reason_codes") or []):
                        if ret_code:
                            _append_reason_codes(decision, [ret_code])

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
        total_elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        result = {
            "run_id": actual_run_id,
            "decision_id": decision.decision_id,
            "action": decision.action,
            "initial_routing_action": initial_routing_action,
            "routing_action": initial_routing_action,
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
            "sources": evidence_list,
            "missing_slots": list(getattr(decision, "missing_slots", [])),
            "confidence": getattr(prediction, "confidence", None),
            "margin": getattr(prediction, "margin", None),
            "score_kind": getattr(prediction, "score_kind", None),
            "draft_body": draft_response,
            "draft_kind": draft_kind,
            "llm": {k: v for k, v in llm_result.items() if k != "body"} if llm_result else None,
            "grounding_provenance": grounding_provenance,
            "llm_input_snapshot": llm_input_snapshot,
            "is_duplicate_run": False,
            "llm_called": llm_called,
            "stage_elapsed_ms": stage_elapsed_ms,
            "total_elapsed_ms": total_elapsed_ms,
        }

        # 8. Atomically save run and enqueue escalation
        t_store = time.perf_counter()
        saved = self.store.save_run_and_escalate_atomic(
            run_id=actual_run_id,
            result=result,
            escalate_info=escalate_info
        )
        stage_elapsed_ms["store_ms"] = round((time.perf_counter() - t_store) * 1000.0, 2)
        result["stage_elapsed_ms"] = stage_elapsed_ms

        if not saved:
            # Another concurrent runner saved this run first; fetch and return existing
            concurrent_run = self.store.get_run(actual_run_id)
            if concurrent_run:
                dup = concurrent_run.copy()
                dup["is_duplicate_run"] = True
                return dup

        if self.observer and hasattr(self.observer, "on_run_completed"):
            try:
                self.observer.on_run_completed(result)
            except Exception:
                pass

        return result

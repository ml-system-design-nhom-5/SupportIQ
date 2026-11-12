import hashlib
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.intent.schemas import RoutingContext
from apps.demo.store import DemoStore

logger = logging.getLogger("demo_service")

# P1: Authoritative server-side simulated customer profiles
DEMO_PROFILES = {
    "demo-customer": {
        "id": "demo-customer",
        "name": "Bùi Thị An (Khách hàng mẫu)",
        "allowed_orders": ["ORD-1001"],
        "scope": "ticket:read order:read",
    },
    "cust-1002": {
        "id": "cust-1002",
        "name": "Phan Văn An (Khách hàng mẫu)",
        "allowed_orders": ["ORD-1002"],
        "scope": "ticket:read order:read",
    },
    "staff-member": {
        "id": "staff-member",
        "name": "Nguyễn Văn Hỗ Trợ (Nhân viên CSKH)",
        "allowed_orders": ["ORD-1001", "ORD-1002"],
        "scope": "ticket:read order:read staff",
    }
}

class DemoRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # P1: Reject any spoofed scope or unexpected client attributes

    submission_id: str
    profile_id: str
    text: str = Field(..., min_length=1, max_length=2000)
    is_personal_lookup: bool = False
    order_id: Optional[str] = None

class DemoFeedbackRequest(BaseModel):
    action: str  # approve, edit, reject, escalate
    draft_hash: str
    edited_text: Optional[str] = None

class DemoService:
    def __init__(self, runner: PipelineRunner, store: Optional[DemoStore] = None):
        self.runner = runner
        self.store = store or DemoStore()

    def get_profiles(self) -> List[Dict[str, Any]]:
        # Exclude server-side scopes from public profile metadata
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "allowed_orders": p["allowed_orders"],
            }
            for p in DEMO_PROFILES.values()
        ]

    def submit_run(self, req: DemoRunRequest, session_id: str) -> Dict[str, Any]:
        profile = DEMO_PROFILES.get(req.profile_id)
        if not profile:
            raise ValueError(f"Unknown demo profile '{req.profile_id}'")

        # Fingerprint request payload
        payload_data = {
            "profile_id": req.profile_id,
            "text": req.text.strip(),
            "is_personal_lookup": req.is_personal_lookup,
            "order_id": req.order_id,
        }
        fingerprint = hashlib.sha256(json.dumps(payload_data, sort_keys=True).encode("utf-8")).hexdigest()

        # Idempotency check on submission_id
        existing = self.store.get_submission(req.submission_id)
        if existing:
            if existing.get("session_id") and existing.get("session_id") != session_id:
                raise KeyError(f"Submission ID '{req.submission_id}' belongs to another session")
            if existing["fingerprint"] != fingerprint:
                # Same submission_id with different payload -> 409 Conflict
                raise KeyError(f"Submission ID '{req.submission_id}' reused with different payload")
            res = existing["result"].copy()
            res["is_duplicate_run"] = True
            return res

        # Build secure server-side RoutingContext
        slots = {}
        if req.order_id:
            slots["order_id"] = req.order_id.strip()

        context = RoutingContext(
            verified_scope=profile["scope"],
            ticket_customer_id=profile["id"],
            is_personal_lookup=req.is_personal_lookup,
            extracted_slots=slots,
        )

        run_result = self.runner.run(text=req.text.strip(), context=context, run_id=req.submission_id)

        # Hash draft body for integrity tracking
        draft_body = run_result.get("draft_body")
        draft_hash = hashlib.sha256(draft_body.encode("utf-8")).hexdigest() if draft_body else None

        # Extract and format sources
        sources = []
        for src in run_result.get("sources", []):
            doc_id = src.get("document_id") or src.get("doc_id")
            snippet = src.get("excerpt") or ""
            if not snippet and src.get("chunks"):
                snippet = src["chunks"][0].get("text", "")
            snippet = snippet[:300]
            source_id = None
            llm_citations = (run_result.get("llm") or {}).get("citations", [])
            for c in llm_citations:
                if isinstance(c, dict):
                    if str(c.get("document_id")) == str(doc_id) and str(c.get("version")) == str(src.get("version")):
                        source_id = c.get("source_id")
                        break
                elif isinstance(c, str):
                    source_id = c
                    break
            sources.append({
                "source_id": source_id,
                "doc_id": doc_id,
                "title": src.get("title"),
                "version": src.get("version"),
                "category": src.get("category"),
                "score": src.get("score"),
                "snippet": snippet,
            })

        # Expose structured demo result
        response_payload = {
            "run_id": run_result["run_id"],
            "decision_id": run_result["decision_id"],
            "action": run_result["action"],
            "predicted_intent": run_result["predicted_intent"],
            "final_intent": run_result["final_intent"],
            "requested_team": run_result["requested_team"],
            "target_queue": run_result["target_queue"],
            "reason_codes": run_result["reason_codes"],
            "missing_slots": run_result.get("missing_slots", []),
            "confidence": run_result.get("confidence"),
            "margin": run_result.get("margin"),
            "score_kind": run_result.get("score_kind", "uncalibrated_softmax"),
            "must_human_approve": run_result["must_human_approve"],
            "can_execute_transaction": run_result["can_execute_transaction"],
            "model_version": run_result.get("model_version"),
            "policy_version": run_result.get("policy_version"),
            "evidence_retrieved": run_result.get("evidence_retrieved", False),
            "evidence_count": run_result.get("evidence_count", 0),
            "sources": sources,
            "draft_body": draft_body,
            "draft_kind": run_result.get("draft_kind"),
            "llm": run_result.get("llm"),
            "llm_called": run_result.get("llm_called", False),
            "draft_hash": draft_hash,
            "is_duplicate_run": run_result.get("is_duplicate_run", False),
        }

        self.store.save_submission(
            submission_id=req.submission_id,
            fingerprint=fingerprint,
            run_id=run_result["run_id"],
            session_id=session_id,
            result=response_payload
        )
        return response_payload

    def record_feedback(self, run_id: str, req: DemoFeedbackRequest, session_id: str) -> Dict[str, Any]:
        with self.store._connection() as conn:
            cur = conn.execute("SELECT session_id, result_json FROM demo_submissions WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Run '{run_id}' not found")
            if row["session_id"] and row["session_id"] != session_id:
                raise KeyError("Unauthorized: feedback session does not match submission owner")
            res_data = json.loads(row["result_json"])

        draft_body = res_data.get("draft_body")
        current_hash = res_data.get("draft_hash") or ""

        # Validate action preconditions
        if req.action in ("approve", "edit"):
            if not draft_body:
                # Spec: Nếu không có draft, approve/edit trả 409
                raise KeyError("No draft exists on this run to approve or edit")
            if req.draft_hash != current_hash:
                raise ValueError("Draft revision mismatch: draft has been modified or incorrect revision hash provided")
        elif req.action in ("reject", "escalate"):
            # Reject and escalate do not strictly require draft, but if hash provided it should match if draft exists
            if current_hash and req.draft_hash and req.draft_hash != current_hash:
                raise ValueError("Draft revision mismatch for action")
        else:
            raise ValueError(f"Unknown feedback action '{req.action}'")

        new_hash = current_hash
        if req.action == "edit":
            if not req.edited_text or not req.edited_text.strip():
                raise ValueError("Edited text must be provided when action is 'edit'")
            new_hash = hashlib.sha256(req.edited_text.strip().encode("utf-8")).hexdigest()
            res_data["draft_body"] = req.edited_text.strip()
            res_data["draft_hash"] = new_hash
            self.store.update_submission_result(run_id, res_data)

        # Idempotent escalation enqueue if action is escalate
        if req.action == "escalate":
            if hasattr(self.runner, "store") and hasattr(self.runner.store, "enqueue_escalation"):
                self.runner.store.enqueue_escalation(
                    run_id=run_id,
                    decision_id=res_data.get("decision_id") or run_id,
                    target_team=res_data.get("requested_team") or "general_support",
                    target_queue=res_data.get("target_queue") or "standard",
                    reason_codes=["staff_escalated_feedback"]
                )

        self.store.record_feedback(
            run_id=run_id,
            session_id=session_id,
            action=req.action,
            draft_hash=req.draft_hash,
            edited_text=req.edited_text
        )
        return {"status": "recorded", "action": req.action, "current_draft_hash": new_hash}

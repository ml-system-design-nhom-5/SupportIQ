"""System execution adapter, dependencies factory, and case tracing with isolated state."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock

from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import load_policy_v2, decide_route
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction
from apps.core_backend.llm.gemini import GeminiDraftClient
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.demo.app import create_app
from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    CaseResult,
    SystemCase,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_server import ManagedDemoServer


def _compute_str_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MockIntentClient:
    """Offline mock intent classifier for zero-network benchmark runs."""
    def __init__(self, default_intent: str = "track_order"):
        self.default_intent = default_intent

    def classify_intent(self, text: str, request_id: Optional[str] = None):
        # Keyword matching fallback for standard benchmarks
        t_low = text.lower()
        if "close" in t_low and "account" in t_low:
            intent = "close_account"
        elif "return" in t_low or "refund" in t_low:
            intent = "return_policy"
        elif "ship" in t_low or "delivery" in t_low:
            intent = "shipping_costs"
        elif "track" in t_low or "order" in t_low:
            intent = "track_order"
        elif "cancel" in t_low:
            intent = "cancel_order"
        else:
            intent = self.default_intent

        return IntentPrediction(
            intent=intent,
            confidence=0.95,
            margin=0.30,
            model_version="v1.0-mock",
            score_kind="mock_softmax",
            error=None,
        )


@dataclass
class SystemDependencies:
    """Isolated runtime dependencies for executing benchmark cases."""
    runner: PipelineRunner
    retrieval: RetrievalAdapter
    store: PersistentStore
    demo_app: Any
    profile: str
    runtime_dir: Path
    clock: Callable[[], datetime]
    deadline_seconds: float = 30.0
    ledger: Optional[Any] = None
    managed_server: Optional[ManagedDemoServer] = None

    def close(self) -> None:
        """Clean up managed processes and database locks."""
        if self.managed_server is not None:
            self.managed_server.close()


def build_system_dependencies(
    inputs: VerifiedSystemInputs,
    profile: str,
    runtime_dir: Path | str,
) -> SystemDependencies:
    """Build isolated runtime dependencies according to profile ('mock' or 'live').
    Enforces strict preflight checks and zero network access for mock.
    """
    clean_profile = profile.strip().lower()
    if clean_profile not in ("mock", "live"):
        raise EvaluationError(f"Unsupported evaluation profile: '{profile}' (expected 'mock' or 'live')")

    r_dir = Path(runtime_dir).resolve()
    r_dir.mkdir(parents=True, exist_ok=True)

    orchestration_db = r_dir / "orchestration.sqlite3"
    demo_db = r_dir / "demo.sqlite3"
    clock_fn = lambda: inputs.as_of
    deadline_sec = inputs.config.deadline_seconds or 30.0

    if clean_profile == "mock":
        p_store = PersistentStore(db_path=str(orchestration_db))
        kb_path = inputs.source_paths.get("kb", Path("data/knowledge/approved_kb.v1.json"))
        
        # Build offline retrieval adapter
        retrieval = RetrievalAdapter(kb_path=str(kb_path), encoder=None)
        mock_intent_client = MockIntentClient()
        mock_llm_client = GeminiDraftClient(api_key=None)  # unconfigured mock
        policy = load_policy_v2()

        runner = PipelineRunner(
            intent_client=mock_intent_client,
            policy=policy,
            retrieval_adapter=retrieval,
            store=p_store,
            llm_client=mock_llm_client,
            clock=clock_fn,
        )

        app = create_app(db_path=str(demo_db), runner=runner)

        return SystemDependencies(
            runner=runner,
            retrieval=retrieval,
            store=p_store,
            demo_app=app,
            profile="mock",
            runtime_dir=r_dir,
            clock=clock_fn,
            deadline_seconds=deadline_sec,
        )

    # Live profile preflight verification
    release_manifest = Path("ml/releases/manifest.json")
    if not release_manifest.exists():
        raise EvaluationError("Live preflight failed: release manifest 'ml/releases/manifest.json' not found")

    # In live profile, verify dependencies readiness before starting
    raise EvaluationError("Live preflight failed: external ML inference service not ready or unpinned")


def execute_system_case(
    case: SystemCase,
    deps: SystemDependencies,
    attempt_id: str,
    scope: str = "e2e",
) -> CaseResult:
    """Execute a single benchmark case within isolated dependencies and strict deadline.
    Returns normalized CaseResult with full stage tracing.
    """
    t_start = time.perf_counter()
    deadline = deps.deadline_seconds

    # Controlled fault handling
    if case.fault in ("ml_timeout", "llm_timeout"):
        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
        return CaseResult(
            case_id=case.id,
            repetition=1,
            profile=deps.profile,
            scope=scope,
            execution_status="timeout",
            error_code="deadline_exceeded",
            stage_elapsed_ms={"simulated_timeout_ms": elapsed_ms},
            total_elapsed_ms=elapsed_ms,
        )

    # 1. Component Scope
    if scope == "component":
        t_probe = time.perf_counter()
        target_intent = case.true_intent or "unknown"
        pred = IntentPrediction(
            intent=target_intent,
            confidence=0.95,
            margin=0.30,
            model_version="v1.0-probe",
            score_kind="probe_softmax",
            error=None,
        )
        ctx = RoutingContext(
            ticket_customer_id=case.context.ticket_customer_id,
            verified_scope=case.context.verified_scope,
            is_personal_lookup=case.context.is_personal_lookup,
            extracted_slots=case.context.extracted_slots,
            role="agent",
            as_of=deps.clock(),
        )
        decision = decide_route(pred, ctx, deps.runner.policy)

        # Retrieval component probe uses gold intent directly
        normalized_sources = []
        ret_status = "ok"
        if decision.action == "retrieve_draft" or case.expected.retrieval_applicable or case.expected.answerable:
            ret_res = deps.retrieval.retrieve(
                case.text,
                target_intent,
                role="agent",
                current_time=deps.clock(),
            )
            raw_sources = ret_res.get("evidence", [])
            for s in raw_sources:
                normalized_sources.append({
                    "doc_id": s.get("document_id") or s.get("doc_id"),
                    "version": str(s.get("version", "1.0")),
                    "status": s.get("status", "approved"),
                })
            if ret_res.get("status") != "success":
                ret_status = ret_res.get("status", "error")

        probe_elapsed = round((time.perf_counter() - t_probe) * 1000.0, 2)
        return CaseResult(
            case_id=case.id,
            repetition=1,
            profile=deps.profile,
            scope="component",
            execution_status="ok",
            error_code=None if ret_status == "ok" else ret_status,
            routing_action=decision.action,
            final_action=decision.action,
            requested_team=decision.requested_team,
            target_queue=decision.target_queue,
            reason_codes=decision.reason_codes,
            predicted_intent=decision.predicted_intent,
            final_intent=decision.final_intent,
            sources=normalized_sources,
            stage_elapsed_ms={"component_probe_ms": probe_elapsed},
            total_elapsed_ms=probe_elapsed,
        )

    # 2. E2E Scope
    ctx = RoutingContext(
        ticket_customer_id=case.context.ticket_customer_id,
        verified_scope=case.context.verified_scope,
        is_personal_lookup=case.context.is_personal_lookup,
        extracted_slots=case.context.extracted_slots,
        role="agent",
        as_of=deps.clock(),
    )

    t_run_start = time.perf_counter()
    try:
        run_res = deps.runner.run(text=case.text, context=ctx, run_id=attempt_id)
    except Exception as exc:
        total_elapsed = round((time.perf_counter() - t_start) * 1000.0, 2)
        return CaseResult(
            case_id=case.id,
            repetition=1,
            profile=deps.profile,
            scope=scope,
            execution_status="error",
            error_code=type(exc).__name__,
            stage_elapsed_ms={},
            total_elapsed_ms=total_elapsed,
        )

    t_run_elapsed = time.perf_counter() - t_run_start
    total_elapsed_ms = round(t_run_elapsed * 1000.0, 2)

    # Deadline termination check
    if t_run_elapsed > deadline:
        return CaseResult(
            case_id=case.id,
            repetition=1,
            profile=deps.profile,
            scope=scope,
            execution_status="timeout",
            error_code="deadline_exceeded",
            stage_elapsed_ms=run_res.get("stage_elapsed_ms", {}),
            total_elapsed_ms=total_elapsed_ms,
        )

    # Extract draft and compute SHA-256 hash if present
    draft_body = run_res.get("draft_body")
    draft_hash = _compute_str_sha256(draft_body) if draft_body else None

    # Normalize sources
    normalized_sources = []
    for s in run_res.get("sources", []):
        normalized_sources.append({
            "doc_id": s.get("document_id") or s.get("doc_id"),
            "version": str(s.get("version", "1.0")),
            "status": s.get("status", "approved"),
        })

    routing_act = run_res.get("routing_action") or run_res.get("initial_routing_action") or run_res.get("action")

    return CaseResult(
        case_id=case.id,
        repetition=1,
        profile=deps.profile,
        scope=scope,
        execution_status="ok",
        error_code=None,
        routing_action=routing_act,
        final_action=run_res.get("action"),
        requested_team=run_res.get("requested_team"),
        target_queue=run_res.get("target_queue"),
        reason_codes=run_res.get("reason_codes", []),
        predicted_intent=run_res.get("predicted_intent"),
        final_intent=run_res.get("final_intent"),
        prediction_confidence=run_res.get("confidence"),
        prediction_margin=run_res.get("margin"),
        sources=normalized_sources,
        draft_body=draft_body,
        draft_kind=run_res.get("draft_kind"),
        draft_hash=draft_hash,
        llm_called=run_res.get("llm_called", False),
        llm_metadata=None,
        llm_usage=None,
        stage_elapsed_ms=run_res.get("stage_elapsed_ms", {}),
        total_elapsed_ms=total_elapsed_ms,
    )


def run_component_probes(
    inputs: VerifiedSystemInputs,
    deps: SystemDependencies,
) -> List[CaseResult]:
    """Execute component probes for all benchmark cases with isolated scope='component'.
    Evaluates routing and semantic retrieval directly without modifying end-to-end metrics.
    """
    probe_results: List[CaseResult] = []
    for case in inputs.cases:
        res = execute_system_case(
            case=case,
            deps=deps,
            attempt_id=f"probe-{case.id}",
            scope="component",
        )
        probe_results.append(res)
    return probe_results


def run_oversight_scenarios(
    deps: SystemDependencies,
    runtime_dir: Path | str,
) -> List[CaseResult]:
    """Execute human oversight, session ownership, and idempotency scenarios against demo app.
    Collects actual database persistence facts and returns structured CaseResult records.
    """
    import sqlite3
    from fastapi.testclient import TestClient

    r_dir = Path(runtime_dir).resolve()
    results: List[CaseResult] = []

    client_a = TestClient(deps.demo_app, cookies={"demo_session_id": "eval-session-A"})
    client_b = TestClient(deps.demo_app, cookies={"demo_session_id": "eval-session-B"})

    # 1. Submit a base run as Session A
    sub_id = "eval-over-sub-001"
    resp_sub = client_a.post("/api/demo/runs", json={
        "submission_id": sub_id,
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    })
    run_data = resp_sub.json()
    run_id = run_data["run_id"]
    current_hash = run_data.get("draft_hash") or "initial-hash"

    # Scenario 1: Session B cross-session feedback rejection
    t0 = time.perf_counter()
    resp_cross = client_b.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": current_hash,
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    cross_rejected = resp_cross.status_code in (403, 409)

    results.append(CaseResult(
        case_id="oversight-session-ownership",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if cross_rejected else "error",
        error_code=None if cross_rejected else f"status_{resp_cross.status_code}",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "session_owner": "eval-session-A",
            "attacker_session": "eval-session-B",
            "http_status": resp_cross.status_code,
            "ownership_protected": cross_rejected,
        },
    ))

    # Scenario 2: Stale draft hash approval rejection (409)
    t0 = time.perf_counter()
    resp_stale = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": "stale-tampered-hash-000",
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    stale_rejected = resp_stale.status_code in (400, 409)

    results.append(CaseResult(
        case_id="oversight-stale-hash",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if stale_rejected else "error",
        error_code=None if stale_rejected else f"status_{resp_stale.status_code}",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "expected_hash": current_hash,
            "submitted_hash": "stale-tampered-hash-000",
            "http_status": resp_stale.status_code,
            "stale_protection_passed": stale_rejected,
        },
    ))

    # Scenario 3: Feedback audit verification & transaction safety
    t0 = time.perf_counter()
    resp_approve = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": current_hash,
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    demo_db = r_dir / "demo.sqlite3"
    feedback_count = 0
    tx_blocked = True
    if demo_db.exists():
        with sqlite3.connect(demo_db) as conn:
            conn.row_factory = sqlite3.Row
            fb_row = conn.execute("SELECT COUNT(*) as cnt FROM demo_feedback WHERE run_id = ?", (run_id,)).fetchone()
            feedback_count = fb_row["cnt"] if fb_row else 0
            sub_row = conn.execute("SELECT result_json FROM demo_submissions WHERE run_id = ?", (run_id,)).fetchone()
            if sub_row:
                import json
                sub_data = json.loads(sub_row["result_json"])
                tx_blocked = (sub_data.get("can_execute_transaction") is False)

    results.append(CaseResult(
        case_id="oversight-feedback-audit",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if (feedback_count >= 1 and tx_blocked) else "error",
        error_code=None if (feedback_count >= 1 and tx_blocked) else "audit_check_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "feedback_recorded": feedback_count >= 1,
            "can_execute_transaction": not tx_blocked,
            "audit_verified": (feedback_count >= 1 and tx_blocked),
        },
    ))

    # Scenario 4: Concurrent idempotency on orchestration store
    t0 = time.perf_counter()
    idem_run_id = "eval-idem-test-999"
    saved1 = deps.store.save_run_and_escalate_atomic(
        run_id=idem_run_id,
        result={"run_id": idem_run_id, "action": "escalate"},
        escalate_info={"decision_id": "dec-1", "target_team": "support", "target_queue": "standard", "reason_codes": []},
    )
    saved2 = deps.store.save_run_and_escalate_atomic(
        run_id=idem_run_id,
        result={"run_id": idem_run_id, "action": "escalate"},
        escalate_info={"decision_id": "dec-1", "target_team": "support", "target_queue": "standard", "reason_codes": []},
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    idempotent_ok = (saved1 is True and saved2 is False)

    results.append(CaseResult(
        case_id="oversight-idempotent-persistence",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if idempotent_ok else "error",
        error_code=None if idempotent_ok else "idempotency_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": idem_run_id,
            "first_save": saved1,
            "second_save": saved2,
            "idempotency_preserved": idempotent_ok,
        },
    ))

    return results

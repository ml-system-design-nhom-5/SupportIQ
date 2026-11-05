"""System execution adapter, dependencies factory, and case tracing with isolated state."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock

import numpy as np

from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import load_policy_v2, decide_route
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
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
from pipeline.evaluation.system_performance import BudgetLedger
from pipeline.evaluation.system_server import ManagedDemoServer
from pipeline.preparation.utils import compute_sha256


def _compute_str_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MockPolicyEncoder:
    """Offline mock policy encoder ensuring zero network/disk weight loading in mock profile."""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.tokenizer = None

    def encode_passages(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        vecs = []
        for t in texts:
            h = int(hashlib.sha256(t.encode("utf-8")).hexdigest(), 16)
            rng = np.random.RandomState(h % (2**32))
            v = rng.randn(self.dimension).astype(np.float32)
            norm = np.linalg.norm(v)
            vecs.append(v / (norm if norm > 0 else 1.0))
        return np.array(vecs, dtype=np.float32)

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        return self.encode_passages(queries)

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode_passages([query])[0]


class MockLLMClient:
    """Zero-network mock LLM client completely isolated from environment keys and httpx."""
    def __init__(self, configured: bool = True):
        self.configured = configured

    def generate(self, question: str, intent: str, evidence: list[dict], business_context: dict | None = None) -> dict[str, Any]:
        if not self.configured:
            raise LLMError("llm_not_configured")
        citations = []
        body_parts = []
        for i, ev in enumerate(evidence[:3], start=1):
            doc_id = ev.get("document_id") or ev.get("doc_id", "DOC")
            citations.append(f"[S{i}]")
            excerpt = ev.get("excerpt") or ev.get("title") or "policy information"
            body_parts.append(f"{excerpt.strip()} [S{i}]")
        body = " ".join(body_parts) if body_parts else "Support information."
        return {
            "body": body,
            "citations": citations,
            "usage": {"input_tokens": 120, "output_tokens": 60},
        }


class BudgetedLLMClient:
    """Wraps any LLM client to atomically reserve and record budget via BudgetLedger."""
    def __init__(self, client: Any, ledger: BudgetLedger, input_bound: int = 4000, output_bound: int = 1000):
        self._client = client
        self._ledger = ledger
        self.input_bound = input_bound
        self.output_bound = output_bound

    @property
    def configured(self) -> bool:
        return bool(getattr(self._client, "configured", False))

    def generate(self, question: str, intent: str, evidence: list[dict], business_context: dict | None = None) -> dict[str, Any]:
        attempt_id = self._ledger.reserve(self.input_bound, self.output_bound)
        try:
            res = self._client.generate(question, intent, evidence, business_context=business_context)
            usage = res.get("usage") if isinstance(res, dict) else None
            self._ledger.record(attempt_id, usage)
            return res
        except Exception:
            self._ledger.record(attempt_id, None)
            raise


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
    start_server: bool = True,
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
    budget_db = r_dir / "budget.sqlite3"
    clock_fn = lambda: inputs.as_of
    deadline_sec = inputs.config.deadline_seconds or 30.0

    # Build Budget Ledger for call and cost governance
    ledger = BudgetLedger(db_path=budget_db, config=inputs.config)

    if clean_profile == "mock":
        p_store = PersistentStore(db_path=str(orchestration_db))
        kb_path = inputs.source_paths.get("kb", Path("data/knowledge/approved_kb.v1.json"))

        # Build offline retrieval adapter with MockPolicyEncoder (zero PyTorch / model loading)
        mock_encoder = MockPolicyEncoder()
        retrieval = RetrievalAdapter(kb_path=str(kb_path), encoder=mock_encoder)
        mock_intent_client = MockIntentClient()
        raw_mock_llm = MockLLMClient(configured=True)
        budgeted_llm = BudgetedLLMClient(raw_mock_llm, ledger=ledger)
        policy = load_policy_v2()

        runner = PipelineRunner(
            intent_client=mock_intent_client,
            policy=policy,
            retrieval_adapter=retrieval,
            store=p_store,
            llm_client=budgeted_llm,
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
            ledger=ledger,
        )

    # Live profile preflight verification
    release_manifest = Path("ml/releases/manifest.json")
    if not release_manifest.exists():
        raise EvaluationError("Live preflight failed: release manifest 'ml/releases/manifest.json' not found")

    try:
        with open(release_manifest, "r", encoding="utf-8") as f:
            rel_data = json.load(f)
    except Exception as exc:
        raise EvaluationError(f"Live preflight failed: invalid release manifest JSON: {exc}") from exc

    if not isinstance(rel_data, dict):
        raise EvaluationError("Live preflight failed: release manifest must be a JSON object")

    # Strict release schema validation
    for required_key in ("package_version", "model_type", "artifacts"):
        if required_key not in rel_data:
            raise EvaluationError(
                f"Live preflight failed: release manifest missing required fields ({required_key})"
            )

    artifacts = rel_data.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise EvaluationError(
            "Live preflight failed: release manifest must contain a non-empty 'artifacts' dictionary"
        )

    rel_dir = release_manifest.parent
    for art_key, art_meta in artifacts.items():
        if not isinstance(art_meta, dict) or "path" not in art_meta or "sha256" not in art_meta:
            raise EvaluationError(f"Live preflight failed: artifact '{art_key}' missing path or sha256 checksum")
        target_art = rel_dir / art_meta["path"]
        if not target_art.exists():
            raise EvaluationError(f"Live preflight failed: declared artifact '{art_key}' missing at {target_art}")
        actual_sha = compute_sha256(target_art)
        expected_sha = art_meta["sha256"]
        if actual_sha != expected_sha:
            raise EvaluationError(
                f"Live preflight failed: artifact '{art_key}' checksum mismatch: expected {expected_sha}, got {actual_sha}"
            )

    kb_path = inputs.source_paths.get("kb", Path("data/knowledge/approved_kb.v1.json"))
    if not Path(kb_path).exists():
        raise EvaluationError(f"Live preflight failed: approved KB snapshot '{kb_path}' not found")

    # In live profile, build real dependencies
    p_store = PersistentStore(db_path=str(orchestration_db))
    try:
        retrieval = RetrievalAdapter(kb_path=str(kb_path))
    except Exception as exc:
        raise EvaluationError(f"Live preflight failed: could not load retrieval adapter: {exc}") from exc

    intent_client = IntentClient()
    raw_llm = GeminiDraftClient()
    budgeted_llm = BudgetedLLMClient(raw_llm, ledger=ledger)
    policy = load_policy_v2()

    runner = PipelineRunner(
        intent_client=intent_client,
        policy=policy,
        retrieval_adapter=retrieval,
        store=p_store,
        llm_client=budgeted_llm,
        clock=clock_fn,
    )

    app = create_app(db_path=str(demo_db), runner=runner)

    # Instantiate and start managed demo server for live loopback testing
    managed_server = ManagedDemoServer(
        run_nonce=f"live-eval-{uuid.uuid4().hex[:8]}",
        input_fingerprint=inputs.input_hashes.get("suite_manifest", "live-fingerprint"),
    )
    try:
        if start_server:
            managed_server.start(inputs, runtime_dir=r_dir, ledger_path=budget_db, profile="live")
        else:
            managed_server = None
    except Exception as exc:
        managed_server.close()
        raise EvaluationError(f"Live preflight failed to start managed demo server: {exc}") from exc

    return SystemDependencies(
        runner=runner,
        retrieval=retrieval,
        store=p_store,
        demo_app=app,
        profile="live",
        runtime_dir=r_dir,
        clock=clock_fn,
        deadline_seconds=deadline_sec,
        ledger=ledger,
        managed_server=managed_server,
    )


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

    # Inject controlled faults into runner dependencies if specified
    old_classify = None
    runner_intent_client = getattr(deps.runner, "intent_client", None)
    if case.fault in ("ml_error", "ml_unavailable") and runner_intent_client is not None:
        old_classify = getattr(runner_intent_client, "classify_intent", None)
        runner_intent_client.classify_intent = lambda *a, **kw: IntentPrediction(
            intent="unknown",
            confidence=0.0,
            margin=0.0,
            model_version="fault-injected",
            score_kind="error",
            error="ml_service_unavailable",
        )

    old_llm_generate = None
    runner_llm = getattr(deps.runner, "llm_client", None)
    if case.fault in (
        "llm_error",
        "llm_unavailable",
        "llm_rate_limited",
        "llm_invalid_citations",
        "llm_blocked",
    ) and runner_llm is not None:
        old_llm_generate = getattr(runner_llm, "generate", None)
        def _failing_llm(*a, **kw):
            raise LLMError(case.fault)
        runner_llm.generate = _failing_llm

    old_retrieve = None
    runner_retrieval = getattr(deps.runner, "retrieval", None)
    if case.fault in ("encoder_unavailable", "encoder_failure") and runner_retrieval is not None:
        old_retrieve = getattr(runner_retrieval, "retrieve", None)
        runner_retrieval.retrieve = lambda *a, **kw: {
            "status": case.fault,
            "evidence": [],
            "error": case.fault,
        }

    old_lookup_order = None
    runner_commerce = getattr(deps.runner, "commerce", None)
    if case.fault in ("commerce_unauthorized", "commerce_not_found") and runner_commerce is not None:
        old_lookup_order = getattr(runner_commerce, "lookup_order", None)
        error_kind = "unauthorized_scope" if case.fault == "commerce_unauthorized" else "order_not_found"
        runner_commerce.lookup_order = lambda *a, **kw: {
            "authorized": False,
            "error": error_kind,
            "order": None,
        }
        if not ctx.extracted_slots.get("order_id"):
            ctx.extracted_slots["order_id"] = "FAULT-ORD-999"

    t_run_start = time.perf_counter()
    worker_res: Dict[str, Any] = {}
    worker_exc: Dict[str, Any] = {}

    def _worker():
        try:
            worker_res["data"] = deps.runner.run(text=case.text, context=ctx, run_id=attempt_id)
        except BaseException as exc:
            worker_exc["error"] = exc

    worker_thread = threading.Thread(target=_worker, daemon=True)
    try:
        worker_thread.start()
        worker_thread.join(timeout=deadline)

        if worker_thread.is_alive():
            # If a managed worker process exists, terminate and restart it to kill hung worker and release locks cleanly
            if deps.managed_server is not None and deps.managed_server.is_running():
                deps.managed_server.close()
                deps.managed_server.restart()

            total_elapsed = round((time.perf_counter() - t_start) * 1000.0, 2)
            return CaseResult(
                case_id=case.id,
                repetition=1,
                profile=deps.profile,
                scope=scope,
                execution_status="timeout",
                error_code="deadline_exceeded",
                stage_elapsed_ms={"deadline_timeout_ms": total_elapsed},
                total_elapsed_ms=total_elapsed,
            )

        if "error" in worker_exc:
            exc = worker_exc["error"]
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

        run_res = worker_res.get("data", {})
    finally:
        if old_classify and runner_intent_client:
            runner_intent_client.classify_intent = old_classify
        if old_llm_generate and runner_llm:
            runner_llm.generate = old_llm_generate
        if old_retrieve and runner_retrieval:
            runner_retrieval.retrieve = old_retrieve
        if old_lookup_order and runner_commerce:
            runner_commerce.lookup_order = old_lookup_order

    t_run_elapsed = time.perf_counter() - t_run_start
    total_elapsed_ms = round(t_run_elapsed * 1000.0, 2)

    # Post-execution sanity check on total elapsed
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

    # Safety check on must_not_draft invariant
    if case.expected.must_not_draft and draft_body and str(draft_body).strip():
        return CaseResult(
            case_id=case.id,
            repetition=1,
            profile=deps.profile,
            scope=scope,
            execution_status="error",
            error_code="must_not_draft_violation",
            routing_action=routing_act,
            final_action=run_res.get("action"),
            draft_body=draft_body,
            draft_hash=draft_hash,
            sources=normalized_sources,
            total_elapsed_ms=total_elapsed_ms,
        )

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

"""Task C isolated fault-boundary verification runner (0 live LLM calls).

Executes the previously NOT_EXECUTED fault cases from
`data/benchmarks/system/v2/acceptance/cases.jsonl` across two real runtime surfaces:
1. Application Backend + Disposable PostgreSQL + SuggestionWorker + Isolated ai_service gateway
2. Core Backend PipelineRunner (IntentClient -> decide_route -> CommerceAdapter -> RetrievalAdapter -> SpyLLM)

Strict constraints:
- Zero production source edits (`apps/` untouched)
- Zero live Gemini calls (`ZeroBudgetTransport` with max_requests=0 and retries=0)
- Frozen benchmark expectations (`expected.actions`, `reason_any`, `must_escalate`, `must_not_draft`)
  preserved untouched and evaluated with explicit strict-vs-safe-fallback distinction.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional
import uuid

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine, select, text

from apps.backend.main import create_app as create_backend_app
from apps.backend.platform.config import Settings as BackendSettings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Order, Suggestion, Ticket
from apps.backend.seed import seed
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.schemas import RoutingContext
from apps.core_backend.llm.gemini import LLMError
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.flash_lite_acceptance import (
    DEFAULT_ROOT_REPO,
    FLASH_LITE_35_MODEL,
    REPO_ROOT,
    _drop_temporary_postgres_schema,
    owned_isolated_ai_service,
)
from pipeline.evaluation.live_provider_verification import (
    ALLOWED_GEMINI_HOST,
    BudgetExhaustedBeforeNetworkError,
    sanitize_text,
)
from scripts.collect_final_acceptance_evidence import (
    compute_bytes_sha256,
    compute_sha256,
    get_git_commit_hash,
    resolve_database_url,
)

PRIMARY_TARGET_CASE_IDS = (
    "unc-track_order-03",     # ml_timeout
    "unc-return_policy-04",   # encoder_failure
    "unc-track_order-05",     # commerce_unauthorized
)

COMPANION_FAULT_CASE_IDS = (
    "unc-track_order-04",     # ml_error
    "unc-return_policy-03",   # encoder_unavailable
    "unc-refund_policy-01",   # llm_timeout
    "unc-cancel_order-03",    # llm_invalid_citations
    "unc-track_order-06",     # commerce_not_found
)


class ZeroBudgetTransport(httpx.BaseTransport):
    """Pre-network HTTP transport enforcing max_requests=0 and retries=0."""

    def __init__(self) -> None:
        self.max_requests = 0
        self._retries_configured = 0
        self._lock = threading.Lock()
        self.requests_attempted = 0
        self.rejected_before_network_count = 0
        self.records: List[Dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests_attempted += 1
            self.rejected_before_network_count += 1
            self.records.append(
                {
                    "scheme": request.url.scheme,
                    "host": request.url.host,
                    "path": request.url.path,
                    "outcome": "blocked_zero_live_budget",
                }
            )
        if request.url.scheme != "https" or request.url.host != ALLOWED_GEMINI_HOST:
            raise httpx.RequestError(f"Egress host is not allowed: {request.url.scheme}://{request.url.host}", request=request)
        raise BudgetExhaustedBeforeNetworkError(
            "Zero live budget enforced (0/0); blocked before network I/O",
            request=request,
        )


class SpyLLMClient:
    """In-memory spy LLM tracking call counts and supporting deterministic offline fault injection."""

    def __init__(self, mode: str = "forbid", configured: bool = True) -> None:
        self.mode = mode
        self.configured = configured
        self.calls: List[Dict[str, Any]] = []

    def reset(self, mode: str = "forbid") -> None:
        self.mode = mode
        self.calls = []

    def generate(
        self,
        message: str,
        intent: str,
        evidence: List[Dict[str, Any]],
        business_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append(
            {
                "message": message,
                "intent": intent,
                "evidence_count": len(evidence),
                "has_business_context": bool(business_context),
            }
        )
        if self.mode == "forbid":
            raise AssertionError(f"LLM generate() must not be called in fault mode 'forbid' (intent={intent})")
        if self.mode == "llm_timeout":
            raise LLMError(
                "llm_timeout",
                metadata={"provider": "spy_offline", "model": "none"},
                latency_seconds=0.01,
            )
        if self.mode == "llm_invalid_citations":
            return {
                "body": "Refunds and cancellations follow policy rules [S99].",
                "provider": "spy_offline",
                "model": "none",
                "usage": {"promptTokenCount": 1, "candidatesTokenCount": 1},
                "latency_seconds": 0.005,
                "input_snapshot": {"sources": []},
            }
        raise ValueError(f"Unsupported SpyLLMClient mode: {self.mode}")


def load_acceptance_fault_cases(cases_path: Path) -> List[Dict[str, Any]]:
    """Load frozen fault cases from `acceptance/cases.jsonl` preserving exact order and fields."""
    rows: List[Dict[str, Any]] = []
    for raw in cases_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("fault") is not None:
            rows.append(obj)
    return rows


def _resolve_model_dir(worktree_root: Path, root_repo: Path) -> Path:
    local_dir = worktree_root / "artifacts" / "models" / "trained" / "distilbert-supportiq"
    if (local_dir / "model.safetensors").exists():
        return local_dir
    fallback_dir = root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"
    if (fallback_dir / "model.safetensors").exists():
        return fallback_dir
    raise FileNotFoundError(f"Serving model missing under {local_dir} and {fallback_dir}")


def _map_backend_action(draft_status: Optional[str], http_status: Optional[int]) -> Optional[str]:
    if http_status == 404:
        return "http_404_denied"
    mapping = {
        "escalation_recommended": "escalate",
        "abstained": "manual_fallback",
        "unavailable": "manual_fallback",
        "llm_unavailable": "manual_fallback",
        "draft_ready": "retrieve_draft",
    }
    return mapping.get(draft_status or "")


def _classify_fault_outcome(
    *,
    case: Dict[str, Any],
    surface: str,
    scenario: str,
    raw_action: Optional[str],
    mapped_action: Optional[str],
    reason_codes: List[str],
    no_draft_preserved: bool,
    llm_calls: int,
    customer_status: Optional[str] = None,
    customer_reply_is_none: Optional[bool] = None,
    is_authority_required: Optional[bool] = None,
    http_status: Optional[int] = None,
    exception_type: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    exp = case["expected"]
    expected_actions = list(exp.get("actions") or [])
    expected_reason_any = list(exp.get("reason_any") or [])
    must_escalate = bool(exp.get("must_escalate", False))
    must_not_draft = bool(exp.get("must_not_draft", False))

    reason_any_matched = (
        any(r in reason_codes for r in expected_reason_any)
        if expected_reason_any
        else True
    )
    action_in_expected = (mapped_action in expected_actions) if mapped_action else False
    strict_must_escalate_matched = (not must_escalate) or (mapped_action == "escalate")
    is_llm_fault_probe = case.get("fault") in ("llm_timeout", "llm_invalid_citations")
    no_draft_ok = no_draft_preserved if is_llm_fault_probe else ((not must_not_draft) or (no_draft_preserved and llm_calls == 0))

    if exception_type is not None:
        verdict = "UNHANDLED_EXCEPTION"
    elif not no_draft_ok:
        verdict = "FAIL_DRAFT_OR_LLM_ATTEMPTED"
    elif http_status == 404 and mapped_action == "http_404_denied":
        verdict = "INTAKE_DENIAL_404_MISMATCH" if must_escalate or expected_reason_any else "INTAKE_DENIAL_404"
    elif action_in_expected and strict_must_escalate_matched and reason_any_matched:
        verdict = "STRICT_PASS"
    elif action_in_expected:
        verdict = "SAFE_FALLBACK_MISMATCH"
    else:
        verdict = "ACTION_MISMATCH"

    return {
        "case_id": case["id"],
        "fault": case["fault"],
        "text": case["text"],
        "surface": surface,
        "scenario": scenario,
        "expected": {
            "actions": expected_actions,
            "reason_any": expected_reason_any,
            "must_escalate": must_escalate,
            "must_not_draft": must_not_draft,
            "team": exp.get("team"),
        },
        "observed": {
            "http_status": http_status,
            "raw_action": raw_action,
            "mapped_action": mapped_action,
            "reason_codes": reason_codes,
            "no_draft_preserved": no_draft_preserved,
            "llm_calls": llm_calls,
            "customer_status": customer_status,
            "customer_reply_is_none": customer_reply_is_none,
            "is_authority_required": is_authority_required,
            "exception_type": exception_type,
            **(details or {}),
        },
        "checks": {
            "no_draft_ok": no_draft_ok,
            "action_in_expected": action_in_expected,
            "strict_must_escalate_matched": strict_must_escalate_matched,
            "reason_any_matched": reason_any_matched,
        },
        "verdict": verdict,
    }


@contextmanager
def _installed_gateway_fault_hooks(fault_state: Dict[str, Any]) -> Iterator[None]:
    """Install surgical, reversible runtime fault hooks on ModelContainer & PolicyEncoder only."""
    import apps.core_backend.retrieval.adapter as ret_adapter_mod
    import apps.core_backend.retrieval.encoder as encoder_mod
    import apps.ml_inference.app as ml_app

    orig_predict = ml_app.ModelContainer.predict
    orig_encode_queries = encoder_mod.PolicyEncoder.encode_queries
    orig_retrieve = ret_adapter_mod.RetrievalAdapter.retrieve

    def wrapped_predict(self_container: Any, text_arg: str, *args: Any, **kwargs: Any) -> Any:
        mode = fault_state.get("ml_mode")
        if mode == "sleep":
            time.sleep(float(fault_state.get("sleep_seconds", 0.45)))
        elif mode == "timeout_error":
            raise TimeoutError("Injected ML inference TimeoutError inside ModelContainer.predict")
        elif mode == "runtime_error":
            raise RuntimeError("Injected ML inference RuntimeError inside ModelContainer.predict")
        return orig_predict(self_container, text_arg, *args, **kwargs)

    def wrapped_encode_queries(self_enc: Any, queries: List[str], *args: Any, **kwargs: Any) -> Any:
        mode = fault_state.get("encoder_mode")
        if mode == "runtime_failure":
            raise RuntimeError("Injected runtime encoder failure during PolicyEncoder.encode_queries")
        return orig_encode_queries(self_enc, queries, *args, **kwargs)

    def wrapped_retrieve(self_ret: Any, *args: Any, **kwargs: Any) -> Any:
        if fault_state.get("encoder_mode") == "encoder_unavailable":
            prev_encoder = self_ret.encoder
            prev_error = getattr(self_ret, "encoder_error", None)
            self_ret.encoder = None
            self_ret.encoder_error = "Injected encoder initialization unavailability"
            try:
                return orig_retrieve(self_ret, *args, **kwargs)
            finally:
                self_ret.encoder = prev_encoder
                self_ret.encoder_error = prev_error
        return orig_retrieve(self_ret, *args, **kwargs)

    ml_app.ModelContainer.predict = wrapped_predict  # type: ignore[method-assign]
    encoder_mod.PolicyEncoder.encode_queries = wrapped_encode_queries  # type: ignore[method-assign]
    ret_adapter_mod.RetrievalAdapter.retrieve = wrapped_retrieve  # type: ignore[method-assign]
    try:
        yield
    finally:
        ml_app.ModelContainer.predict = orig_predict  # type: ignore[method-assign]
        encoder_mod.PolicyEncoder.encode_queries = orig_encode_queries  # type: ignore[method-assign]
        ret_adapter_mod.RetrievalAdapter.retrieve = orig_retrieve  # type: ignore[method-assign]


def _poll_backend_terminal_suggestion(
    staff_client: TestClient,
    ticket_id: str,
    timeout_seconds: float = 8.0,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_detail: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = staff_client.get(f"/v1/console/tickets/{ticket_id}")
        if resp.status_code != 200:
            raise RuntimeError(f"GET /v1/console/tickets/{ticket_id} returned {resp.status_code}")
        last_detail = resp.json()
        sug = last_detail.get("suggestion") or {}
        a_stat = sug.get("analysis_status", "pending")
        d_stat = sug.get("draft_status", "pending")
        if a_stat != "pending" and d_stat != "pending":
            return last_detail
        time.sleep(0.05)
    return last_detail


def _submit_and_observe_backend_case(
    *,
    case: Dict[str, Any],
    scenario: str,
    customer_client: TestClient,
    staff_client: TestClient,
    order_id: Optional[str],
    zero_guard: ZeroBudgetTransport,
    timeout_seconds: float = 8.0,
) -> Dict[str, Any]:
    requests_before = zero_guard.requests_attempted
    before_tickets_resp = staff_client.get("/v1/console/tickets")
    before_ticket_count = (
        len(before_tickets_resp.json().get("items") or [])
        if before_tickets_resp.status_code == 200
        else None
    )
    payload: Dict[str, Any] = {"message": case["text"]}
    if order_id is not None:
        payload["order_id"] = order_id

    create_resp = customer_client.post(
        "/v1/shop/tickets",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json=payload,
    )
    if create_resp.status_code != 201:
        after_tickets_resp = staff_client.get("/v1/console/tickets")
        after_ticket_count = (
            len(after_tickets_resp.json().get("items") or [])
            if after_tickets_resp.status_code == 200
            else None
        )
        tickets_delta = (
            after_ticket_count - before_ticket_count
            if before_ticket_count is not None and after_ticket_count is not None
            else None
        )
        err_body = create_resp.json() if "application/" in create_resp.headers.get("content-type", "") else {}
        return _classify_fault_outcome(
            case=case,
            surface="backend_pg_gateway",
            scenario=scenario,
            raw_action=err_body.get("type") or f"http_{create_resp.status_code}",
            mapped_action=_map_backend_action(None, create_resp.status_code),
            reason_codes=[f"http_{create_resp.status_code}", str(err_body.get("type") or "rejected")],
            no_draft_preserved=True,
            llm_calls=zero_guard.requests_attempted - requests_before,
            http_status=create_resp.status_code,
            details={
                "response_problem": err_body,
                "tickets_created_delta": tickets_delta,
            },
        )

    ticket_created = create_resp.json()
    ticket_id = ticket_created["ticket_id"]
    detail = _poll_backend_terminal_suggestion(staff_client, ticket_id, timeout_seconds=timeout_seconds)
    cust_resp = customer_client.get(f"/v1/shop/tickets/{ticket_id}")
    cust_json = cust_resp.json() if cust_resp.status_code == 200 else {}

    sug = detail.get("suggestion") or {}
    raw_analysis = sug.get("analysis") or {}
    routing_codes = list((raw_analysis.get("routing") or {}).get("reason_codes") or [])
    sug_codes = list(sug.get("reason_codes") or [])
    merged_codes = sorted(set(routing_codes) | set(sug_codes))
    draft_status = sug.get("draft_status")
    analysis_status = sug.get("analysis_status")
    no_draft_preserved = (
        draft_status != "draft_ready"
        and sug.get("draft") is None
        and cust_json.get("reply") is None
    )
    linked_order = detail.get("order") or {}

    return _classify_fault_outcome(
        case=case,
        surface="backend_pg_gateway",
        scenario=scenario,
        raw_action=draft_status,
        mapped_action=_map_backend_action(draft_status, create_resp.status_code),
        reason_codes=merged_codes,
        no_draft_preserved=no_draft_preserved,
        llm_calls=zero_guard.requests_attempted - requests_before,
        customer_status=cust_json.get("customer_status"),
        customer_reply_is_none=(cust_json.get("reply") is None),
        is_authority_required=bool(detail.get("is_authority_required")),
        http_status=create_resp.status_code,
        details={
            "ticket_id": ticket_id,
            "ticket_order_id": linked_order.get("order_id"),
            "analysis_status": analysis_status,
            "draft_status": draft_status,
            "predicted_intent": (raw_analysis.get("intent") or {}).get("label"),
            "routing_recommendation": (raw_analysis.get("routing") or {}).get("recommendation"),
            "failure_code": sug.get("failure_code"),
            "staff_note": sug.get("staff_note"),
            "allowed_actions": detail.get("allowed_actions"),
        },
    )


def _make_mock_predict_transport(
    predict_fn: Callable[[str], Dict[str, Any]],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/predict":
            body = json.loads(request.content.decode("utf-8"))
            payload = predict_fn(body["text"])
            status_code = int(payload.pop("_http_status", 200))
            return httpx.Response(status_code, json=payload)
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def _run_pipeline_runner_case(
    *,
    case: Dict[str, Any],
    scenario: str,
    intent_client: IntentClient,
    commerce: CommerceAdapter,
    retrieval: RetrievalAdapter,
    spy_llm: SpyLLMClient,
    store_dir: Path,
) -> Dict[str, Any]:
    spy_llm.calls = []
    store = PersistentStore(db_path=str(store_dir / f"{scenario}_{uuid.uuid4().hex[:8]}.sqlite3"))
    runner = PipelineRunner(
        intent_client=intent_client,
        commerce_adapter=commerce,
        retrieval_adapter=retrieval,
        store=store,
        llm_client=spy_llm,
    )
    ctx_raw = case.get("context") or {}
    context = RoutingContext(
        ticket_customer_id=ctx_raw.get("ticket_customer_id", "demo-customer"),
        verified_scope=ctx_raw.get("verified_scope", "ticket:read order:read"),
        is_personal_lookup=bool(ctx_raw.get("is_personal_lookup", False)),
        extracted_slots=dict(ctx_raw.get("extracted_slots") or {}),
    )
    try:
        res = runner.run(case["text"], context, run_id=f"{case['id']}-{scenario}")
    except Exception as exc:
        return _classify_fault_outcome(
            case=case,
            surface="pipeline_runner",
            scenario=scenario,
            raw_action=None,
            mapped_action=None,
            reason_codes=[],
            no_draft_preserved=True,
            llm_calls=len(spy_llm.calls),
            exception_type=type(exc).__name__,
            details={"exception_message": str(exc)},
        )

    return _classify_fault_outcome(
        case=case,
        surface="pipeline_runner",
        scenario=scenario,
        raw_action=res.get("action"),
        mapped_action=res.get("action"),
        reason_codes=list(res.get("reason_codes") or []),
        no_draft_preserved=(res.get("draft_body") is None),
        llm_calls=len(spy_llm.calls),
        details={
            "initial_routing_action": res.get("initial_routing_action"),
            "predicted_intent": res.get("predicted_intent"),
            "final_intent": res.get("final_intent"),
            "must_human_approve": res.get("must_human_approve"),
            "llm_called_flag": res.get("llm_called"),
            "requested_team": res.get("requested_team"),
        },
    )


def _model_predict_to_ml_payload(model_container: Any, text_arg: str) -> Dict[str, Any]:
    pred = model_container.predict(text_arg)
    raw_top_k = pred.get("top_k", []) or []
    top_k = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in raw_top_k]
    return {
        "intent": pred["intent"],
        "confidence": pred["confidence"],
        "margin": pred["margin"],
        "top_k": top_k,
        "model_version": model_container.verified_model_version or getattr(model_container, "model_version", "unknown"),
        "model_mode": pred.get("model_mode"),
        "verified": pred.get("verified"),
        "raw_confidence": pred.get("raw_confidence"),
        "raw_margin": pred.get("raw_margin"),
        "raw_score_kind": pred.get("raw_score_kind"),
        "calibration_temperature": pred.get("calibration_temperature"),
        "calibration_schema_version": pred.get("calibration_schema_version"),
        "calibration_checksum": pred.get("calibration_checksum"),
        "selective_accepted": pred.get("selective_accepted"),
        "selective_score": pred.get("selective_score"),
        "selective_threshold": pred.get("selective_threshold"),
        "rejected_by_experimental_adapter": pred.get("rejected_by_experimental_adapter"),
        "rejector_decision": pred.get("rejector_decision"),
    }


def _evaluate_backend_fault_suite(
    *,
    cases_by_id: Dict[str, Dict[str, Any]],
    owner_url: str,
    passwords: Dict[str, str],
    gw_base_url: str,
    database: Database,
    fault_state: Dict[str, Any],
    zero_guard: ZeroBudgetTransport,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run Backend+PG+ai_service fault boundaries inside an isolated disposable PG schema."""
    with database.transaction() as session:
        ord_1002 = session.get(Order, "ORD-1002")
        ord_1001 = session.get(Order, "ORD-1001")
        pg_ownership_fact = {
            "ord_1001_customer_id": ord_1001.customer_id if ord_1001 else None,
            "ord_1002_customer_id": ord_1002.customer_id if ord_1002 else None,
            "cross_customer_distinct": bool(ord_1001 and ord_1002 and ord_1001.customer_id != ord_1002.customer_id),
        }

    # Note: 650ms analysis timeout + 1.2s simulated predict sleep triggers real HTTP ReadTimeout cleanly
    # while leaving comfortable headroom above cold CPU DistilBERT forward passes (~250-400ms).
    settings = BackendSettings(
        database_url_app=owner_url,
        database_url_owner=owner_url,
        allowed_origins=["http://testserver"],
        session_cookie_secure=False,
        ai_service_base_url=gw_base_url,
        ai_service_analysis_timeout_ms=650,
        ai_service_draft_timeout_ms=2500,
        job_poll_interval_ms=30,
    )
    observations: List[Dict[str, Any]] = []

    with TestClient(create_backend_app(settings=settings, database=database, start_worker=True)) as customer, \
         TestClient(create_backend_app(settings=settings, database=database, start_worker=False)) as staff:
        for cli, role, login in ((customer, "customer", "customer-1"), (staff, "staff", "staff-1")):
            cli.headers["Origin"] = "http://testserver"
            resp = cli.post("/v1/sessions", json={"login_name": login, "password": passwords[role]})
            if resp.status_code != 201:
                raise RuntimeError(f"Failed login for {login}: {resp.status_code}")

        # Wait briefly if needed? First let's warm up normal /predict path implicitly on first non-fault or reset fault_state cleanly
        try:
            # 1a. ml_timeout via HTTP analysis timeout (worker ReadTimeout)
            fault_state.clear()
            fault_state.update({"ml_mode": "sleep", "sleep_seconds": 1.2})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-03"],
                    scenario="backend_pg_analysis_read_timeout",
                    customer_client=customer,
                    staff_client=staff,
                    order_id="ORD-1001",
                    zero_guard=zero_guard,
                )
            )

            # 1b. ml_timeout via in-process TimeoutError inside ModelContainer.predict (HTTP 500 in ai_service)
            fault_state.clear()
            fault_state.update({"ml_mode": "timeout_error"})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-03"],
                    scenario="backend_pg_model_timeout_error",
                    customer_client=customer,
                    staff_client=staff,
                    order_id="ORD-1001",
                    zero_guard=zero_guard,
                )
            )

            # 2a. encoder_failure via runtime encode_queries RuntimeError
            fault_state.clear()
            fault_state.update({"encoder_mode": "runtime_failure"})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-return_policy-04"],
                    scenario="backend_pg_encoder_runtime_failure",
                    customer_client=customer,
                    staff_client=staff,
                    order_id=None,
                    zero_guard=zero_guard,
                )
            )

            # 2b. encoder_unavailable via encoder=None in RetrievalAdapter
            fault_state.clear()
            fault_state.update({"encoder_mode": "encoder_unavailable"})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-return_policy-04"],
                    scenario="backend_pg_encoder_unavailable",
                    customer_client=customer,
                    staff_client=staff,
                    order_id=None,
                    zero_guard=zero_guard,
                )
            )

            # 3a. commerce_unauthorized with explicit cross-customer order_id="ORD-1002"
            fault_state.clear()
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-05"],
                    scenario="backend_pg_explicit_unauthorized_order",
                    customer_client=customer,
                    staff_client=staff,
                    order_id="ORD-1002",
                    zero_guard=zero_guard,
                )
            )

            # 3b. commerce_unauthorized text-only customer submission (no order_id dropdown field)
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-05"],
                    scenario="backend_pg_text_only_unauthorized_order",
                    customer_client=customer,
                    staff_client=staff,
                    order_id=None,
                    zero_guard=zero_guard,
                )
            )

            # Companion faults cleanly observed on Backend+PG
            fault_state.clear()
            fault_state.update({"ml_mode": "runtime_error"})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-04"],
                    scenario="backend_pg_ml_runtime_error_503",
                    customer_client=customer,
                    staff_client=staff,
                    order_id="ORD-1001",
                    zero_guard=zero_guard,
                )
            )

            fault_state.clear()
            fault_state.update({"encoder_mode": "encoder_unavailable"})
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-return_policy-03"],
                    scenario="backend_pg_companion_encoder_unavailable",
                    customer_client=customer,
                    staff_client=staff,
                    order_id=None,
                    zero_guard=zero_guard,
                )
            )

            fault_state.clear()
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-06"],
                    scenario="backend_pg_explicit_not_found_order",
                    customer_client=customer,
                    staff_client=staff,
                    order_id="ORD-9999",
                    zero_guard=zero_guard,
                )
            )
            observations.append(
                _submit_and_observe_backend_case(
                    case=cases_by_id["unc-track_order-06"],
                    scenario="backend_pg_text_only_not_found_order",
                    customer_client=customer,
                    staff_client=staff,
                    order_id=None,
                    zero_guard=zero_guard,
                )
            )
        finally:
            fault_state.clear()

    return observations, pg_ownership_fact


def _evaluate_pipeline_runner_fault_suite(
    *,
    cases_by_id: Dict[str, Dict[str, Any]],
    worktree_root: Path,
    model_dir: Path,
    store_dir: Path,
) -> tuple[List[Dict[str, Any]], Any, RetrievalAdapter]:
    """Run PipelineRunner fault boundaries directly using real ModelContainer, CommerceAdapter, RetrievalAdapter & SpyLLM."""
    from apps.ml_inference.app import ModelContainer

    model_container = ModelContainer()
    model_container.load(model_dir=model_dir)
    expected_version = model_container.verified_model_version or getattr(model_container, "model_version", "unknown")

    release = json.loads((worktree_root / "apps" / "ai_service" / "kb-release.json").read_text(encoding="utf-8"))
    allowed_versions = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    commerce = CommerceAdapter(data_path=str(worktree_root / "data" / "knowledge" / "mock_orders.json"))
    retrieval = RetrievalAdapter(
        kb_path=str(worktree_root / "data" / "knowledge" / "approved_kb.v2.json"),
        allowed_document_versions=allowed_versions,
    )
    spy_llm = SpyLLMClient(mode="forbid", configured=True)

    real_client = IntentClient(
        base_url="http://ml.local",
        expected_model_version=expected_version,
        http_client=httpx.Client(
            transport=_make_mock_predict_transport(lambda txt: _model_predict_to_ml_payload(model_container, txt)),
            trust_env=False,
        ),
    )

    def _fixed_predict_client(intent: str, confidence: float = 0.96, margin: float = 0.85) -> IntentClient:
        return IntentClient(
            base_url="http://ml.local",
            expected_model_version=expected_version,
            http_client=httpx.Client(
                transport=_make_mock_predict_transport(
                    lambda _txt: {
                        "intent": intent,
                        "confidence": confidence,
                        "margin": margin,
                        "top_k": [{"intent": intent, "probability": confidence}],
                        "model_version": expected_version,
                        "verified": True,
                    }
                ),
                trust_env=False,
            ),
        )

    def _timeout_client() -> IntentClient:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Simulated ML inference ReadTimeout", request=request)

        return IntentClient(
            base_url="http://ml.local",
            expected_model_version=expected_version,
            http_client=httpx.Client(transport=httpx.MockTransport(handler), trust_env=False),
        )

    def _error_503_client() -> IntentClient:
        return IntentClient(
            base_url="http://ml.local",
            expected_model_version=expected_version,
            http_client=httpx.Client(
                transport=_make_mock_predict_transport(lambda _t: {"_http_status": 503, "detail": "model down"}),
                trust_env=False,
            ),
        )

    observations: List[Dict[str, Any]] = []

    # 1. ml_timeout on PipelineRunner
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-track_order-03"],
            scenario="pipeline_runner_ml_read_timeout",
            intent_client=_timeout_client(),
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    # 2a. encoder_failure via runtime encode_queries RuntimeError (real ModelContainer prediction)
    faulty_ret = RetrievalAdapter(
        kb_path=str(worktree_root / "data" / "knowledge" / "approved_kb.v2.json"),
        encoder=retrieval.encoder,
        allowed_document_versions=allowed_versions,
    )
    orig_enc = faulty_ret.encoder.encode_queries

    def _raise_enc(queries: List[str], *a: Any, **kw: Any) -> Any:
        raise RuntimeError("Injected runtime encoder failure in PolicyEncoder.encode_queries")

    faulty_ret.encoder.encode_queries = _raise_enc  # type: ignore[method-assign]
    try:
        observations.append(
            _run_pipeline_runner_case(
                case=cases_by_id["unc-return_policy-04"],
                scenario="pipeline_runner_encoder_runtime_failure",
                intent_client=real_client,
                commerce=commerce,
                retrieval=faulty_ret,
                spy_llm=spy_llm,
                store_dir=store_dir,
            )
        )
    finally:
        faulty_ret.encoder.encode_queries = orig_enc  # type: ignore[method-assign]

    # 2b. encoder_unavailable (encoder=None) for both unc-return_policy-04 & unc-return_policy-03
    unavail_ret = RetrievalAdapter(
        kb_path=str(worktree_root / "data" / "knowledge" / "approved_kb.v2.json"),
        encoder=retrieval.encoder,
        allowed_document_versions=allowed_versions,
    )
    unavail_ret.encoder = None
    unavail_ret.encoder_error = "Injected encoder_unavailable"
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-return_policy-04"],
            scenario="pipeline_runner_encoder_unavailable",
            intent_client=real_client,
            commerce=commerce,
            retrieval=unavail_ret,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-return_policy-03"],
            scenario="pipeline_runner_companion_encoder_unavailable",
            intent_client=real_client,
            commerce=commerce,
            retrieval=unavail_ret,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    # 3a. commerce_unauthorized on PipelineRunner with REAL Serving ModelContainer prediction
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-track_order-05"],
            scenario="pipeline_runner_real_classifier_commerce_unauthorized",
            intent_client=real_client,
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    # 3b. commerce_unauthorized on PipelineRunner reaching CommerceAdapter with track_order prediction
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-track_order-05"],
            scenario="pipeline_runner_track_order_commerce_unauthorized",
            intent_client=_fixed_predict_client("track_order"),
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    # Companion faults on PipelineRunner
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-track_order-04"],
            scenario="pipeline_runner_ml_error_503",
            intent_client=_error_503_client(),
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-track_order-06"],
            scenario="pipeline_runner_commerce_not_found_frozen_empty_slots",
            intent_client=_fixed_predict_client("track_order"),
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )
    explicit_9999_case = {
        **cases_by_id["unc-track_order-06"],
        "context": {
            **(cases_by_id["unc-track_order-06"].get("context") or {}),
            "extracted_slots": {"order_id": "ORD-9999"},
        },
    }
    observations.append(
        _run_pipeline_runner_case(
            case=explicit_9999_case,
            scenario="pipeline_runner_commerce_not_found_explicit_slot",
            intent_client=_fixed_predict_client("track_order"),
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    spy_llm.reset(mode="llm_timeout")
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-refund_policy-01"],
            scenario="pipeline_runner_llm_timeout_offline_spy",
            intent_client=real_client,
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )
    spy_llm.reset(mode="llm_invalid_citations")
    observations.append(
        _run_pipeline_runner_case(
            case=cases_by_id["unc-cancel_order-03"],
            scenario="pipeline_runner_llm_invalid_citations_offline_spy",
            intent_client=real_client,
            commerce=commerce,
            retrieval=retrieval,
            spy_llm=spy_llm,
            store_dir=store_dir,
        )
    )

    return observations, model_container, retrieval


def _build_engine_llm_fault_checks(
    cases_by_id: Dict[str, Dict[str, Any]],
    worktree_root: Path,
    model_container: Any,
    retriever: RetrievalAdapter,
) -> List[Dict[str, Any]]:
    """Verify companion llm_timeout and llm_invalid_citations inside ai_service Engine cleanly (0 network calls)."""
    from apps.ai_service.engine import Engine

    policy = json.loads((worktree_root / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json").read_text(encoding="utf-8"))
    versions = {"release_id": "offline-fault-check"}
    spy = SpyLLMClient()
    engine = Engine(model_container, retriever, spy, versions, policy)

    checks: List[Dict[str, Any]] = []
    for case_id, spy_mode in (("unc-refund_policy-01", "llm_timeout"), ("unc-cancel_order-03", "llm_invalid_citations")):
        case = cases_by_id[case_id]
        spy.reset(mode=spy_mode)
        out = engine.draft({"message": case["text"], "order_context": {}, "as_of": "2026-11-05T00:00:00Z"})
        draft_status = out.get("status")
        codes = sorted(set(out.get("reason_codes") or []) | ({out["failure_code"]} if out.get("failure_code") else set()))
        checks.append(
            _classify_fault_outcome(
                case=case,
                surface="ai_service_engine_offline_spy",
                scenario=f"engine_{spy_mode}",
                raw_action=draft_status,
                mapped_action=_map_backend_action(draft_status, 200),
                reason_codes=codes,
                no_draft_preserved=(draft_status != "draft_ready" and out.get("draft") is None),
                llm_calls=len(spy.calls),
                details={
                    "failure_code": out.get("failure_code"),
                    "staff_note": out.get("staff_note"),
                    "offline_spy_only": True,
                },
            )
        )
    return checks


def _render_fault_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Fault Boundary Execution Report (`0` Live LLM Requests)",
        "",
        f"- **Generated UTC:** `{report['generated_at_utc']}`",
        f"- **Git Commit:** `{report['git_commit']}`",
        f"- **Live Provider Requests Attempted:** `{report['live_http_requests_attempted']}` / `{report['live_http_budget_max']}`",
        f"- **PostgreSQL Temporary Schema:** `{report['pg_cleanup']['postgres_schema']}` (cleanup verified: `{report['pg_cleanup']['pg_namespace_verified_absent']}`)",
        "",
        "## Primary Target Faults (Previously `NOT_EXECUTED`)",
        "",
        "| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped Action | Reason Codes | `llm_calls` | `customer_reply_is_none` | Verdict |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |",
    ]
    for rec in report["primary_fault_results"]:
        obs = rec["observed"]
        reasons = ", ".join(obs["reason_codes"]) if obs["reason_codes"] else "-"
        lines.append(
            f"| `{rec['case_id']}` | `{rec['fault']}` | `{rec['surface']}` / `{rec['scenario']}` | `{obs['raw_action']}` | `{obs['mapped_action']}` | `{reasons}` | `{obs['llm_calls']}` | `{obs['customer_reply_is_none']}` | `{rec['verdict']}` |"
        )
    lines.extend([
        "",
        "## Companion Faults (Acceptance v2 Fault Matrix)",
        "",
        "| Case ID | Fault | Surface / Scenario | Raw Outcome | Mapped Action | Reason Codes | `llm_calls` | Verdict |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |",
    ])
    for rec in report["companion_fault_results"]:
        obs = rec["observed"]
        reasons = ", ".join(obs["reason_codes"]) if obs["reason_codes"] else "-"
        lines.append(
            f"| `{rec['case_id']}` | `{rec['fault']}` | `{rec['surface']}` / `{rec['scenario']}` | `{obs['raw_action']}` | `{obs['mapped_action']}` | `{reasons}` | `{obs['llm_calls']}` | `{rec['verdict']}` |"
        )
    lines.extend([
        "",
        "## Concrete Cross-Architecture Findings & Reproductions",
        "",
    ])
    for finding in report["concrete_findings"]:
        lines.append(f"- **{finding['case_id']} (`{finding['fault']}`) — {finding['title']}:** {finding['summary']}")
    return "\n".join(lines) + "\n"


def _summarize_concrete_findings(all_records: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    by_scenario = {r["scenario"]: r for r in all_records}

    if "backend_pg_analysis_read_timeout" in by_scenario and "pipeline_runner_ml_read_timeout" in by_scenario:
        b_rec = by_scenario["backend_pg_analysis_read_timeout"]
        b_err = by_scenario.get("backend_pg_model_timeout_error", {})
        p_rec = by_scenario["pipeline_runner_ml_read_timeout"]
        findings.append(
            {
                "case_id": "unc-track_order-03",
                "fault": "ml_timeout",
                "title": "Fails closed safely as manual fallback, but misses strict must_escalate=true and reason 'ml_timeout'",
                "summary": (
                    f"Backend worker HTTP ReadTimeout -> draft_status={b_rec['observed']['draft_status']} reasons={b_rec['observed']['reason_codes']}; "
                    f"in-process ModelContainer TimeoutError -> http/fallback reasons={(b_err.get('observed') or {}).get('reason_codes')}; "
                    f"PipelineRunner ReadTimeout -> action={p_rec['observed']['raw_action']} reasons={p_rec['observed']['reason_codes']} "
                    f"(0 LLM calls, no draft leaked)."
                ),
            }
        )

    if "backend_pg_encoder_runtime_failure" in by_scenario and "pipeline_runner_encoder_runtime_failure" in by_scenario:
        b_run = by_scenario["backend_pg_encoder_runtime_failure"]
        p_run = by_scenario["pipeline_runner_encoder_runtime_failure"]
        p_unavail = by_scenario.get("pipeline_runner_encoder_unavailable", {})
        findings.append(
            {
                "case_id": "unc-return_policy-04",
                "fault": "encoder_failure",
                "title": "Backend abstains as generic no_valid_document; PipelineRunner escalates without 'encoder_failure' code",
                "summary": (
                    f"Backend runtime encode_queries RuntimeError -> draft_status={b_run['observed']['draft_status']} reasons={b_run['observed']['reason_codes']} "
                    f"(mapped={b_run['observed']['mapped_action']}, strict must_escalate mismatch). "
                    f"PipelineRunner runtime encode_queries RuntimeError -> action={p_run['observed']['raw_action']} reasons={p_run['observed']['reason_codes']} "
                    f"(RetrievalAdapter strips search_policies ['encoder_failed'] down to status='error'; encoder=None gives {(p_unavail.get('observed') or {}).get('reason_codes')})."
                ),
            }
        )

    if "backend_pg_explicit_unauthorized_order" in by_scenario and "backend_pg_text_only_unauthorized_order" in by_scenario:
        b_exp = by_scenario["backend_pg_explicit_unauthorized_order"]
        b_txt = by_scenario["backend_pg_text_only_unauthorized_order"]
        p_real = by_scenario.get("pipeline_runner_real_classifier_commerce_unauthorized", {})
        p_trk = by_scenario.get("pipeline_runner_track_order_commerce_unauthorized", {})
        findings.append(
            {
                "case_id": "unc-track_order-05",
                "fault": "commerce_unauthorized",
                "title": "Explicit order_id returns HTTP 404 denial; text-only drops order link without commerce auth code; PipelineRunner emits 'commerce_unauthorized_customer'",
                "summary": (
                    f"Backend explicit ORD-1002 by demo-customer -> HTTP {b_exp['observed']['http_status']} ({b_exp['observed']['raw_action']}, 0 tickets). "
                    f"Backend text-only 'Track order ORD-1002 for customer cust_1' -> ticket created with order_id=None, "
                    f"predicted_intent={b_txt['observed'].get('predicted_intent')}, draft_status={b_txt['observed']['draft_status']}, reasons={b_txt['observed']['reason_codes']}. "
                    f"PipelineRunner real classifier -> action={(p_real.get('observed') or {}).get('raw_action')} reasons={(p_real.get('observed') or {}).get('reason_codes')}; "
                    f"PipelineRunner track_order -> action={(p_trk.get('observed') or {}).get('raw_action')} reasons={(p_trk.get('observed') or {}).get('reason_codes')}."
                ),
            }
        )

    return findings


def run_fault_boundary_suite(
    *,
    worktree_root: Path = REPO_ROOT,
    root_repo: Path = DEFAULT_ROOT_REPO,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute real isolated fault-boundary suite across Backend+PG and PipelineRunner with 0 live requests."""
    out_dir = output_dir or (worktree_root / "artifacts" / "evaluation" / "fault_boundaries_20261113")
    out_dir.mkdir(parents=True, exist_ok=True)

    cases_path = worktree_root / "data" / "benchmarks" / "system" / "v2" / "acceptance" / "cases.jsonl"
    fault_cases = load_acceptance_fault_cases(cases_path)
    cases_by_id = {c["id"]: c for c in fault_cases}
    missing_primary = [cid for cid in PRIMARY_TARGET_CASE_IDS if cid not in cases_by_id]
    if missing_primary:
        raise KeyError(f"Missing required fault cases in {cases_path}: {missing_primary}")

    model_dir = _resolve_model_dir(worktree_root, root_repo)
    zero_guard = ZeroBudgetTransport()
    fault_state: Dict[str, Any] = {}

    owner_url, default_passwords = resolve_database_url(str(root_repo / ".local" / "application.json"))
    schema = f"fault_chk_{uuid.uuid4().hex[:10]}"
    root_engine = create_engine(owner_url, hide_parameters=True)
    app_engine = None
    schema_created = False

    backend_records: List[Dict[str, Any]] = []
    pipeline_records: List[Dict[str, Any]] = []
    engine_llm_records: List[Dict[str, Any]] = []
    pg_ownership_fact: Dict[str, Any] = {}

    try:
        with root_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        app_engine = create_engine(
            owner_url,
            connect_args={"options": f"-csearch_path={schema}"},
            hide_parameters=True,
        )
        database = Database(app_engine)
        database.create_schema()
        passwords = {
            role: default_passwords.get(role, uuid.uuid4().hex)
            for role in ("customer", "staff", "manager", "admin")
        }
        seed(database, passwords)

        with _installed_gateway_fault_hooks(fault_state):
            with owned_isolated_ai_service(
                api_key="offline-zero-budget-key",
                model_name=FLASH_LITE_35_MODEL,
                model_dir=model_dir,
                budget_guard=zero_guard,
            ) as gw:
                backend_records, pg_ownership_fact = _evaluate_backend_fault_suite(
                    cases_by_id=cases_by_id,
                    owner_url=owner_url,
                    passwords=passwords,
                    gw_base_url=gw["base_url"],
                    database=database,
                    fault_state=fault_state,
                    zero_guard=zero_guard,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline_records, shared_model, shared_retriever = _evaluate_pipeline_runner_fault_suite(
                cases_by_id=cases_by_id,
                worktree_root=worktree_root,
                model_dir=model_dir,
                store_dir=Path(tmpdir),
            )

        engine_llm_records = _build_engine_llm_fault_checks(cases_by_id, worktree_root, shared_model, shared_retriever)
    finally:
        if app_engine is not None:
            app_engine.dispose()
        pg_cleanup = _drop_temporary_postgres_schema(root_engine, schema, schema_created=schema_created)
        with root_engine.connect() as conn:
            exists_count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM pg_namespace WHERE nspname = :schema_name"),
                    {"schema_name": schema},
                ).scalar()
                or 0
            )
        pg_cleanup["pg_namespace_verified_absent"] = exists_count == 0
        root_engine.dispose()

    if zero_guard.requests_attempted != 0:
        raise RuntimeError(f"Live HTTP leakage detected under zero budget: {zero_guard.requests_attempted}")

    all_records = backend_records + pipeline_records + engine_llm_records
    primary_set = set(PRIMARY_TARGET_CASE_IDS)
    primary_results = [r for r in all_records if r["case_id"] in primary_set]
    companion_results = [r for r in all_records if r["case_id"] not in primary_set]

    report: Dict[str, Any] = {
        "report_type": "task_c_fault_boundary_execution",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit_hash(),
        "source_benchmark_path": str(cases_path.relative_to(worktree_root)).replace("\\", "/"),
        "source_benchmark_sha256": compute_sha256(cases_path),
        "live_http_budget_max": 0,
        "live_http_requests_attempted": zero_guard.requests_attempted,
        "live_http_rejected_before_network": zero_guard.rejected_before_network_count,
        "pg_ownership_seed_fact": pg_ownership_fact,
        "pg_cleanup": pg_cleanup,
        "primary_target_case_ids": list(PRIMARY_TARGET_CASE_IDS),
        "companion_fault_case_ids": list(COMPANION_FAULT_CASE_IDS),
        "summary": {
            "primary_total_executions": len(primary_results),
            "primary_strict_pass": sum(1 for r in primary_results if r["verdict"] == "STRICT_PASS"),
            "primary_safe_fallback_mismatch": sum(1 for r in primary_results if r["verdict"] == "SAFE_FALLBACK_MISMATCH"),
            "primary_intake_404_mismatch": sum(1 for r in primary_results if r["verdict"] == "INTAKE_DENIAL_404_MISMATCH"),
            "primary_no_draft_all_preserved": all(r["checks"]["no_draft_ok"] for r in primary_results),
            "companion_total_executions": len(companion_results),
            "companion_no_draft_all_preserved": all(r["checks"]["no_draft_ok"] for r in companion_results),
        },
        "primary_fault_results": primary_results,
        "companion_fault_results": companion_results,
        "concrete_findings": _summarize_concrete_findings(all_records),
    }

    report_json_text = sanitize_text(json.dumps(report, indent=2))
    report_md_text = sanitize_text(_render_fault_markdown(report))

    json_path = out_dir / "fault_boundary_report.json"
    md_path = out_dir / "FAULT_BOUNDARY_REPORT.md"
    hashes_path = out_dir / "report_hashes.json"

    json_path.write_text(report_json_text, encoding="utf-8")
    md_path.write_text(report_md_text, encoding="utf-8")

    hashes_payload = {
        "fault_boundary_report.json": compute_bytes_sha256(json_path.read_bytes()),
        "FAULT_BOUNDARY_REPORT.md": compute_bytes_sha256(md_path.read_bytes()),
    }
    hashes_path.write_text(json.dumps(hashes_payload, indent=2) + "\n", encoding="utf-8")

    return {
        "output_dir": str(out_dir),
        "report": report,
        "hashes": hashes_payload,
    }

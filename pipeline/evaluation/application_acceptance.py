"""Application End-to-End Acceptance Runner (Task B3).

Exercises real application boundaries:
  ticket submit -> leased PostgreSQL background worker -> terminal AI state
Measures p50/p95 latency, error counts, warm vs cold conditions,
token and verified cost coverage, and verifies the 100% human oversight invariant
(unreviewed draft never automatically sent to customer).
Operates strictly in isolated disposable schemas and avoids destructive resets.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import math
import os
import platform
import secrets
import socketserver
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.seed import seed
from scripts.native_runtime import configure_runtime_environment


def compute_sha256(path: Path | str) -> str:
    """Compute uppercase SHA-256 of file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def get_git_commit_hash() -> str:
    """Safely obtain current git commit hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown_or_detached"


class MockAIHandler(http.server.BaseHTTPRequestHandler):
    """Mock AI gateway server for deterministic offline acceptance testing."""

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        server_mode = getattr(self.server, "mode", "normal")

        if server_mode == "error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail": "Internal AI service failure"}')
            return

        if server_mode == "timeout":
            time.sleep(3.5)  # Longer than analysis timeout
            self.send_response(504)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail": "AI service timeout"}')
            return

        path = self.path
        if "/analyses" in path:
            if server_mode == "abstain":
                res = {
                    "intent": {"label": "unknown", "probability": 0.45, "confidence_band": "low"},
                    "routing": {"recommendation": "abstain", "reason_codes": ["low_confidence"], "action": "clarify", "requested_team": "general_support"},
                    "alternatives": [],
                    "documents": [],
                    "warnings": ["low_confidence"],
                    "versions": {"release_id": "rel-v2", "model_version": "v1.0.0", "kb_version": "v2.0"},
                    "step_latency_ms": {"classify_ms": 10, "route_ms": 1, "retrieve_ms": 5},
                }
            elif server_mode == "escalate":
                res = {
                    "intent": {"label": "cancel_order", "probability": 0.95, "confidence_band": "high"},
                    "routing": {"recommendation": "escalate", "reason_codes": ["requires_authority"], "action": "escalate", "requested_team": "order_support"},
                    "alternatives": [],
                    "documents": [{"doc_id": "POL-ORD-01", "version": "v2.0", "title": "Cancellation Policy", "snippet": "Order cancellation requires authorization"}],
                    "warnings": [],
                    "versions": {"release_id": "rel-v2", "model_version": "v1.0.0", "kb_version": "v2.0"},
                    "step_latency_ms": {"classify_ms": 12, "route_ms": 2, "retrieve_ms": 15},
                }
            else:
                res = {
                    "intent": {"label": "return_policy", "probability": 0.96, "confidence_band": "high"},
                    "routing": {"recommendation": "draft", "reason_codes": [], "action": "retrieve_draft", "requested_team": "returns_support"},
                    "alternatives": [],
                    "documents": [{"doc_id": "POL-RET-01", "version": "v2.0", "title": "Return Policy", "snippet": "Returns accepted within 30 days"}],
                    "warnings": [],
                    "versions": {"release_id": "rel-v2", "model_version": "v1.0.0", "kb_version": "v2.0"},
                    "step_latency_ms": {"classify_ms": 15, "route_ms": 2, "retrieve_ms": 25},
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if "/drafts" in path:
            res = {
                "status": "draft_ready",
                "reason_codes": [],
                "analysis": {
                    "intent": {"label": "return_policy", "probability": 0.96, "confidence_band": "high"},
                    "routing": {"recommendation": "draft", "reason_codes": [], "action": "retrieve_draft", "requested_team": "returns_support"},
                    "alternatives": [],
                    "documents": [{"doc_id": "POL-RET-01", "version": "v2.0", "title": "Return Policy", "snippet": "Returns accepted within 30 days"}],
                    "warnings": [],
                    "versions": {"release_id": "rel-v2", "model_version": "v1.0.0", "kb_version": "v2.0"},
                    "step_latency_ms": {"classify_ms": 15, "route_ms": 2, "retrieve_ms": 25},
                },
                "draft": {
                    "segments": [
                        {"paragraph_index": 0, "text": "Our standard policy permits returns within 30 days of purchase for a full refund."}
                    ],
                    "citations": [
                        {"source_type": "document", "doc_id": "POL-RET-01", "version": "v2.0", "field": "policy_body", "span": "within 30 days"}
                    ],
                },
                "step_latency_ms": {"analysis_ms": 42, "draft_ms": 180, "llm_ms": 150},
                "llm_usage": {"input_tokens": 128, "output_tokens": 42, "thinking_tokens": 0, "total_tokens": 170},
                "versions": {"release_id": "rel-v2", "model_version": "v1.0.0", "llm_model": "mock-eval-llm"},
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


class EphemeralMockAIServer:
    """Spins up an ephemeral loopback mock AI server in a daemon thread."""

    def __init__(self, mode: str = "normal"):
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), MockAIHandler)
        self.server.mode = mode
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def set_mode(self, mode: str):
        self.server.mode = mode

    def start(self):
        self.thread.start()

    def stop(self):
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.server.server_close()
        except Exception:
            pass


@dataclass
class TicketCaseResult:
    case_index: int
    condition: str  # "cold" or "warm"
    message: str
    ticket_id: Optional[str]
    wall_latency_ms: Optional[float]
    analysis_status: str
    draft_status: str
    customer_reply_is_none: bool  # Safety invariant check
    step_latency_ms: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, Any] = field(default_factory=dict)
    llm_model: Optional[str] = None
    versions: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    is_terminal: bool = False
    is_success: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_index": self.case_index,
            "condition": self.condition,
            "message": self.message,
            "ticket_id": self.ticket_id,
            "wall_latency_ms": self.wall_latency_ms,
            "analysis_status": self.analysis_status,
            "draft_status": self.draft_status,
            "reply_is_none": self.customer_reply_is_none,
            "step_latency_ms": self.step_latency_ms,
            "tokens": self.tokens,
            "llm_model": self.llm_model,
            "versions": self.versions,
            "error_code": self.error_code,
            "is_terminal": self.is_terminal,
            "is_success": self.is_success,
        }


@dataclass
class ApplicationAcceptanceConfig:
    secrets_path: Optional[str] = None
    mode: str = "mock"  # "mock" or "live"
    live_ai_url: Optional[str] = None
    num_warm_requests: int = 4
    poll_timeout_seconds: float = 25.0
    analysis_timeout_ms: int = 3_000   # Declared runtime-comparable timeout default
    draft_timeout_ms: int = 11_000     # Declared runtime-comparable timeout default
    verified_pricing: Optional[Dict[str, Any]] = None


def resolve_database_url(secrets_path: Optional[str] = None) -> Tuple[str, Dict[str, str]]:
    """Resolve owner database URL respecting SUPPORTIQ_APPLICATION_SECRETS, explicit path, or local fallback.

    Removes any coordinator-drive hardcoded fallback.
    """
    candidates: List[Path] = []

    # 1. Environment variable SUPPORTIQ_APPLICATION_SECRETS
    env_secrets = os.environ.get("SUPPORTIQ_APPLICATION_SECRETS")
    if env_secrets:
        trimmed = env_secrets.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if "database_url_owner" in data:
                    return data["database_url_owner"], data.get("passwords", {})
            except Exception:
                pass
        else:
            candidates.append(Path(trimmed))

    # 2. Explicit secrets_path argument
    if secrets_path:
        candidates.append(Path(secrets_path))

    # 3. Worktree-local application.json
    candidates.append(Path(".local/application.json"))

    for cand in candidates:
        if cand.exists():
            try:
                local = json.loads(cand.read_text(encoding="utf-8"))
                if "database_url_owner" in local:
                    return local["database_url_owner"], local.get("passwords", {})
            except Exception:
                pass

    raise RuntimeError(
        "Could not find valid database_url_owner. Set SUPPORTIQ_APPLICATION_SECRETS or ensure .local/application.json exists."
    )


def validate_pricing_rates(pricing: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate that pricing rates are finite positive numbers (not boolean, NaN, Inf, or <= 0)."""
    in_rate = pricing.get("input_cost_per_million")
    out_rate = pricing.get("output_cost_per_million")

    if isinstance(in_rate, bool) or isinstance(out_rate, bool):
        return False, "Rates cannot be boolean values"
    if not (isinstance(in_rate, (int, float)) and isinstance(out_rate, (int, float))):
        return False, "Rates must be numeric values"
    if not (math.isfinite(in_rate) and math.isfinite(out_rate)):
        return False, "Rates must be finite numbers (not NaN or Inf)"
    if in_rate <= 0 or out_rate <= 0:
        return False, "Rates must be positive numbers"

    return True, None


class ApplicationAcceptanceRunner:
    """Executes end-to-end application acceptance testing with isolated schemas."""

    def __init__(self, config: ApplicationAcceptanceConfig):
        self.config = config

    def run(self, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        configure_runtime_environment()
        owner_url, default_passwords = resolve_database_url(self.config.secrets_path)

        schema = "accept_" + uuid.uuid4().hex[:12]
        root_engine = None
        schema_created = False
        mock_server = None
        app_engine = None

        try:
            root_engine = create_engine(owner_url, hide_parameters=True)
            with root_engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True

            if self.config.mode == "mock":
                mock_server = EphemeralMockAIServer(mode="normal")
                mock_server.start()
                ai_base_url = mock_server.base_url
            else:
                ai_base_url = self.config.live_ai_url or "http://127.0.0.1:8002"

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

            settings = Settings(
                database_url_app=owner_url,
                database_url_owner=owner_url,
                allowed_origins=["http://testserver", "http://127.0.0.1:18080"],
                session_cookie_secure=False,
                ai_service_base_url=ai_base_url,
                ai_service_analysis_timeout_ms=self.config.analysis_timeout_ms,
                ai_service_draft_timeout_ms=self.config.draft_timeout_ms,
                job_poll_interval_ms=50,
            )

            with TestClient(create_app(settings=settings, database=database, start_worker=True)) as customer, \
                 TestClient(create_app(settings=settings, database=database, start_worker=False)) as staff:

                for client, role in ((customer, "customer"), (staff, "staff")):
                    client.headers["Origin"] = "http://testserver"
                    auth_resp = client.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
                    if auth_resp.status_code != 201:
                        raise RuntimeError(f"Failed to authenticate as {role}: {auth_resp.text}")

                test_messages = [
                    "What is your return policy?",
                    "Can I return an item I bought last week?",
                    "How long do I have to make a return?",
                    "Do you offer refunds for returned items?",
                    "What are the return shipping costs?",
                ]
                total_cases = 1 + max(0, self.config.num_warm_requests)
                cases_to_run = (test_messages * ((total_cases // len(test_messages)) + 1))[:total_cases]

                results: List[TicketCaseResult] = []

                for idx, msg in enumerate(cases_to_run):
                    cond = "cold" if idx == 0 else "warm"
                    t0 = time.perf_counter()

                    ticket_resp = customer.post(
                        "/v1/shop/tickets",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json={"message": msg},
                    )

                    if ticket_resp.status_code != 201:
                        results.append(TicketCaseResult(
                            case_index=idx,
                            condition=cond,
                            message=msg,
                            ticket_id=None,
                            wall_latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                            analysis_status="error",
                            draft_status="error",
                            customer_reply_is_none=True,
                            error_code=f"HTTP_{ticket_resp.status_code}",
                            is_terminal=True,
                            is_success=False,
                        ))
                        continue

                    t_id = ticket_resp.json()["ticket_id"]
                    deadline = time.monotonic() + self.config.poll_timeout_seconds
                    reached_terminal = False
                    suggestion_data: Dict[str, Any] = {}

                    while time.monotonic() < deadline:
                        ws_resp = staff.get(f"/v1/console/tickets/{t_id}")
                        if ws_resp.status_code == 200:
                            suggestion_data = ws_resp.json().get("suggestion", {})
                            a_stat = suggestion_data.get("analysis_status", "pending")
                            d_stat = suggestion_data.get("draft_status", "pending")
                            if a_stat != "pending" and d_stat != "pending":
                                reached_terminal = True
                                break
                        time.sleep(0.05)

                    wall_ms = round((time.perf_counter() - t0) * 1000, 2)

                    # Check 100% human oversight invariant: unreviewed draft never reaches customer
                    cust_view = customer.get(f"/v1/shop/tickets/{t_id}").json()
                    customer_reply = cust_view.get("reply")
                    reply_is_none = customer_reply is None

                    a_stat = suggestion_data.get("analysis_status", "timeout" if not reached_terminal else "unknown")
                    d_stat = suggestion_data.get("draft_status", "timeout" if not reached_terminal else "unknown")
                    step_lat = suggestion_data.get("step_latency_ms", {})
                    tokens = suggestion_data.get("llm_usage", {}) or {}
                    versions = suggestion_data.get("versions", {}) or {}
                    observed_model = versions.get("llm_model")

                    success = reached_terminal and d_stat in ("draft_ready", "abstained", "escalation_recommended") and reply_is_none

                    results.append(TicketCaseResult(
                        case_index=idx,
                        condition=cond,
                        message=msg,
                        ticket_id=t_id,
                        wall_latency_ms=wall_ms,
                        analysis_status=a_stat,
                        draft_status=d_stat,
                        customer_reply_is_none=reply_is_none,
                        step_latency_ms=step_lat,
                        tokens=tokens,
                        llm_model=observed_model,
                        versions=versions,
                        error_code=suggestion_data.get("failure_code") or (None if reached_terminal else "timeout"),
                        is_terminal=reached_terminal,
                        is_success=success,
                    ))

                return self._compute_summary(results, output_dir)

        finally:
            if mock_server:
                try:
                    mock_server.stop()
                except Exception:
                    pass
            if app_engine:
                try:
                    app_engine.dispose()
                except Exception:
                    pass
            if root_engine and schema_created:
                try:
                    with root_engine.begin() as conn:
                        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                except Exception:
                    pass
            if root_engine:
                try:
                    root_engine.dispose()
                except Exception:
                    pass

    def _compute_summary(self, results: List[TicketCaseResult], output_dir: Optional[Path]) -> Dict[str, Any]:
        is_mock = (self.config.mode == "mock")
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_id = f"accept-{timestamp_str}-{secrets.token_hex(3)}"
        iso_timestamp = datetime.now(timezone.utc).isoformat()
        git_commit = get_git_commit_hash()

        # Handle empty results / zero measurements: fail closed and reject
        if not results:
            summary_data = {
                "meta": {
                    "run_id": run_id,
                    "timestamp": iso_timestamp,
                    "git_commit": git_commit,
                    "mode": self.config.mode,
                    "status": "rejected_empty_results",
                    "rejection_reason": "No valid measurements or ticket cases were executed.",
                    "evidence_kind": "mock_runner_simulation" if is_mock else "bounded_live",
                    "scope": "end_to_end_application_acceptance",
                    "boundary": "POST /v1/shop/tickets -> PostgreSQL job -> GET /v1/console/tickets/{id} terminal state",
                    "certification_scope": "mock_simulation_only" if is_mock else "bounded_live_run",
                },
                "acceptance_summary": {
                    "runner_checks_passed": False,
                    "overall_passed": False,
                    "mock_only_evaluation": is_mock,
                    "global_production_accepted": False,
                    "total_cases": 0,
                    "successful_cases": 0,
                    "technical_errors": 0,
                    "timeouts": 0,
                    "failed_jobs": 0,
                    "auto_send_violations": 0,
                    "human_oversight_enforced": False,
                },
                "performance": {
                    "p50_seconds": None,
                    "p95_seconds": None,
                    "min_seconds": None,
                    "max_seconds": None,
                    "target_p95_met": False,
                    "target_threshold_seconds": 12.0,
                    "conditions": {
                        "cold": {
                            "count": 0,
                            "latency_seconds": None,
                            "description": "App connection and DB pool cold start only (NOT model cold start)",
                        },
                        "warm": {
                            "count": 0,
                            "p50_seconds": None,
                            "p95_seconds": None,
                            "description": "Subsequent tickets executed on warm connection pool and worker",
                        },
                    },
                },
                "tokens_and_cost": {
                    "total_prompt_tokens": 0,
                    "total_candidate_tokens": 0,
                    "total_thinking_tokens": 0,
                    "total_completion_tokens": 0,
                    "thinking_tracked": False,
                    "all_requests_tracked_thinking": False,
                    "total_tokens": 0,
                    "cost_status": "unavailable",
                    "cost_usd": None,
                    "lower_bound_cost_usd": None,
                    "cost_note": "Empty run; no valid measurements executed.",
                },
                "cases": [],
            }
            if output_dir:
                self._persist_run_artifacts(summary_data, [], output_dir, run_id)
            return summary_data

        valid_latencies = [
            r.wall_latency_ms / 1000.0
            for r in results
            if r.wall_latency_ms is not None and isinstance(r.wall_latency_ms, (int, float)) and math.isfinite(r.wall_latency_ms)
        ]
        latencies_sorted = sorted(valid_latencies)

        cold_lats = [
            r.wall_latency_ms / 1000.0
            for r in results
            if r.condition == "cold" and r.wall_latency_ms is not None and math.isfinite(r.wall_latency_ms)
        ]
        warm_lats = [
            r.wall_latency_ms / 1000.0
            for r in results
            if r.condition == "warm" and r.wall_latency_ms is not None and math.isfinite(r.wall_latency_ms)
        ]

        if latencies_sorted:
            p50 = (latencies_sorted[(len(latencies_sorted) - 1) // 2] + latencies_sorted[len(latencies_sorted) // 2]) / 2.0
            p95_idx = max(0, math.ceil(0.95 * len(latencies_sorted)) - 1)
            p95 = latencies_sorted[p95_idx]
            min_sec = latencies_sorted[0]
            max_sec = latencies_sorted[-1]
        else:
            p50 = None
            p95 = None
            min_sec = None
            max_sec = None

        p50_cold = cold_lats[0] if cold_lats else None
        p95_warm = sorted(warm_lats)[max(0, math.ceil(0.95 * len(warm_lats)) - 1)] if warm_lats else None
        p50_warm = (sorted(warm_lats)[len(warm_lats) // 2]) if warm_lats else None

        technical_errors = sum(1 for r in results if r.analysis_status == "error" or r.draft_status == "error")
        timeouts = sum(1 for r in results if not r.is_terminal or r.analysis_status == "timeout")
        failed_jobs = sum(1 for r in results if r.draft_status in ("failed", "unavailable"))
        auto_send_violations = sum(1 for r in results if not r.customer_reply_is_none)

        # Per-request token inspection supporting output_tokens alias and tracking thinking coverage
        total_prompt_tokens = 0
        total_candidate_tokens = 0
        total_thinking_tokens = 0
        draft_requests_count = 0
        drafts_with_complete_thinking = 0
        observed_models: set[str] = set()

        for r in results:
            tok = r.tokens or {}
            # Prompt / Input tokens
            p_tok = tok.get("prompt_tokens") if tok.get("prompt_tokens") is not None else tok.get("input_tokens", 0)
            if isinstance(p_tok, (int, float)) and not isinstance(p_tok, bool) and math.isfinite(p_tok):
                total_prompt_tokens += int(p_tok)

            # Candidate / Output tokens (supporting output_tokens alias alongside candidate_tokens and completion_tokens)
            c_tok = None
            for alias in ("candidate_tokens", "output_tokens", "completion_tokens"):
                if tok.get(alias) is not None:
                    c_tok = tok[alias]
                    break
            if c_tok is not None and isinstance(c_tok, (int, float)) and not isinstance(c_tok, bool) and math.isfinite(c_tok):
                total_candidate_tokens += int(c_tok)

            # Thinking tokens
            t_tok = tok.get("thinking_tokens")
            has_valid_thinking = (
                t_tok is not None
                and not isinstance(t_tok, bool)
                and isinstance(t_tok, (int, float))
                and math.isfinite(t_tok)
                and t_tok >= 0
            )
            if has_valid_thinking:
                total_thinking_tokens += int(t_tok)

            # Record model if observed
            if r.llm_model:
                observed_models.add(str(r.llm_model))
            elif r.versions.get("llm_model"):
                observed_models.add(str(r.versions["llm_model"]))

            # Assess if this request invoked drafting
            if r.draft_status in ("draft_ready", "failed", "unavailable") or (tok and (p_tok or c_tok)):
                draft_requests_count += 1
                if has_valid_thinking:
                    drafts_with_complete_thinking += 1

        total_completion_tokens = total_candidate_tokens + total_thinking_tokens
        total_tokens = total_prompt_tokens + total_completion_tokens
        has_thinking_tracked = (total_thinking_tokens > 0 or drafts_with_complete_thinking > 0)
        all_drafts_have_thinking = (draft_requests_count > 0 and drafts_with_complete_thinking == draft_requests_count)

        # Pricing evaluation and strict provenance checks
        pricing = self.config.verified_pricing
        cost_status = "unavailable"
        cost_usd = None
        lower_bound_cost_usd = None
        cost_note = "Pricing details unverified or missing; cost is strictly unavailable (not 0.0)."

        if pricing and isinstance(pricing, dict):
            rates_valid, rate_err = validate_pricing_rates(pricing)
            if not rates_valid:
                cost_status = "invalid_pricing_rates"
                cost_usd = None
                lower_bound_cost_usd = None
                cost_note = f"Invalid pricing rates provided: {rate_err}. Cost is strictly unavailable."
            else:
                in_rate = float(pricing["input_cost_per_million"])
                out_rate = float(pricing["output_cost_per_million"])
                expected_model = pricing.get("model")
                has_provenance = bool(pricing.get("source_url") and pricing.get("verified_on") and expected_model)

                if is_mock:
                    # Mock token fixtures must NEVER be labeled with real-cost labels
                    cost_status = "mock_simulation_cost_estimate"
                    calc_out = total_candidate_tokens + total_thinking_tokens
                    cost_usd = (total_prompt_tokens * in_rate + calc_out * out_rate) / 1_000_000.0
                    lower_bound_cost_usd = (total_prompt_tokens * in_rate + total_candidate_tokens * out_rate) / 1_000_000.0
                    cost_note = (
                        "MOCK TRANSPORT FIXTURE ONLY: Tokens and cost reflect mock simulated responses, "
                        "NOT live LLM provider usage or real invoiced charges."
                    )
                else:
                    # Live run evaluation
                    # Check model alignment: source URL alone cannot assert request model!
                    model_mismatch = False
                    if observed_models and expected_model:
                        if not any(expected_model.lower() in obs.lower() or obs.lower() in expected_model.lower() for obs in observed_models):
                            model_mismatch = True

                    if model_mismatch:
                        cost_status = "model_mismatch_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = (
                            f"Pricing configuration model '{expected_model}' does not match actual observed "
                            f"request model(s) {list(observed_models)}. Cost is unavailable."
                        )
                    elif has_provenance:
                        # Compute lower bound regardless of thinking
                        lower_bound_cost_usd = (total_prompt_tokens * in_rate + total_candidate_tokens * out_rate) / 1_000_000.0

                        if all_drafts_have_thinking:
                            cost_status = "verified_list_price_estimate"
                            output_tokens_for_cost = total_candidate_tokens + total_thinking_tokens
                            cost_usd = (total_prompt_tokens * in_rate + output_tokens_for_cost * out_rate) / 1_000_000.0
                            cost_note = (
                                f"List-price estimate for {expected_model} ({pricing.get('tier', 'standard_paid')}) "
                                f"based on primary source {pricing.get('source_url')} verified on {pricing.get('verified_on')}. "
                                "Calculated with verified 100% per-request thinking token coverage. Not an invoiced charge."
                            )
                        else:
                            # Absent or partial thinking tokens: cost_usd must be None!
                            cost_status = "partial_lower_bound_missing_thinking"
                            cost_usd = None
                            cost_note = (
                                f"Thinking tokens were missing or untracked on one or more draft requests "
                                f"({drafts_with_complete_thinking}/{draft_requests_count} complete). "
                                "Complete cost_usd is strictly unavailable (None); lower_bound_cost_usd "
                                "reflects lower bound excluding thinking tokens."
                            )
                    else:
                        cost_status = "arithmetic_fixture_unverified"
                        cost_usd = (total_prompt_tokens * in_rate + total_completion_tokens * out_rate) / 1_000_000.0
                        lower_bound_cost_usd = (total_prompt_tokens * in_rate + total_candidate_tokens * out_rate) / 1_000_000.0
                        cost_note = "Arithmetic unit test fixture only; rates lack primary source URL or verified_on provenance."

        p95_target_met = bool(p95 is not None and p95 <= 12.0)
        oversight_target_met = bool(len(results) > 0 and auto_send_violations == 0)

        # Runner-level checks passed
        runner_checks_passed = (
            len(results) > 0
            and all(r.is_success for r in results)
            and p95_target_met
            and oversight_target_met
            and technical_errors == 0
            and timeouts == 0
            and failed_jobs == 0
        )

        # Topic 1 / Production acceptance can NEVER be certified by runner checks alone
        global_production_accepted = False

        summary_data = {
            "meta": {
                "run_id": run_id,
                "timestamp": iso_timestamp,
                "git_commit": git_commit,
                "mode": self.config.mode,
                "evidence_kind": "mock_runner_simulation" if is_mock else "bounded_live",
                "scope": "end_to_end_application_acceptance",
                "boundary": "POST /v1/shop/tickets -> PostgreSQL job -> GET /v1/console/tickets/{id} terminal state",
                "certification_scope": "mock_simulation_only" if is_mock else "bounded_live_run",
                "certification_disclaimer": "Local runner checks alone cannot certify overall Topic 1 or production deployment; holistic multi-worker acceptance required.",
                "environment": {
                    "os": platform.platform(),
                    "python_version": platform.python_version(),
                    "psycopg_impl": os.environ.get("PSYCOPG_IMPL", "unspecified"),
                },
                "runner_config": {
                    "num_warm_requests": self.config.num_warm_requests,
                    "poll_timeout_seconds": self.config.poll_timeout_seconds,
                    "analysis_timeout_ms": self.config.analysis_timeout_ms,
                    "draft_timeout_ms": self.config.draft_timeout_ms,
                },
            },
            "acceptance_summary": {
                "runner_checks_passed": runner_checks_passed,
                "overall_passed": runner_checks_passed,
                "mock_only_evaluation": is_mock,
                "global_production_accepted": global_production_accepted,
                "total_cases": len(results),
                "successful_cases": sum(1 for r in results if r.is_success),
                "technical_errors": technical_errors,
                "timeouts": timeouts,
                "failed_jobs": failed_jobs,
                "auto_send_violations": auto_send_violations,
                "human_oversight_enforced": oversight_target_met,
            },
            "performance": {
                "p50_seconds": p50,
                "p95_seconds": p95,
                "min_seconds": min_sec,
                "max_seconds": max_sec,
                "target_p95_met": p95_target_met,
                "target_threshold_seconds": 12.0,
                "conditions": {
                    "cold": {
                        "count": len(cold_lats),
                        "latency_seconds": p50_cold,
                        "description": "App connection and DB pool cold start only (NOT model or provider cold start)",
                    },
                    "warm": {
                        "count": len(warm_lats),
                        "p50_seconds": p50_warm,
                        "p95_seconds": p95_warm,
                        "description": "Subsequent tickets executed on warm connection pool and worker",
                    },
                },
            },
            "tokens_and_cost": {
                "total_prompt_tokens": total_prompt_tokens,
                "total_candidate_tokens": total_candidate_tokens,
                "total_thinking_tokens": total_thinking_tokens,
                "total_completion_tokens": total_completion_tokens,
                "thinking_tracked": has_thinking_tracked,
                "all_requests_tracked_thinking": all_drafts_have_thinking,
                "total_tokens": total_tokens,
                "cost_status": cost_status,
                "cost_usd": cost_usd,
                "lower_bound_cost_usd": lower_bound_cost_usd,
                "cost_note": cost_note,
                "observed_models": sorted(list(observed_models)),
            },
            "cases": [r.as_dict() for r in results],
        }

        if output_dir:
            self._persist_run_artifacts(summary_data, results, output_dir, run_id)

        return summary_data

    def _persist_run_artifacts(
        self,
        summary_data: Dict[str, Any],
        results: List[TicketCaseResult],
        base_output_dir: Path,
        run_id: str,
    ) -> None:
        """Persist reports in a unique run directory to preserve exploratory artifacts."""
        run_dir = base_output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        raw_cases = [r.as_dict() for r in results]
        raw_json_bytes = json.dumps(raw_cases, indent=2, ensure_ascii=False).encode("utf-8")
        raw_records_sha256 = hashlib.sha256(raw_json_bytes).hexdigest().upper()
        summary_data["meta"]["raw_records_sha256"] = raw_records_sha256

        raw_file = run_dir / "raw_records.json"
        raw_file.write_bytes(raw_json_bytes)

        json_file = run_dir / "acceptance_e2e_report.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        md_content = self._render_markdown(summary_data)
        md_file = run_dir / "acceptance_e2e_report.md"
        md_file.write_text(md_content, encoding="utf-8")

        # Update latest_run.json pointer without overwriting old reports
        latest_pointer = base_output_dir / "latest_run.json"
        latest_data = {
            "latest_run_id": run_id,
            "run_dir": str(run_dir),
            "timestamp": summary_data["meta"]["timestamp"],
            "runner_checks_passed": summary_data["acceptance_summary"]["runner_checks_passed"],
            "mode": summary_data["meta"]["mode"],
            "raw_records_sha256": raw_records_sha256,
        }
        with open(latest_pointer, "w", encoding="utf-8") as f:
            json.dump(latest_data, f, indent=2, ensure_ascii=False)

    def _render_markdown(self, summary: Dict[str, Any]) -> str:
        s = summary["acceptance_summary"]
        p = summary["performance"]
        tc = summary["tokens_and_cost"]
        meta = summary["meta"]
        is_mock = meta.get("mode") == "mock"

        headline_suffix = " (MOCK CHECKS ONLY)" if is_mock else " (Bounded Live Run)"
        status_label = "PASSED (MOCK CHECKS ONLY)" if (is_mock and s["runner_checks_passed"]) else ("PASSED" if s["runner_checks_passed"] else "FAILED")

        p95_str = f"{p['p95_seconds']:.3f}s" if p["p95_seconds"] is not None else "None"
        p50_str = f"{p['p50_seconds']:.3f}s" if p["p50_seconds"] is not None else "None"
        min_str = f"{p['min_seconds']:.3f}s" if p["min_seconds"] is not None else "None"
        max_str = f"{p['max_seconds']:.3f}s" if p["max_seconds"] is not None else "None"

        lines = [
            f"# SupportIQ — End-to-End Application Acceptance Report{headline_suffix}",
            "",
            f"- **Run ID:** `{meta['run_id']}`",
            f"- **Timestamp:** `{meta['timestamp']}`",
            f"- **Git HEAD:** `{meta.get('git_commit', 'unknown')}`",
            f"- **Mode:** `{meta['mode']}`",
            f"- **Runner Checks Status:** **{status_label}**",
            f"- **Global Production Accepted:** `{s['global_production_accepted']}` *(Cannot be certified by runner alone)*",
            "",
        ]

        if is_mock:
            lines.extend([
                "> [!WARNING]",
                "> **MOCK SIMULATION NOTICE:** Latency figures (e.g. p95) reflect mock loopback transport latency and synthetic delays, NOT actual LLM provider execution evidence. This run does NOT constitute live or production certification.",
                "",
            ])

        lines.extend([
            "> [!IMPORTANT]",
            "> **Application Acceptance Invariants:**",
            "> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None`).",
            "> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions.",
            "> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided; missing pricing remains `unavailable`, never 0.0.",
            "",
            "## 1. Acceptance Gates & Quality Checks",
            "",
            "| Gate | Observed Value | Requirement | Status |",
            "|---|---|---|:---:|",
            f"| **Human Oversight (No Auto-Send)** | {s['auto_send_violations']} violations | 0 violations (`customer_reply is None`) | **{'PASS' if s['human_oversight_enforced'] else 'FAIL'}** |",
            f"| **p95 Latency** | `{p95_str}` | <= 12.000s | **{'PASS' if p['target_p95_met'] else 'FAIL'}** |",
            f"| **Technical Errors** | `{s['technical_errors']}` | 0 errors | **{'PASS' if s['technical_errors'] == 0 else 'FAIL'}** |",
            f"| **Timeouts** | `{s['timeouts']}` | 0 timeouts | **{'PASS' if s['timeouts'] == 0 else 'FAIL'}** |",
            f"| **Failed Background Jobs** | `{s['failed_jobs']}` | 0 failures | **{'PASS' if s['failed_jobs'] == 0 else 'FAIL'}** |",
            "",
            "## 2. Latency Analysis (Cold vs Warm Conditions)",
            "",
            f"- **Overall p50 Latency:** `{p50_str}`",
            f"- **Overall p95 Latency:** `{p95_str}`",
            f"- **Min / Max Latency:** `{min_str}` / `{max_str}`",
            "",
            "| Condition | Cases (n) | Latency (p50 / p95) | Description |",
            "|---|---:|---|---|",
        ])

        cold_info = p["conditions"]["cold"]
        cold_lat_str = f"`{cold_info['latency_seconds']:.3f}s`" if cold_info["latency_seconds"] is not None else "`None`"
        lines.append(
            f"| **Cold Start** | {cold_info['count']} | {cold_lat_str} (first call) | Initial submission: application connection and DB pool cold start (NOT model cold start) |"
        )

        warm_info = p["conditions"]["warm"]
        warm_p50 = f"`{warm_info['p50_seconds']:.3f}s`" if warm_info["p50_seconds"] is not None else "`None`"
        warm_p95 = f"`{warm_info['p95_seconds']:.3f}s`" if warm_info["p95_seconds"] is not None else "`None`"
        lines.append(
            f"| **Warm Runs** | {warm_info['count']} | p50: {warm_p50}, p95: {warm_p95} | Subsequent tickets on warmed worker thread |"
        )

        lines.extend([
            "",
            "## 3. Token Usage and Pricing Coverage",
            "",
            f"- **Prompt / Input Tokens:** `{tc['total_prompt_tokens']}`",
            f"- **Candidate / Output Tokens:** `{tc.get('total_candidate_tokens', 0)}`",
            f"- **Thinking Tokens:** `{tc.get('total_thinking_tokens', 0)}` ({'complete coverage' if tc.get('all_requests_tracked_thinking') else ('partial/untracked' if tc.get('thinking_tracked') else 'omitted/untracked')})",
            f"- **Total Completion Tokens:** `{tc['total_completion_tokens']}`",
            f"- **Total Tokens:** `{tc['total_tokens']}`",
            f"- **Cost Status:** `{tc['cost_status']}`",
            f"- **Estimated Cost (USD):** `{tc['cost_usd'] if tc['cost_usd'] is not None else 'UNAVAILABLE'}`",
            f"- **Lower Bound Cost (USD):** `{tc['lower_bound_cost_usd'] if tc.get('lower_bound_cost_usd') is not None else 'N/A'}`",
            f"- **Pricing Note:** {tc['cost_note']}",
            "",
            "## 4. Case Execution Summary",
            "",
            "| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |",
            "|---|:---:|---|---|---:|:---:|:---:|:---:|",
        ])

        for c in summary["cases"]:
            wall_str = str(c["wall_latency_ms"]) if c["wall_latency_ms"] is not None else "None"
            lines.append(
                f"| {c['case_index']} | `{c['condition']}` | `{c['ticket_id'] or 'None'}` | "
                f"{c['message'][:30]}... | {wall_str} | `{c['draft_status']}` | "
                f"{'YES' if c['reply_is_none'] else '**NO**'} | {'**PASS**' if c['is_success'] else '**FAIL**'} |"
            )

        lines.extend([
            "",
            "## 5. Verification Commands for Integration",
            "",
            "```powershell",
            "# 1. Environment preflight check",
            "$env:PSYCOPG_IMPL = 'python'",
            "$env:PATH = 'F:\\PostgreSQL\\bin;' + $env:PATH",
            "& 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode mock",
            "",
            "# 2. Live bounded verification (when coordinator authorizes)",
            "# & 'F:/Năm 3/SD/project/SupportIQ/.venv/Scripts/python.exe' -m scripts.run_application_acceptance --mode live",
            "```",
            "",
        ])

        return "\n".join(lines)

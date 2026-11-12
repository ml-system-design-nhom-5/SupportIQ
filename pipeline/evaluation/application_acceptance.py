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


def is_valid_token_count(val: Any) -> bool:
    """Check if token count is a valid non-negative integer (not boolean or fractional)."""
    return isinstance(val, int) and not isinstance(val, bool) and val >= 0


def is_valid_latency(lat: Any) -> bool:
    """Check if latency is a valid non-negative finite number (not boolean, NaN, Inf, or negative)."""
    return (
        lat is not None
        and isinstance(lat, (int, float))
        and not isinstance(lat, bool)
        and math.isfinite(lat)
        and lat >= 0
    )


def compute_stratum_metrics(latencies_seconds: List[float], errors_count: int, total_count: int) -> Dict[str, Any]:
    """Compute p50, p95, mean, min, max, and error rate for a latency stratum."""
    if not latencies_seconds or total_count == 0:
        return {
            "count": total_count,
            "p50_seconds": None,
            "p95_seconds": None,
            "mean_seconds": None,
            "min_seconds": None,
            "max_seconds": None,
            "error_rate": 0.0 if total_count == 0 else round(errors_count / total_count, 4),
        }
    sorted_lats = sorted(latencies_seconds)
    n = len(sorted_lats)
    p50 = (sorted_lats[(n - 1) // 2] + sorted_lats[n // 2]) / 2.0
    p95_idx = max(0, math.ceil(0.95 * n) - 1)
    p95 = sorted_lats[p95_idx]
    mean_lat = sum(sorted_lats) / n
    return {
        "count": total_count,
        "p50_seconds": round(p50, 5),
        "p95_seconds": round(p95, 5),
        "mean_seconds": round(mean_lat, 5),
        "min_seconds": round(sorted_lats[0], 5),
        "max_seconds": round(sorted_lats[-1], 5),
        "error_rate": round(errors_count / total_count, 4),
    }


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
                "llm_usage": {
                    "input_tokens": 128,
                    "output_tokens": 42,
                    "thought_tokens": 0,
                    "total_tokens": 170,
                },
                "llm_metadata": {
                    "provider": "google_ai_studio",
                    "model": "mock-eval-llm",
                    "model_version": "v1.0.0",
                    "prompt_version": "v2.0",
                },
                "versions": {
                    "release_id": "rel-v2",
                    "model_version": "v1.0.0",
                    "llm_model": "mock-eval-llm",
                },
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
    observation_succeeded: bool = True  # Verified expected 200 JSON shape
    step_latency_ms: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, Any] = field(default_factory=dict)
    llm_metadata: Dict[str, Any] = field(default_factory=dict)
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
            "observation_succeeded": self.observation_succeeded,
            "step_latency_ms": self.step_latency_ms,
            "tokens": self.tokens,
            "llm_metadata": self.llm_metadata,
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

    def validate(self) -> None:
        """Validate config parameters before database connection or service invocation."""
        if self.mode not in ("mock", "live"):
            raise ValueError(f"Invalid mode '{self.mode}'; must be 'mock' or 'live'")
        if isinstance(self.num_warm_requests, bool) or not isinstance(self.num_warm_requests, int) or self.num_warm_requests < 0:
            raise ValueError(f"num_warm_requests must be a non-negative integer, got {self.num_warm_requests}")
        if (
            isinstance(self.poll_timeout_seconds, bool)
            or not isinstance(self.poll_timeout_seconds, (int, float))
            or not math.isfinite(self.poll_timeout_seconds)
            or self.poll_timeout_seconds <= 0
        ):
            raise ValueError(f"poll_timeout_seconds must be a positive finite number, got {self.poll_timeout_seconds}")
        if (
            isinstance(self.analysis_timeout_ms, bool)
            or not isinstance(self.analysis_timeout_ms, int)
            or self.analysis_timeout_ms <= 0
        ):
            raise ValueError(f"analysis_timeout_ms must be a positive integer, got {self.analysis_timeout_ms}")
        if (
            isinstance(self.draft_timeout_ms, bool)
            or not isinstance(self.draft_timeout_ms, int)
            or self.draft_timeout_ms <= 0
        ):
            raise ValueError(f"draft_timeout_ms must be a positive integer, got {self.draft_timeout_ms}")


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
        # Validate configuration upfront before creating engines or spawning servers
        self.config.validate()

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
                            observation_succeeded=False,
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

                    # Strict human oversight invariant: verify customer GET returns HTTP 200 AND valid JSON shape
                    cust_resp = customer.get(f"/v1/shop/tickets/{t_id}")
                    if cust_resp.status_code != 200:
                        reply_is_none = False
                        observation_succeeded = False
                        error_code = f"CUSTOMER_VIEW_HTTP_{cust_resp.status_code}"
                    else:
                        try:
                            cust_view = cust_resp.json()
                            if not isinstance(cust_view, dict) or "reply" not in cust_view or "ticket_id" not in cust_view:
                                reply_is_none = False
                                observation_succeeded = False
                                error_code = "CUSTOMER_VIEW_MALFORMED_SHAPE"
                            else:
                                customer_reply = cust_view.get("reply")
                                reply_is_none = (customer_reply is None)
                                observation_succeeded = True
                                error_code = None
                        except Exception:
                            reply_is_none = False
                            observation_succeeded = False
                            error_code = "CUSTOMER_VIEW_JSON_PARSE_ERROR"

                    a_stat = suggestion_data.get("analysis_status", "timeout" if not reached_terminal else "unknown")
                    d_stat = suggestion_data.get("draft_status", "timeout" if not reached_terminal else "unknown")
                    step_lat = suggestion_data.get("step_latency_ms", {})
                    tokens = suggestion_data.get("llm_usage", {}) or {}
                    llm_meta = suggestion_data.get("llm_metadata", {}) or {}
                    versions = suggestion_data.get("versions", {}) or {}
                    observed_model = llm_meta.get("model") or versions.get("llm_model")

                    auto_send_safe = (observation_succeeded and reply_is_none)
                    success = (
                        reached_terminal
                        and d_stat in ("draft_ready", "abstained", "escalation_recommended")
                        and auto_send_safe
                        and is_valid_latency(wall_ms)
                    )

                    results.append(TicketCaseResult(
                        case_index=idx,
                        condition=cond,
                        message=msg,
                        ticket_id=t_id,
                        wall_latency_ms=wall_ms,
                        analysis_status=a_stat,
                        draft_status=d_stat,
                        customer_reply_is_none=reply_is_none,
                        observation_succeeded=observation_succeeded,
                        step_latency_ms=step_lat,
                        tokens=tokens,
                        llm_metadata=llm_meta,
                        llm_model=observed_model,
                        versions=versions,
                        error_code=error_code or suggestion_data.get("failure_code") or (None if reached_terminal else "timeout"),
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

        runner_config_dict = {
            "num_warm_requests": getattr(self.config, "num_warm_requests", 4),
            "poll_timeout_seconds": getattr(self.config, "poll_timeout_seconds", 25.0),
            "analysis_timeout_ms": getattr(self.config, "analysis_timeout_ms", 3000),
            "draft_timeout_ms": getattr(self.config, "draft_timeout_ms", 11000),
        }

        # Handle empty results / zero measurements: fail closed and reject
        if not results:
            summary_data = {
                "meta": {
                    "run_id": run_id,
                    "timestamp": iso_timestamp,
                    "git_commit": git_commit,
                    "mode": self.config.mode,
                    "boundary_kind": "in_process_asgi_testclient",
                    "status": "rejected_empty_results",
                    "rejection_reason": "No valid measurements or ticket cases were executed.",
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
                    "runner_config": runner_config_dict,
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
                    "latency_coverage_complete": False,
                },
                "performance": {
                    "p50_seconds": None,
                    "p95_seconds": None,
                    "mean_seconds": None,
                    "min_seconds": None,
                    "max_seconds": None,
                    "error_rate": 0.0,
                    "target_p95_met": False,
                    "target_threshold_seconds": 12.0,
                    "strata": {
                        "draft_producing": {
                            "count": 0,
                            "p50_seconds": None,
                            "p95_seconds": None,
                            "mean_seconds": None,
                            "min_seconds": None,
                            "max_seconds": None,
                            "error_rate": 0.0,
                            "description": "Tickets reaching draft generation (e.g. draft_ready, clarification)",
                        },
                        "abstention": {
                            "count": 0,
                            "p50_seconds": None,
                            "p95_seconds": None,
                            "mean_seconds": None,
                            "min_seconds": None,
                            "max_seconds": None,
                            "error_rate": 0.0,
                            "description": "Tickets abstaining or escalating before LLM generation (e.g. abstained, escalation_recommended)",
                        },
                        "overall": {
                            "count": 0,
                            "p50_seconds": None,
                            "p95_seconds": None,
                            "mean_seconds": None,
                            "min_seconds": None,
                            "max_seconds": None,
                            "error_rate": 0.0,
                            "description": "All submitted tickets across all conditions and outcomes",
                        },
                    },
                    "conditions": {
                        "cold": {
                            "count": 0,
                            "latency_seconds": None,
                            "mean_seconds": None,
                            "description": "App connection and DB pool cold start only (NOT model cold start)",
                        },
                        "warm": {
                            "count": 0,
                            "p50_seconds": None,
                            "p95_seconds": None,
                            "mean_seconds": None,
                            "description": "Subsequent tickets executed on warm connection pool and worker",
                        },
                    },
                },
                "tokens_and_cost": {
                    "total_prompt_tokens": None,
                    "total_candidate_tokens": None,
                    "total_thinking_tokens": None,
                    "total_completion_tokens": None,
                    "total_tokens": None,
                    "provider_reported_total_tokens": None,
                    "observed_thought_tokens": 0,
                    "observed_partial_tokens": 0,
                    "thinking_tracked": False,
                    "all_requests_tracked_thinking": False,
                    "thinking_tokens_assumed_zero": False,
                    "derivation_provenance": None,
                    "cost_status": "unavailable",
                    "cost_usd": None,
                    "lower_bound_cost_usd": None,
                    "cost_note": "Empty run; no valid measurements executed.",
                    "observed_models": [],
                    "observed_providers": [],
                    "observed_tiers": [],
                },
                "cases": [],
            }
            if output_dir:
                self._persist_run_artifacts(summary_data, [], output_dir, run_id)
            return summary_data

        # Strict latency validation: ALL cases must have valid non-negative finite numeric latency
        all_latencies_valid = all(is_valid_latency(r.wall_latency_ms) for r in results)
        valid_latencies = [r.wall_latency_ms / 1000.0 for r in results if is_valid_latency(r.wall_latency_ms)]

        cold_lats = [r.wall_latency_ms / 1000.0 for r in results if r.condition == "cold" and is_valid_latency(r.wall_latency_ms)]
        warm_lats = [r.wall_latency_ms / 1000.0 for r in results if r.condition == "warm" and is_valid_latency(r.wall_latency_ms)]

        # Helper to classify unique failed tickets without overlapping double-counts
        def is_failed_ticket(res: TicketCaseResult) -> bool:
            if not res.is_success:
                return True
            if res.analysis_status in ("error", "timeout"):
                return True
            if res.draft_status in ("error", "failed", "unavailable", "llm_unavailable"):
                return True
            if not res.is_terminal:
                return True
            if not res.customer_reply_is_none or not res.observation_succeeded:
                return True
            return False

        failed_tickets_count = sum(1 for r in results if is_failed_ticket(r))
        overall_error_rate = round(failed_tickets_count / len(results), 4) if results else 0.0

        cold_cases = [r for r in results if r.condition == "cold"]
        cold_failed = sum(1 for r in cold_cases if is_failed_ticket(r))
        cold_error_rate = round(cold_failed / len(cold_cases), 4) if cold_cases else 0.0

        warm_cases = [r for r in results if r.condition == "warm"]
        warm_failed = sum(1 for r in warm_cases if is_failed_ticket(r))
        warm_error_rate = round(warm_failed / len(warm_cases), 4) if warm_cases else 0.0

        draft_cases = [r for r in results if r.draft_status in ("draft_ready", "clarification")]
        abstain_cases = [r for r in results if r.draft_status in ("abstained", "escalation_recommended")]

        draft_lats = [r.wall_latency_ms / 1000.0 for r in draft_cases if is_valid_latency(r.wall_latency_ms)]
        abstain_lats = [r.wall_latency_ms / 1000.0 for r in abstain_cases if is_valid_latency(r.wall_latency_ms)]

        draft_errors = sum(1 for r in draft_cases if is_failed_ticket(r))
        abstain_errors = sum(1 for r in abstain_cases if is_failed_ticket(r))

        draft_stratum = compute_stratum_metrics(draft_lats, draft_errors, len(draft_cases))
        abstain_stratum = compute_stratum_metrics(abstain_lats, abstain_errors, len(abstain_cases))
        overall_stratum = compute_stratum_metrics(valid_latencies, failed_tickets_count, len(results))

        if all_latencies_valid and valid_latencies:
            latencies_sorted = sorted(valid_latencies)
            p50 = (latencies_sorted[(len(latencies_sorted) - 1) // 2] + latencies_sorted[len(latencies_sorted) // 2]) / 2.0
            p95_idx = max(0, math.ceil(0.95 * len(latencies_sorted)) - 1)
            p95 = latencies_sorted[p95_idx]
            min_sec = latencies_sorted[0]
            max_sec = latencies_sorted[-1]
            mean_sec = round(sum(valid_latencies) / len(valid_latencies), 5)
            p50_cold = cold_lats[0] if cold_lats else None
            cold_mean = round(sum(cold_lats) / len(cold_lats), 5) if cold_lats else None
            p95_warm = sorted(warm_lats)[max(0, math.ceil(0.95 * len(warm_lats)) - 1)] if warm_lats else None
            p50_warm = (sorted(warm_lats)[len(warm_lats) // 2]) if warm_lats else None
            warm_mean = round(sum(warm_lats) / len(warm_lats), 5) if warm_lats else None
            p95_target_met = bool(p95 <= 12.0)
        else:
            # Latency coverage failed: missing, negative, NaN, or boolean latency on any case
            p50 = None
            p95 = None
            min_sec = None
            max_sec = None
            mean_sec = None
            p50_cold = None
            cold_mean = None
            p95_warm = None
            p50_warm = None
            warm_mean = None
            p95_target_met = False

        technical_errors = sum(1 for r in results if r.analysis_status == "error" or r.draft_status == "error")
        timeouts = sum(1 for r in results if not r.is_terminal or r.analysis_status == "timeout")
        failed_jobs = sum(1 for r in results if r.draft_status in ("failed", "unavailable", "llm_unavailable"))
        auto_send_violations = sum(1 for r in results if not r.customer_reply_is_none or not r.observation_succeeded)

        # Per-billable attempt token and metadata validation
        billable_attempts: List[Dict[str, Any]] = []
        observed_models: set[str] = set()
        observed_providers: set[str] = set()
        observed_tiers: set[str] = set()
        token_coverage_valid = True
        has_invalid_numeric_values = False
        has_inconsistent_totals = False
        has_unknown_timeout_attempt = False
        has_missing_provider = False
        has_missing_model = False

        for r in results:
            tok = r.tokens or {}
            meta = r.llm_metadata or {}
            raw_attempts = meta.get("attempts")

            is_billable = (
                r.draft_status in ("draft_ready", "clarification", "failed", "unavailable", "llm_unavailable")
                or bool(tok)
                or bool(raw_attempts)
            )
            if not is_billable:
                continue

            if tok.get("incomplete"):
                token_coverage_valid = False
            if tok.get("has_invalid_fields"):
                has_invalid_numeric_values = True

            attempts_to_process = []
            is_legacy_ticket = False
            if isinstance(raw_attempts, list) and raw_attempts:
                for att in raw_attempts:
                    if isinstance(att, dict):
                        attempts_to_process.append(att)

            if not attempts_to_process:
                is_legacy_ticket = True
                attempts_to_process = [{
                    "attempt_index": 0,
                    "status": r.draft_status,
                    "usage": tok,
                    "metadata": meta,
                }]

            for att in attempts_to_process:
                att_status = att.get("status")
                att_u = att.get("usage") or {}
                att_m = att.get("metadata") or {}

                if is_legacy_ticket:
                    # Legacy ticket with no raw attempts: can fall back to ticket-level meta / versions / llm_model
                    m_val = att_m.get("model") if att_m.get("model") is not None else att.get("model")
                    if m_val is None:
                        m_val = meta.get("model")
                    if m_val is None:
                        m_val = r.versions.get("llm_model") if r.versions else None
                    if m_val is None:
                        m_val = r.llm_model

                    p_val = att_m.get("provider") if att_m.get("provider") is not None else att.get("provider")
                    if p_val is None:
                        p_val = meta.get("provider")
                    if p_val is None:
                        p_val = r.versions.get("provider") if r.versions else None

                    t_val = att_m.get("tier") if att_m.get("tier") is not None else att.get("tier")
                    if t_val is None:
                        t_val = meta.get("tier")
                    if t_val is None:
                        t_val = r.versions.get("tier") if r.versions else None
                else:
                    # Explicit raw attempts must NOT inherit last-success provider/model/tier
                    m_val = att_m.get("model") if att_m.get("model") is not None else att.get("model")
                    p_val = att_m.get("provider") if att_m.get("provider") is not None else att.get("provider")
                    t_val = att_m.get("tier") if att_m.get("tier") is not None else att.get("tier")

                if m_val:
                    observed_models.add(str(m_val))
                else:
                    has_missing_model = True

                if p_val:
                    observed_providers.add(str(p_val))
                else:
                    has_missing_provider = True

                if t_val:
                    observed_tiers.add(str(t_val))

                in_tok = att_u.get("promptTokenCount")
                if in_tok is None:
                    in_tok = att_u.get("input_tokens")
                if in_tok is None:
                    in_tok = att_u.get("prompt_tokens")

                out_tok = att_u.get("candidatesTokenCount")
                if out_tok is None:
                    out_tok = att_u.get("output_tokens")
                if out_tok is None:
                    out_tok = att_u.get("candidate_tokens")
                if out_tok is None:
                    out_tok = att_u.get("completion_tokens")

                tot_tok = att_u.get("totalTokenCount")
                if tot_tok is None:
                    tot_tok = att_u.get("total_tokens")

                th_tok = att_u.get("thoughtsTokenCount")
                if th_tok is None:
                    th_tok = att_u.get("thought_tokens")
                if th_tok is None:
                    th_tok = att_u.get("thinking_tokens")

                # Detect unknown timeout usage (timeout occurred with unknown provider token usage)
                if att_status in ("llm_timeout", "timeout") and in_tok is None:
                    has_unknown_timeout_attempt = True

                # Check numeric validity (boolean is invalid, float is invalid, negative is invalid)
                for raw_val in (in_tok, out_tok, tot_tok, th_tok):
                    if raw_val is not None and not is_valid_token_count(raw_val):
                        has_invalid_numeric_values = True

                has_valid_in = is_valid_token_count(in_tok)
                has_valid_out = is_valid_token_count(out_tok)
                has_valid_tot = is_valid_token_count(tot_tok)
                has_valid_thought = is_valid_token_count(th_tok)

                is_draft_producing_status = att_status in ("draft_ready", "clarification", "success")

                # If output is missing but provider reported totalTokenCount:
                if not has_valid_out and has_valid_tot and has_valid_in:
                    if has_valid_thought:
                        # candidate tokens derivable = total - prompt - thought
                        if tot_tok >= in_tok + th_tok:
                            out_tok = tot_tok - in_tok - th_tok
                            has_valid_out = True

                # For a failed attempt before candidate generation (e.g. llm_unavailable), output tokens is 0
                if not has_valid_out and not is_draft_producing_status and not (att_status in ("abstained", "escalation_recommended")):
                    out_tok = 0
                    has_valid_out = True

                # Input coverage: executed attempt must have valid input tokens
                if not has_valid_in and not (att_status in ("abstained", "escalation_recommended")):
                    token_coverage_valid = False

                # Output coverage: draft-producing attempt must have valid output tokens OR provider total to derive billable output
                if not has_valid_out and not has_valid_tot and is_draft_producing_status:
                    token_coverage_valid = False

                if has_valid_tot and has_valid_in and has_valid_out:
                    if tot_tok < in_tok + out_tok:
                        has_inconsistent_totals = True
                    if has_valid_thought and tot_tok < in_tok + out_tok + th_tok:
                        has_inconsistent_totals = True

                billable_attempts.append({
                    "case_index": r.case_index,
                    "attempt_index": att.get("attempt_index", 0),
                    "status": att_status,
                    "input_tokens": in_tok if has_valid_in else None,
                    "output_tokens": out_tok if has_valid_out else None,
                    "total_tokens": tot_tok if has_valid_tot else None,
                    "thought_tokens": th_tok if has_valid_thought else None,
                    "has_valid_in": has_valid_in,
                    "has_valid_out": has_valid_out,
                    "has_valid_tot": has_valid_tot,
                    "has_valid_thought": has_valid_thought,
                    "model": m_val,
                    "provider": p_val,
                    "tier": t_val,
                })

        # Token aggregation with strict complete null handling when thoughts are absent
        observed_thought_tokens = 0
        provider_reported_total_tokens = None
        derivation_provenance = None

        if token_coverage_valid and not has_invalid_numeric_values and not has_inconsistent_totals and billable_attempts:
            total_prompt_tokens = sum(b["input_tokens"] for b in billable_attempts)
            all_attempts_have_out = all(b["has_valid_out"] for b in billable_attempts)
            total_candidate_tokens = sum(b["output_tokens"] for b in billable_attempts) if all_attempts_have_out else None

            all_attempts_have_thought = all(b["has_valid_thought"] for b in billable_attempts)
            has_thinking_tracked = any(b["has_valid_thought"] for b in billable_attempts)
            observed_thought_tokens = sum(b["thought_tokens"] for b in billable_attempts if b["has_valid_thought"])
            observed_partial_tokens = total_prompt_tokens + (total_candidate_tokens or 0) + observed_thought_tokens

            all_attempts_have_total = all(b["has_valid_tot"] for b in billable_attempts)

            if all_attempts_have_thought and all_attempts_have_out:
                total_thinking_tokens = observed_thought_tokens
                total_completion_tokens = total_candidate_tokens + total_thinking_tokens
                total_tokens = total_prompt_tokens + total_completion_tokens
                provider_reported_total_tokens = sum(b["total_tokens"] for b in billable_attempts) if all_attempts_have_total else None
                derivation_provenance = None
            elif all_attempts_have_total:
                # When thoughts are absent/untracked BUT explicit provider totalTokenCount is reported for all attempts:
                provider_reported_total = sum(b["total_tokens"] for b in billable_attempts)
                provider_reported_total_tokens = provider_reported_total
                derived_output = provider_reported_total - total_prompt_tokens
                total_thinking_tokens = None  # Do NOT assert zero!
                total_completion_tokens = derived_output
                total_tokens = provider_reported_total
                derivation_provenance = {
                    "formula": "billable_output_tokens = totalTokenCount - promptTokenCount (text-only/no-tools requests)",
                    "raw_reported_total_tokens": provider_reported_total,
                    "total_prompt_tokens": total_prompt_tokens,
                    "total_candidate_tokens": total_candidate_tokens,
                    "derived_output_tokens": derived_output,
                    "thinking_tokens_reported": False,
                    "thinking_tokens_assumed_zero": False,
                    "provider_semantics_verified": True,
                    "source_doc": "https://aistudio.google.com/api-reference/generate-content UsageMetadata plus pricing",
                    "description": (
                        "Derived from provider-reported totalTokenCount under Gemini API billing semantics "
                        "for this client's text-only/no-tools requests (where totalTokenCount = promptTokenCount + "
                        "candidatesTokenCount + thoughtsTokenCount, with toolUsePromptTokenCount not applicable). "
                        "Separate thoughtsTokenCount was not returned by provider; thoughts are NOT asserted to be zero."
                    ),
                }
            else:
                # When thoughts are absent AND total_tokens is missing from one or more attempts
                total_thinking_tokens = None
                total_completion_tokens = None
                total_tokens = None
                provider_reported_total_tokens = None
                derivation_provenance = None
        elif not billable_attempts:
            total_prompt_tokens = 0
            total_candidate_tokens = 0
            total_thinking_tokens = 0
            total_completion_tokens = 0
            total_tokens = 0
            provider_reported_total_tokens = None
            observed_thought_tokens = 0
            observed_partial_tokens = 0
            has_thinking_tracked = False
            all_attempts_have_thought = False
            derivation_provenance = None
        else:
            total_prompt_tokens = None
            total_candidate_tokens = None
            total_thinking_tokens = None
            total_completion_tokens = None
            total_tokens = None
            provider_reported_total_tokens = None
            observed_thought_tokens = sum(b["thought_tokens"] for b in billable_attempts if b["has_valid_thought"])
            observed_partial_tokens = 0
            has_thinking_tracked = any(b["has_valid_thought"] for b in billable_attempts)
            all_attempts_have_thought = False
            derivation_provenance = None

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
            elif has_invalid_numeric_values:
                cost_status = "invalid_numeric_token_values"
                cost_usd = None
                lower_bound_cost_usd = None
                cost_note = "Billable attempts have invalid numeric token values (e.g. boolean, negative, or non-integer). Cost is strictly unavailable."
            elif has_inconsistent_totals:
                cost_status = "inconsistent_token_totals"
                cost_usd = None
                lower_bound_cost_usd = None
                cost_note = "Billable attempts have mathematically inconsistent token totals (e.g. total_tokens < input_tokens + output_tokens). Cost is strictly unavailable."
            elif has_unknown_timeout_attempt:
                cost_status = "incomplete_token_coverage"
                cost_usd = None
                lower_bound_cost_usd = None
                cost_note = "One or more retry attempts timed out with unmeasured provider usage; token usage is incomplete despite subsequent success. Cost is strictly unavailable."
            elif not token_coverage_valid:
                cost_status = "incomplete_token_coverage"
                cost_usd = None
                lower_bound_cost_usd = None
                cost_note = "Billable attempts have missing or non-integer input/output tokens. Cost cannot be calculated."
            else:
                in_rate = float(pricing["input_cost_per_million"])
                out_rate = float(pricing["output_cost_per_million"])
                expected_model = pricing.get("model")
                expected_provider = pricing.get("provider")
                has_provenance = bool(pricing.get("source_url") and pricing.get("verified_on") and expected_model)

                if is_mock:
                    # Mock token fixtures must NEVER be labeled with real-cost labels
                    cost_status = "mock_simulation_cost_estimate"
                    calc_out = total_completion_tokens if total_completion_tokens is not None else ((total_candidate_tokens or 0) + (observed_thought_tokens or 0))
                    cost_usd = ((total_prompt_tokens or 0) * in_rate + calc_out * out_rate) / 1_000_000.0
                    lower_bound_cost_usd = ((total_prompt_tokens or 0) * in_rate + (total_candidate_tokens or 0) * out_rate) / 1_000_000.0
                    cost_note = (
                        "MOCK TRANSPORT FIXTURE ONLY: Tokens and cost reflect mock simulated responses, "
                        "NOT live LLM provider usage or real invoiced charges."
                    )
                else:
                    # Live run evaluation with fail-closed model, provider, and tier verification
                    if not billable_attempts:
                        cost_status = "zero_billable_calls"
                        cost_usd = 0.0
                        lower_bound_cost_usd = 0.0
                        cost_note = "All submitted tickets abstained; zero billable LLM calls were executed in this run."
                    elif len(observed_models) > 1:
                        cost_status = "mixed_models_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = f"Multiple distinct models observed across billable calls: {sorted(list(observed_models))}. Uniform pricing cannot be verified."
                    elif len(observed_providers) > 1:
                        cost_status = "mixed_providers_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = f"Multiple distinct providers observed across billable calls: {sorted(list(observed_providers))}. Uniform pricing cannot be verified."
                    elif has_missing_model or any(not b["model"] for b in billable_attempts):
                        cost_status = "unknown_model_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = "One or more billable attempts lack model metadata. Cost is unverified."
                    elif expected_provider and (has_missing_provider or any(not b["provider"] for b in billable_attempts)):
                        cost_status = "provider_missing_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = f"One or more billable attempts lack provider metadata while pricing specifies '{expected_provider}'."
                    elif expected_provider and any(b["provider"].strip().lower() != expected_provider.strip().lower() for b in billable_attempts):
                        cost_status = "provider_mismatch_unverified"
                        cost_usd = None
                        lower_bound_cost_usd = None
                        cost_note = f"Observed provider does not match verified pricing provider '{expected_provider}'."
                    else:
                        single_model = list(observed_models)[0]
                        # Exact canonical model match required if model is declared or required by provenance
                        if expected_model and single_model.strip().lower() != expected_model.strip().lower():
                            cost_status = "model_mismatch_unverified"
                            cost_usd = None
                            lower_bound_cost_usd = None
                            cost_note = f"Observed model '{single_model}' does not exactly match verified pricing model '{expected_model}'. Cost is unverified."
                        elif not expected_model and (pricing.get("source_url") or pricing.get("verified_on")):
                            cost_status = "model_missing_unverified"
                            cost_usd = None
                            lower_bound_cost_usd = None
                            cost_note = "Pricing artifact has provenance sources but is missing declared model. Cost is unverified."
                        elif has_provenance:
                            lower_bound_cost_usd = (total_prompt_tokens * in_rate + (total_candidate_tokens or 0) * out_rate) / 1_000_000.0

                            if total_completion_tokens is None:
                                cost_status = "partial_lower_bound_missing_thinking"
                                cost_usd = None
                                cost_note = (
                                    "One or more billable attempts lacked thought_tokens/thinking_tokens and total_tokens. "
                                    "Complete cost_usd is strictly null (None); lower_bound_cost_usd "
                                    "reflects lower bound excluding thinking tokens."
                                )
                            else:
                                expected_tier = pricing.get("tier", "standard_paid")
                                tier_conflict = False
                                if observed_tiers:
                                    if any(t.strip().lower() != expected_tier.strip().lower() for t in observed_tiers):
                                        tier_conflict = True

                                if tier_conflict:
                                    cost_status = "tier_mismatch_unverified"
                                    cost_usd = None
                                    lower_bound_cost_usd = None
                                    cost_note = f"Observed billing tier(s) {sorted(list(observed_tiers))} do not match pricing tier '{expected_tier}'."
                                else:
                                    calc_out = total_completion_tokens
                                    calc_cost = (total_prompt_tokens * in_rate + calc_out * out_rate) / 1_000_000.0

                                    # Missing pricing.provider OR per-attempt provider cannot yield VERIFIED label
                                    has_verified_provider = bool(
                                        expected_provider
                                        and billable_attempts
                                        and all(b.get("provider") and b["provider"].strip().lower() == expected_provider.strip().lower() for b in billable_attempts)
                                    )
                                    has_verified_tier = bool(
                                        observed_tiers
                                        and all(b.get("tier") and b["tier"].strip().lower() == expected_tier.strip().lower() for b in billable_attempts)
                                    )

                                    if not has_verified_provider or not has_verified_tier:
                                        cost_status = "conditional_list_price_estimate_unknown_account_tier"
                                        cost_usd = calc_cost
                                        lower_bound_cost_usd = (total_prompt_tokens * in_rate + (total_candidate_tokens or 0) * out_rate) / 1_000_000.0 if derivation_provenance else calc_cost
                                        prov_note = ""
                                        if derivation_provenance:
                                            prov_note = f" Output tokens derived from provider-reported totalTokenCount ({provider_reported_total_tokens} - {total_prompt_tokens} = {total_completion_tokens}) under Gemini API billing semantics (text-only/no-tools); thoughts are not asserted to be zero."
                                        reason = "Actual customer account billing tier is unverified (cannot be observed from API metadata)." if has_verified_provider else "Pricing provider is unverified or unspecified."
                                        cost_note = (
                                            f"Conditional list-price estimate for {expected_model} ({expected_tier}) "
                                            f"based on primary source {pricing.get('source_url')} verified on {pricing.get('verified_on')}.{prov_note} "
                                            f"{reason} Not an invoiced charge."
                                        )
                                    else:
                                        cost_status = "verified_list_price_estimate"
                                        cost_usd = calc_cost
                                        lower_bound_cost_usd = (total_prompt_tokens * in_rate + (total_candidate_tokens or 0) * out_rate) / 1_000_000.0 if derivation_provenance else calc_cost
                                        prov_note = ""
                                        if derivation_provenance:
                                            prov_note = f" Output tokens derived from provider-reported totalTokenCount ({provider_reported_total_tokens} - {total_prompt_tokens} = {total_completion_tokens}) under Gemini API billing semantics (text-only/no-tools); thoughts are not asserted to be zero."
                                        cost_note = (
                                            f"Verified list-price estimate for {expected_model} ({expected_tier}) "
                                            f"based on primary source {pricing.get('source_url')} verified on {pricing.get('verified_on')}.{prov_note} "
                                            "Matching provider and tier verified. Not an invoiced charge."
                                        )
                        else:
                            cost_status = "arithmetic_fixture_unverified"
                            calc_out = total_completion_tokens if total_completion_tokens is not None else (total_candidate_tokens or 0)
                            cost_usd = (total_prompt_tokens * in_rate + calc_out * out_rate) / 1_000_000.0
                            lower_bound_cost_usd = (total_prompt_tokens * in_rate + (total_candidate_tokens or 0) * out_rate) / 1_000_000.0
                            cost_note = "Arithmetic unit test fixture only; rates lack primary source URL or verified_on provenance."

        oversight_target_met = bool(len(results) > 0 and auto_send_violations == 0)

        # Runner-level checks passed: strictly requires valid latency coverage across all cases
        runner_checks_passed = (
            len(results) > 0
            and all_latencies_valid
            and all(r.is_success for r in results)
            and p95_target_met
            and oversight_target_met
            and technical_errors == 0
            and timeouts == 0
            and failed_jobs == 0
        )

        global_production_accepted = False

        summary_data = {
            "meta": {
                "run_id": run_id,
                "timestamp": iso_timestamp,
                "git_commit": git_commit,
                "mode": self.config.mode,
                "boundary_kind": "in_process_asgi_testclient",
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
                "runner_config": runner_config_dict,
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
                "latency_coverage_complete": all_latencies_valid,
            },
            "performance": {
                "p50_seconds": p50,
                "p95_seconds": p95,
                "mean_seconds": mean_sec,
                "min_seconds": min_sec,
                "max_seconds": max_sec,
                "error_rate": overall_error_rate,
                "target_p95_met": p95_target_met,
                "target_threshold_seconds": 12.0,
                "strata": {
                    "draft_producing": {**draft_stratum, "description": "Tickets reaching draft generation (e.g. draft_ready, clarification)"},
                    "abstention": {**abstain_stratum, "description": "Tickets abstaining or escalating before LLM generation (e.g. abstained, escalation_recommended)"},
                    "overall": {**overall_stratum, "description": "All submitted tickets across all conditions and outcomes"},
                },
                "conditions": {
                    "cold": {
                        "count": len(cold_cases),
                        "latency_seconds": p50_cold,
                        "mean_seconds": cold_mean,
                        "error_rate": cold_error_rate,
                        "description": "App connection and DB pool cold start only (NOT model or provider cold start)",
                    },
                    "warm": {
                        "count": len(warm_cases),
                        "p50_seconds": p50_warm,
                        "p95_seconds": p95_warm,
                        "mean_seconds": warm_mean,
                        "error_rate": warm_error_rate,
                        "description": "Subsequent tickets executed on warm connection pool and worker",
                    },
                },
            },
            "tokens_and_cost": {
                "total_prompt_tokens": total_prompt_tokens,
                "total_candidate_tokens": total_candidate_tokens,
                "total_thinking_tokens": total_thinking_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens,
                "provider_reported_total_tokens": provider_reported_total_tokens,
                "observed_thought_tokens": observed_thought_tokens,
                "observed_partial_tokens": observed_partial_tokens,
                "thinking_tracked": has_thinking_tracked,
                "all_requests_tracked_thinking": all_attempts_have_thought,
                "thinking_tokens_assumed_zero": False,
                "derivation_provenance": derivation_provenance,
                "cost_status": cost_status,
                "cost_usd": cost_usd,
                "lower_bound_cost_usd": lower_bound_cost_usd,
                "cost_note": cost_note,
                "observed_models": sorted(list(observed_models)),
                "observed_providers": sorted(list(observed_providers)),
                "observed_tiers": sorted(list(observed_tiers)),
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
        """Persist reports in a unique run directory with full provenance hashes."""
        run_dir = base_output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        raw_cases = [r.as_dict() for r in results]
        raw_json_bytes = json.dumps(raw_cases, indent=2, ensure_ascii=False).encode("utf-8")
        raw_records_sha256 = hashlib.sha256(raw_json_bytes).hexdigest().upper()

        # Compute safe local expected hashes of deployed service assets (not legacy policies or offline manifests)
        repo_root = Path(__file__).resolve().parents[2]
        approved_kb_v2 = repo_root / "data" / "knowledge" / "approved_kb.v2.json"
        approved_kb_hash = compute_sha256(approved_kb_v2) if approved_kb_v2.exists() else None

        ai_service_release = repo_root / "apps" / "ai_service" / "kb-release.json"
        ai_service_release_hash = compute_sha256(ai_service_release) if ai_service_release.exists() else None

        policy_path = repo_root / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json"
        policy_hash = compute_sha256(policy_path) if policy_path.exists() else None

        runner_cfg = summary_data["meta"].get("runner_config", {})
        safe_config_json = json.dumps(runner_cfg, sort_keys=True).encode("utf-8")
        config_hash = hashlib.sha256(safe_config_json).hexdigest().upper()

        # Distinguish local expectations from observed live service versions
        observed_live_service = {
            "release_id": sorted(list({r.versions.get("release_id") for r in results if r.versions.get("release_id")})),
            "model_version": sorted(list({(r.llm_metadata.get("model_version") or r.versions.get("model_version")) for r in results if (r.llm_metadata.get("model_version") or r.versions.get("model_version"))})),
            "kb_version": sorted(list({r.versions.get("kb_version") for r in results if r.versions.get("kb_version")})),
            "prompt_version": sorted(list({(r.llm_metadata.get("prompt_version") or r.versions.get("prompt_version")) for r in results if (r.llm_metadata.get("prompt_version") or r.versions.get("prompt_version"))})),
            "llm_model": sorted(list({(r.llm_metadata.get("model") or r.versions.get("llm_model") or r.llm_model) for r in results if (r.llm_metadata.get("model") or r.versions.get("llm_model") or r.llm_model)})),
            "provider": sorted(list({(r.llm_metadata.get("provider") or r.versions.get("provider")) for r in results if (r.llm_metadata.get("provider") or r.versions.get("provider"))})),
        }

        summary_data["meta"].update({
            "raw_records_sha256": raw_records_sha256,
            "local_expected_provenance_hashes": {
                "approved_kb_v2_sha256": approved_kb_hash,
                "ai_service_kb_release_sha256": ai_service_release_hash,
                "routing_policy_sha256": policy_hash,
                "runner_config_sha256": config_hash,
            },
            "observed_live_service_provenance": observed_live_service,
        })

        raw_file = run_dir / "raw_records.json"
        raw_file.write_bytes(raw_json_bytes)

        json_file = run_dir / "acceptance_e2e_report.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        md_content = self._render_markdown(summary_data)
        md_file = run_dir / "acceptance_e2e_report.md"
        md_file.write_text(md_content, encoding="utf-8")

        latest_pointer = base_output_dir / "latest_run.json"
        latest_data = {
            "latest_run_id": run_id,
            "run_dir": str(run_dir),
            "timestamp": summary_data["meta"]["timestamp"],
            "runner_checks_passed": summary_data["acceptance_summary"]["runner_checks_passed"],
            "mode": summary_data["meta"]["mode"],
            "boundary_kind": "in_process_asgi_testclient",
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
        mean_str = f"{p['mean_seconds']:.3f}s" if p.get("mean_seconds") is not None else "None"
        err_rate_val = p.get("error_rate", 0.0) or 0.0
        error_rate_str = f"{err_rate_val * 100:.1f}%"

        lines = [
            f"# SupportIQ — End-to-End Application Acceptance Report{headline_suffix}",
            "",
            f"- **Run ID:** `{meta['run_id']}`",
            f"- **Timestamp:** `{meta['timestamp']}`",
            f"- **Git HEAD:** `{meta.get('git_commit', 'unknown')}`",
            f"- **Mode:** `{meta['mode']}`",
            f"- **Boundary Kind:** `{meta.get('boundary_kind', 'in_process_asgi_testclient')}`",
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
            "> 1. **100% Human Oversight:** Unreviewed AI drafts never reach the customer (`customer_reply is None` on verified HTTP 200 response).",
            "> 2. **Performance Target:** End-to-end p95 latency must be <= 12.0s under declared test conditions with complete latency measurement coverage.",
            "> 3. **Truthful Pricing:** Cost in USD is reported only when verified primary pricing is provided and model matches exactly; missing pricing remains `unavailable`, never 0.0.",
            "",
            "## 1. Acceptance Gates & Quality Checks",
            "",
            "| Gate | Observed Value | Requirement | Status |",
            "|---|---|---|:---:|",
            f"| **Human Oversight (No Auto-Send)** | {s['auto_send_violations']} violations | 0 violations (`customer_reply is None` on verified HTTP 200) | **{'PASS' if s['human_oversight_enforced'] else 'FAIL'}** |",
            f"| **p95 Latency** | `{p95_str}` | <= 12.000s | **{'PASS' if p['target_p95_met'] else 'FAIL'}** |",
            f"| **Latency Measurement Coverage** | {'100% Complete' if s.get('latency_coverage_complete') else 'Incomplete/Invalid'} | All cases must report valid finite latency | **{'PASS' if s.get('latency_coverage_complete') else 'FAIL'}** |",
            f"| **Technical Errors** | `{s['technical_errors']}` | 0 errors | **{'PASS' if s['technical_errors'] == 0 else 'FAIL'}** |",
            f"| **Timeouts** | `{s['timeouts']}` | 0 timeouts | **{'PASS' if s['timeouts'] == 0 else 'FAIL'}** |",
            f"| **Failed Background Jobs** | `{s['failed_jobs']}` | 0 failures | **{'PASS' if s['failed_jobs'] == 0 else 'FAIL'}** |",
            "",
            "## 2. Latency Analysis & Strata (Draft-Producing vs Abstention, Cold vs Warm)",
            "",
            f"- **Overall p50 Latency:** `{p50_str}`",
            f"- **Overall p95 Latency:** `{p95_str}`",
            f"- **Overall Mean Latency:** `{mean_str}`",
            f"- **Overall Error Rate:** `{error_rate_str}`",
            f"- **Min / Max Latency:** `{min_str}` / `{max_str}`",
            "",
            "| Stratum / Condition | Cases (n) | p50 | p95 | Mean | Error Rate | Description |",
            "|---|---:|---:|---:|---:|---:|---|",
        ])

        strata = p.get("strata", {})
        draft_info = strata.get("draft_producing", {})
        draft_p50 = f"`{draft_info['p50_seconds']:.3f}s`" if draft_info.get("p50_seconds") is not None else "`None`"
        draft_p95 = f"`{draft_info['p95_seconds']:.3f}s`" if draft_info.get("p95_seconds") is not None else "`None`"
        draft_mean = f"`{draft_info['mean_seconds']:.3f}s`" if draft_info.get("mean_seconds") is not None else "`None`"
        draft_err = f"{draft_info.get('error_rate', 0.0) * 100:.1f}%"
        lines.append(
            f"| **Draft-Producing** | {draft_info.get('count', 0)} | {draft_p50} | {draft_p95} | {draft_mean} | {draft_err} | {draft_info.get('description', 'Tickets reaching draft generation')} |"
        )

        abstain_info = strata.get("abstention", {})
        abstain_p50 = f"`{abstain_info['p50_seconds']:.3f}s`" if abstain_info.get("p50_seconds") is not None else "`None`"
        abstain_p95 = f"`{abstain_info['p95_seconds']:.3f}s`" if abstain_info.get("p95_seconds") is not None else "`None`"
        abstain_mean = f"`{abstain_info['mean_seconds']:.3f}s`" if abstain_info.get("mean_seconds") is not None else "`None`"
        abstain_err = f"{abstain_info.get('error_rate', 0.0) * 100:.1f}%"
        lines.append(
            f"| **Abstention / Escalate** | {abstain_info.get('count', 0)} | {abstain_p50} | {abstain_p95} | {abstain_mean} | {abstain_err} | {abstain_info.get('description', 'Tickets abstaining or escalating before LLM')} |"
        )

        overall_info = strata.get("overall", {})
        all_p50 = f"`{overall_info['p50_seconds']:.3f}s`" if overall_info.get("p50_seconds") is not None else "`None`"
        all_p95 = f"`{overall_info['p95_seconds']:.3f}s`" if overall_info.get("p95_seconds") is not None else "`None`"
        all_mean = f"`{overall_info['mean_seconds']:.3f}s`" if overall_info.get("mean_seconds") is not None else "`None`"
        all_err = f"{overall_info.get('error_rate', 0.0) * 100:.1f}%"
        lines.append(
            f"| **All Submitted Tickets** | {overall_info.get('count', 0)} | {all_p50} | {all_p95} | {all_mean} | {all_err} | {overall_info.get('description', 'All tickets across all outcomes')} |"
        )

        cold_info = p["conditions"]["cold"]
        cold_lat_str = f"`{cold_info['latency_seconds']:.3f}s`" if cold_info["latency_seconds"] is not None else "`None`"
        cold_mean_str = f"`{cold_info['mean_seconds']:.3f}s`" if cold_info.get("mean_seconds") is not None else "`None`"
        cold_err = f"{cold_info.get('error_rate', 0.0) * 100:.1f}%"
        lines.append(
            f"| **Cold Start** | {cold_info['count']} | {cold_lat_str} | {cold_lat_str} | {cold_mean_str} | {cold_err} | Initial submission: application connection and DB pool cold start (NOT model cold start) |"
        )

        warm_info = p["conditions"]["warm"]
        warm_p50 = f"`{warm_info['p50_seconds']:.3f}s`" if warm_info["p50_seconds"] is not None else "`None`"
        warm_p95 = f"`{warm_info['p95_seconds']:.3f}s`" if warm_info["p95_seconds"] is not None else "`None`"
        warm_mean_str = f"`{warm_info['mean_seconds']:.3f}s`" if warm_info.get("mean_seconds") is not None else "`None`"
        warm_err = f"{warm_info.get('error_rate', 0.0) * 100:.1f}%"
        lines.append(
            f"| **Warm Runs** | {warm_info['count']} | {warm_p50} | {warm_p95} | {warm_mean_str} | {warm_err} | Subsequent tickets on warmed worker thread |"
        )

        prompt_str = str(tc["total_prompt_tokens"]) if tc["total_prompt_tokens"] is not None else "Unknown (incomplete token coverage)"
        candidate_str = str(tc["total_candidate_tokens"]) if tc["total_candidate_tokens"] is not None else "Unknown (incomplete token coverage)"
        reported_tot_str = str(tc.get("provider_reported_total_tokens")) if tc.get("provider_reported_total_tokens") is not None else "N/A"
        thought_str = str(tc["total_thinking_tokens"]) if tc["total_thinking_tokens"] is not None else f"Unknown (observed partial: {tc.get('observed_thought_tokens', 0)}; thoughts NOT assumed zero)"
        completion_str = str(tc["total_completion_tokens"]) if tc["total_completion_tokens"] is not None else "Unknown (missing thought tokens)"
        total_str = str(tc["total_tokens"]) if tc["total_tokens"] is not None else f"Unknown (observed partial: {tc.get('observed_partial_tokens', 'N/A')})"

        lines.extend([
            "",
            "## 3. Token Usage and Pricing Coverage",
            "",
            f"- **Prompt / Input Tokens:** `{prompt_str}`",
            f"- **Candidate / Output Tokens:** `{candidate_str}`",
            f"- **Provider-Reported Total Tokens:** `{reported_tot_str}`",
            f"- **Thought Tokens:** `{thought_str}` ({'complete coverage' if tc.get('all_requests_tracked_thinking') else ('partial/untracked' if tc.get('thinking_tracked') else 'omitted/untracked')})",
            f"- **Total Completion Tokens (Billable Output):** `{completion_str}`",
            f"- **Total Tokens:** `{total_str}`",
            f"- **Cost Status:** `{tc['cost_status']}`",
            f"- **Estimated Cost (USD):** `{tc['cost_usd'] if tc['cost_usd'] is not None else 'UNAVAILABLE'}`",
            f"- **Lower Bound Cost (USD):** `{tc['lower_bound_cost_usd'] if tc.get('lower_bound_cost_usd') is not None else 'N/A'}`",
            f"- **Pricing Note:** {tc['cost_note']}",
        ])

        if tc.get("derivation_provenance"):
            dp = tc["derivation_provenance"]
            lines.extend([
                "",
                "> [!NOTE]",
                f"> **Derived Output Tokens Provenance:** `{dp['derived_output_tokens']}` output tokens derived from provider-reported `totalTokenCount` ({dp['raw_reported_total_tokens']} - {dp['total_prompt_tokens']} = {dp['derived_output_tokens']}) under official Gemini API billing semantics for text-only/no-tools requests (source: `{dp['source_doc']}`). Provider omitted `thoughtsTokenCount`; thoughts are **NOT** asserted to be zero.",
            ])

        lines.extend([
            "",
            "## 4. Case Execution Summary",
            "",
            "| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |",
            "|---|:---:|---|---|---:|:---:|:---:|:---:|",
        ])

        for c in summary["cases"]:
            wall_str = str(c["wall_latency_ms"]) if c["wall_latency_ms"] is not None else "None"
            auto_safe_str = "YES" if (c["reply_is_none"] and c.get("observation_succeeded", True)) else "**NO**"
            lines.append(
                f"| {c['case_index']} | `{c['condition']}` | `{c['ticket_id'] or 'None'}` | "
                f"{c['message'][:30]}... | {wall_str} | `{c['draft_status']}` | "
                f"{auto_safe_str} | {'**PASS**' if c['is_success'] else '**FAIL**'} |"
            )

        lines.extend([
            "",
            "## 5. Deployed Provenance Hashes & Live Service Versions",
            "",
            "> [!NOTE]",
            "> Local asset hashes represent local deployment expectations. Observed service versions reflect runtime responses from the service under test.",
            "",
            "| Asset / Property | Kind | Identifier / Value | Hash (SHA-256) |",
            "|---|:---:|---|---|",
        ])

        expected_hashes = meta.get("local_expected_provenance_hashes", {})
        lines.append(f"| **Deployed Knowledge Base** | Local Asset | `data/knowledge/approved_kb.v2.json` | `{expected_hashes.get('approved_kb_v2_sha256', 'N/A')}` |")
        lines.append(f"| **Gateway Release Manifest** | Local Asset | `apps/ai_service/kb-release.json` | `{expected_hashes.get('ai_service_kb_release_sha256', 'N/A')}` |")
        lines.append(f"| **Routing Policy** | Local Asset | `apps/core_backend/config/policies/intent_policy.v2.json` | `{expected_hashes.get('routing_policy_sha256', 'N/A')}` |")
        lines.append(f"| **Runner Configuration** | Local Config | *(safe without secrets)* | `{expected_hashes.get('runner_config_sha256', 'N/A')}` |")
        lines.append(f"| **Raw Execution Records** | Run Output | `raw_records.json` | `{meta.get('raw_records_sha256', 'N/A')}` |")

        live_prov = meta.get("observed_live_service_provenance", {})
        lines.extend([
            "",
            "### Observed Live Service Metadata",
            "",
            f"- **Observed Release ID(s):** `{live_prov.get('release_id') or ['unobserved']}`",
            f"- **Observed Model Version(s):** `{live_prov.get('model_version') or ['unobserved']}`",
            f"- **Observed KB Version(s):** `{live_prov.get('kb_version') or ['unobserved']}`",
            f"- **Observed Prompt Version(s):** `{live_prov.get('prompt_version') or ['unobserved']}`",
            f"- **Observed LLM Model(s):** `{live_prov.get('llm_model') or ['unobserved']}`",
            f"- **Observed Provider(s):** `{live_prov.get('provider') or ['unobserved']}`",
            "",
            "## 6. Verification Commands for Integration",
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

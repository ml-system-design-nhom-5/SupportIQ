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
import secrets
import socketserver
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
            time.sleep(1.5)  # Longer than analysis timeout in test settings
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
                "llm_usage": {"prompt_tokens": 128, "completion_tokens": 42, "total_tokens": 170},
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
        self.server.shutdown()
        self.server.server_close()


@dataclass
class TicketCaseResult:
    case_index: int
    condition: str  # "cold" or "warm"
    message: str
    ticket_id: Optional[str]
    wall_latency_ms: float
    analysis_status: str
    draft_status: str
    customer_reply_is_none: bool  # Safety invariant check
    step_latency_ms: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, int] = field(default_factory=dict)
    error_code: Optional[str] = None
    is_terminal: bool = False
    is_success: bool = False


@dataclass
class ApplicationAcceptanceConfig:
    secrets_path: Optional[str] = None
    mode: str = "mock"  # "mock" or "live"
    live_ai_url: Optional[str] = None
    num_warm_requests: int = 4
    poll_timeout_seconds: float = 25.0
    verified_pricing: Optional[Dict[str, Any]] = None
    # pricing structure: {"input_cost_per_million": float, "output_cost_per_million": float, "source_document": str}


def resolve_database_url(secrets_path: Optional[str] = None) -> Tuple[str, Dict[str, str]]:
    """Resolve owner database URL from secrets file or environment."""
    candidates = []
    if secrets_path:
        candidates.append(Path(secrets_path))
    candidates.extend([
        Path(".local/application.json"),
        Path("F:/Năm 3/SD/project/SupportIQ/.local/application.json"),
    ])
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


class ApplicationAcceptanceRunner:
    """Executes end-to-end application acceptance testing with isolated schemas."""

    def __init__(self, config: ApplicationAcceptanceConfig):
        self.config = config

    def run(self, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        configure_runtime_environment()
        owner_url, default_passwords = resolve_database_url(self.config.secrets_path)

        schema = "accept_" + uuid.uuid4().hex[:12]
        root_engine = create_engine(owner_url, hide_parameters=True)
        with root_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        mock_server = None
        if self.config.mode == "mock":
            mock_server = EphemeralMockAIServer(mode="normal")
            mock_server.start()
            ai_base_url = mock_server.base_url
        else:
            ai_base_url = self.config.live_ai_url or "http://127.0.0.1:8002"

        app_engine = None
        try:
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
                ai_service_analysis_timeout_ms=1000,
                ai_service_draft_timeout_ms=1500,
                job_poll_interval_ms=50,
            )

            # Customer test client with worker enabled, staff test client without separate worker
            with TestClient(create_app(settings=settings, database=database, start_worker=True)) as customer, \
                 TestClient(create_app(settings=settings, database=database, start_worker=False)) as staff:

                for client, role in ((customer, "customer"), (staff, "staff")):
                    client.headers["Origin"] = "http://testserver"
                    auth_resp = client.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
                    if auth_resp.status_code != 201:
                        raise RuntimeError(f"Failed to authenticate as {role}: {auth_resp.text}")

                # Test cases (1 cold, N warm)
                test_messages = [
                    "What is your return policy?",
                    "Can I return an item I bought last week?",
                    "How long do I have to make a return?",
                    "Do you offer refunds for returned items?",
                    "What are the return shipping costs?",
                ]
                total_cases = 1 + self.config.num_warm_requests
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

                    # Check 100% human oversight invariant: unreviewed draft never reaches customer!
                    cust_view = customer.get(f"/v1/shop/tickets/{t_id}").json()
                    customer_reply = cust_view.get("reply")
                    reply_is_none = customer_reply is None

                    a_stat = suggestion_data.get("analysis_status", "timeout" if not reached_terminal else "unknown")
                    d_stat = suggestion_data.get("draft_status", "timeout" if not reached_terminal else "unknown")
                    step_lat = suggestion_data.get("step_latency_ms", {})
                    tokens = suggestion_data.get("llm_usage", {}) or {}

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
                        error_code=suggestion_data.get("failure_code") or (None if reached_terminal else "timeout"),
                        is_terminal=reached_terminal,
                        is_success=success,
                    ))

                # Compute summary metrics
                return self._compute_summary(results, output_dir)

        finally:
            if mock_server:
                mock_server.stop()
            if app_engine:
                app_engine.dispose()
            with root_engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            root_engine.dispose()

    def _compute_summary(self, results: List[TicketCaseResult], output_dir: Optional[Path]) -> Dict[str, Any]:
        latencies_sec = [r.wall_latency_ms / 1000.0 for r in results]
        latencies_sorted = sorted(latencies_sec)

        cold_lats = [r.wall_latency_ms / 1000.0 for r in results if r.condition == "cold"]
        warm_lats = [r.wall_latency_ms / 1000.0 for r in results if r.condition == "warm"]

        p50 = (latencies_sorted[(len(latencies_sorted) - 1) // 2] + latencies_sorted[len(latencies_sorted) // 2]) / 2.0 if latencies_sorted else 0.0
        p95_idx = max(0, math.ceil(0.95 * len(latencies_sorted)) - 1)
        p95 = latencies_sorted[p95_idx] if latencies_sorted else 0.0

        p50_cold = cold_lats[0] if cold_lats else 0.0
        p95_warm = sorted(warm_lats)[max(0, math.ceil(0.95 * len(warm_lats)) - 1)] if warm_lats else 0.0

        technical_errors = sum(1 for r in results if r.analysis_status == "error" or r.draft_status == "error")
        timeouts = sum(1 for r in results if not r.is_terminal or r.analysis_status == "timeout")
        failed_jobs = sum(1 for r in results if r.draft_status in ("failed", "unavailable"))
        auto_send_violations = sum(1 for r in results if not r.customer_reply_is_none)

        # Token usage aggregation
        total_prompt_tokens = sum(r.tokens.get("prompt_tokens", r.tokens.get("input_tokens", 0)) for r in results)
        total_candidate_tokens = sum(r.tokens.get("candidate_tokens", r.tokens.get("completion_tokens", 0)) for r in results)
        total_thinking_tokens = sum(r.tokens.get("thinking_tokens", 0) for r in results)
        has_thinking_tracked = any("thinking_tokens" in r.tokens for r in results)
        total_completion_tokens = total_candidate_tokens + total_thinking_tokens
        total_tokens = sum(r.tokens.get("total_tokens", 0) for r in results) or (total_prompt_tokens + total_completion_tokens)

        # Cost computation with strict verified primary pricing requirement
        pricing = self.config.verified_pricing
        cost_status = "unavailable"
        cost_usd = None
        cost_note = "Pricing details unverified or missing; cost is strictly unavailable (not 0.0)."

        if pricing and isinstance(pricing, dict):
            in_rate = pricing.get("input_cost_per_million")
            out_rate = pricing.get("output_cost_per_million")
            has_rates = in_rate is not None and out_rate is not None and in_rate > 0 and out_rate > 0
            has_provenance = bool(pricing.get("source_url") and pricing.get("verified_on") and pricing.get("model"))

            if has_rates and has_provenance:
                cost_status = "verified_list_price_estimate"
                output_tokens_for_cost = total_candidate_tokens + total_thinking_tokens
                cost_usd = (total_prompt_tokens * in_rate + output_tokens_for_cost * out_rate) / 1_000_000.0
                thinking_disclosure = "including thinking tokens" if has_thinking_tracked else "thinking tokens omitted/untracked in source records (no assumed zero)"
                cost_note = (
                    f"List-price estimate for {pricing.get('model')} ({pricing.get('tier', 'standard_paid')}) "
                    f"based on primary source {pricing.get('source_url')} verified on {pricing.get('verified_on')}. "
                    f"Calculated with {thinking_disclosure}. Not an invoiced account-tier charge."
                )
            elif has_rates:
                cost_status = "arithmetic_fixture_unverified"
                cost_usd = (total_prompt_tokens * in_rate + total_completion_tokens * out_rate) / 1_000_000.0
                cost_note = "Arithmetic unit test fixture only; unverified rates without primary provider documentation or verified_on provenance."

        # Target verification
        p95_target_met = bool(p95 <= 12.0)
        oversight_target_met = (auto_send_violations == 0)
        is_mock = (self.config.mode == "mock")
        acceptance_passed = (
            all(r.is_success for r in results)
            and p95_target_met
            and oversight_target_met
            and timeouts == 0
            and failed_jobs == 0
        )

        summary_data = {
            "meta": {
                "run_id": f"accept-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": self.config.mode,
                "evidence_kind": "mock_runner_simulation" if is_mock else "bounded_live",
                "scope": "end_to_end_application_acceptance",
                "boundary": "POST /v1/shop/tickets -> PostgreSQL job -> GET /v1/console/tickets/{id} terminal state",
                "certification_scope": "mock_simulation_only" if is_mock else "bounded_live_run",
            },
            "acceptance_summary": {
                "overall_passed": acceptance_passed,
                "mock_only_evaluation": is_mock,
                "global_production_accepted": False if is_mock else acceptance_passed,
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
                "min_seconds": min(latencies_sec) if latencies_sec else 0.0,
                "max_seconds": max(latencies_sec) if latencies_sec else 0.0,
                "target_p95_met": p95_target_met,
                "target_threshold_seconds": 12.0,
                "conditions": {
                    "cold": {
                        "count": len(cold_lats),
                        "latency_seconds": p50_cold,
                        "description": "Initial ticket on fresh session / cold worker connection",
                    },
                    "warm": {
                        "count": len(warm_lats),
                        "p50_seconds": (sorted(warm_lats)[len(warm_lats) // 2]) if warm_lats else 0.0,
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
                "total_tokens": total_tokens,
                "cost_status": cost_status,
                "cost_usd": cost_usd,
                "cost_note": cost_note,
            },
            "cases": [
                {
                    "case_index": r.case_index,
                    "condition": r.condition,
                    "message": r.message,
                    "ticket_id": r.ticket_id,
                    "wall_latency_ms": r.wall_latency_ms,
                    "analysis_status": r.analysis_status,
                    "draft_status": r.draft_status,
                    "reply_is_none": r.customer_reply_is_none,
                    "is_success": r.is_success,
                    "error_code": r.error_code,
                    "tokens": r.tokens,
                }
                for r in results
            ],
        }

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            json_file = output_dir / "acceptance_e2e_report.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            md_content = self._render_markdown(summary_data)
            md_file = output_dir / "acceptance_e2e_report.md"
            md_file.write_text(md_content, encoding="utf-8")

        return summary_data

    def _render_markdown(self, summary: Dict[str, Any]) -> str:
        s = summary["acceptance_summary"]
        p = summary["performance"]
        tc = summary["tokens_and_cost"]

        lines = [
            "# SupportIQ — End-to-End Application Acceptance Report",
            "",
            f"- **Run ID:** `{summary['meta']['run_id']}`",
            f"- **Timestamp:** `{summary['meta']['timestamp']}`",
            f"- **Mode:** `{summary['meta']['mode']}`",
            f"- **Overall Acceptance Status:** **{'PASSED' if s['overall_passed'] else 'FAILED'}**",
            "",
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
            f"| **p95 Latency** | `{p['p95_seconds']:.3f}s` | <= 12.000s | **{'PASS' if p['target_p95_met'] else 'FAIL'}** |",
            f"| **Technical Errors** | `{s['technical_errors']}` | 0 errors | **{'PASS' if s['technical_errors'] == 0 else 'FAIL'}** |",
            f"| **Timeouts** | `{s['timeouts']}` | 0 timeouts | **{'PASS' if s['timeouts'] == 0 else 'FAIL'}** |",
            f"| **Failed Background Jobs** | `{s['failed_jobs']}` | 0 failures | **{'PASS' if s['failed_jobs'] == 0 else 'FAIL'}** |",
            "",
            "## 2. Latency Analysis (Cold vs Warm Conditions)",
            "",
            f"- **Overall p50 Latency:** `{p['p50_seconds']:.3f}s`",
            f"- **Overall p95 Latency:** `{p['p95_seconds']:.3f}s`",
            f"- **Min / Max Latency:** `{p['min_seconds']:.3f}s` / `{p['max_seconds']:.3f}s`",
            "",
            "| Condition | Cases (n) | Latency (p50 / p95) | Description |",
            "|---|---:|---|---|",
            f"| **Cold Start** | {p['conditions']['cold']['count']} | `{p['conditions']['cold']['latency_seconds']:.3f}s` (first call) | Initial submission on fresh session / connection pool pickup |",
            f"| **Warm Runs** | {p['conditions']['warm']['count']} | p50: `{p['conditions']['warm']['p50_seconds']:.3f}s`, p95: `{p['conditions']['warm']['p95_seconds']:.3f}s` | Subsequent tickets on warmed worker thread |",
            "",
            "## 3. Token Usage and Pricing Coverage",
            "",
            f"- **Prompt / Input Tokens:** `{tc['total_prompt_tokens']}`",
            f"- **Candidate Tokens:** `{tc.get('total_candidate_tokens', 0)}`",
            f"- **Thinking Tokens:** `{tc.get('total_thinking_tokens', 0)}` ({'tracked' if tc.get('thinking_tracked') else 'omitted/untracked'})",
            f"- **Total Output Tokens:** `{tc['total_completion_tokens']}`",
            f"- **Total Tokens:** `{tc['total_tokens']}`",
            f"- **Cost Status:** `{tc['cost_status']}`",
            f"- **Estimated Cost (USD):** `{tc['cost_usd'] if tc['cost_usd'] is not None else 'UNAVAILABLE'}`",
            f"- **Pricing Note:** {tc['cost_note']}",
            "",
            "## 4. Case Execution Summary",
            "",
            "| # | Condition | Ticket ID | Message | Wall Latency (ms) | Draft Status | Auto-Send Safe | Success |",
            "|---|:---:|---|---|---:|:---:|:---:|:---:|",
        ]

        for c in summary["cases"]:
            lines.append(
                f"| {c['case_index']} | `{c['condition']}` | `{c['ticket_id'] or 'None'}` | "
                f"{c['message'][:30]}... | {c['wall_latency_ms']} | `{c['draft_status']}` | "
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

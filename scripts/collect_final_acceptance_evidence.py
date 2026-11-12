#!/usr/bin/env python3
"""Isolated PostgreSQL Application Evidence Collector for SupportIQ Final Acceptance.

Worker C Scope:
- Executes 24 synthetic scenarios covering:
  * 12 core product intents (answerable from active approved KB)
  * Sensitive / authority / escalation scenarios
  * No-source / unsupported scenarios
  * Out-of-domain (OOD) scenarios
  * Honest separate injected fixture boundary (temporal expiry & conflicting policies)
- Captures:
  * Full draft text and structured citations
  * Immutable full source snapshots (doc_id, version, title, content_hash, content, valid_from, valid_to)
  * Raw model and routing metadata (intent, probability, confidence_band, recommendation, reason_codes)
  * Usage metadata (input_tokens, output_tokens, thought_tokens if present, total_tokens, provider, model)
  * Measured submit-to-terminal wall-clock latency
  * Explicit customer no-auto-send observation (verifying 100% human oversight invariant)
- Prepares paired same-case tasks with alternating order (assisted vs manual) for coordinator evaluation.
- Operates strictly in isolated PostgreSQL schemas (e.g. accept_final_*) without database resets or root edits.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import http.server
import json
import math
import os
from pathlib import Path
import platform
import socketserver
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.seed import seed
from scripts.native_runtime import configure_runtime_environment


def compute_sha256(path: Path | str) -> str:
    """Compute lowercase SHA-256 of file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_bytes_sha256(data: bytes) -> str:
    """Compute lowercase SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


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


def resolve_database_url(secrets_path: Optional[str] = None) -> Tuple[str, Dict[str, str]]:
    """Resolve owner database URL from SUPPORTIQ_APPLICATION_SECRETS, explicit path, or local fallback."""
    candidates: List[Path] = []

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

    if secrets_path:
        candidates.append(Path(secrets_path))

    candidates.append(REPO_ROOT / ".local" / "application.json")
    candidates.append(Path("F:/Năm 3/SD/project/SupportIQ/.local/application.json"))

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


class MockAcceptanceGatewayHandler(http.server.BaseHTTPRequestHandler):
    """Deterministic loopback mock AI gateway handler for offline acceptance testing."""

    cases_by_query: Dict[str, Dict[str, Any]] = {}
    active_docs: Dict[str, Dict[str, Any]] = {}
    injected_docs: Dict[str, Dict[str, Any]] = {}
    server_mode: str = "normal"  # "normal", "error", "timeout"

    def log_message(self, format, *args):
        # Suppress stdout noise during testing
        pass

    def do_GET(self):
        if self.path in ("/health/live", "/health/ready"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ready", "mock": true, "llm_enabled": true}')
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        mode = getattr(self.server, "mode", self.server_mode)
        if mode == "error":
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail": "Simulated AI service gateway error"}')
            return

        if mode == "timeout":
            time.sleep(3.5)
            self.send_response(504)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail": "Simulated AI service timeout"}')
            return

        path = self.path
        message = body.get("message", "")
        matched_case = self.cases_by_query.get(message)

        # Robust token overlap fallback if query was pseudonymized or formatted
        if not matched_case:
            import re
            cleaned_msg = re.sub(r"\[[A-Z0-9_]+\]", " ", message)
            p_toks = set(re.findall(r"[a-zA-Z0-9]+", cleaned_msg.lower()))
            best_score = -1.0
            for q, c in self.cases_by_query.items():
                c_toks = set(re.findall(r"[a-zA-Z0-9]+", q.lower()))
                score = len(p_toks & c_toks) / max(len(p_toks | c_toks), 1)
                if score > best_score:
                    best_score = score
                    matched_case = c

        intent_label = matched_case.get("intent", "return_policy") if matched_case else "return_policy"
        category = matched_case.get("category", "product_intent") if matched_case else "product_intent"
        expected_action = matched_case.get("expected_action", "draft") if matched_case else "draft"
        expected_reasons = matched_case.get("expected_reasons", []) if matched_case else []
        expected_docs = matched_case.get("expected_docs", []) if matched_case else []

        # Build analysis response
        retrieved_documents = []
        if expected_action == "draft" and expected_docs:
            for doc_key in expected_docs:
                parts = doc_key.split(":")
                d_id = parts[0]
                doc_meta = self.active_docs.get(d_id, {})
                retrieved_documents.append({
                    "doc_id": d_id,
                    "version": doc_meta.get("version", parts[1] if len(parts) > 1 else "1.0"),
                    "title": doc_meta.get("title", f"Policy {d_id}"),
                    "snippet": doc_meta.get("content", "Policy document excerpt.")[:160],
                })

        analysis_res = {
            "intent": {
                "label": intent_label,
                "probability": 0.95 if expected_action == "draft" else 0.50,
                "confidence_band": "high" if expected_action == "draft" else "medium",
            },
            "routing": {
                "recommendation": expected_action,
                "reason_codes": expected_reasons,
                "action": "retrieve_draft" if expected_action == "draft" else ("escalate" if expected_action == "escalate" else "clarify"),
                "requested_team": "support_specialist" if expected_action == "escalate" else "general_support",
            },
            "alternatives": [],
            "documents": retrieved_documents,
            "warnings": [],
            "versions": {
                "release_id": "mock-acceptance-rel-v1",
                "model_version": "v1.0.0",
                "kb_version": "mock-kb-v2.0",
                "prompt_version": "grounded-v2",
                "routing_version": "mock-routing-v2",
                "index_version": "mock-index-v1.5",
            },
            "step_latency_ms": {"classify_ms": 14, "route_ms": 2, "retrieve_ms": 18},
        }

        if "/analyses" in path:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(analysis_res).encode("utf-8"))
            return

        if "/drafts" in path:
            draft_status = (
                "draft_ready" if expected_action == "draft"
                else ("escalation_recommended" if expected_action == "escalate" else "abstained")
            )
            draft_body = None
            if draft_status == "draft_ready" and retrieved_documents:
                doc_item = retrieved_documents[0]
                d_id = doc_item["doc_id"]
                d_ver = doc_item["version"]
                doc_full = self.active_docs.get(d_id, {})
                content = doc_full.get("content", "Our standard customer service policy.")
                span = content[:50] if len(content) >= 50 else content
                draft_body = {
                    "segments": [
                        {"paragraph_index": 0, "text": f"Thank you for contacting customer support regarding your inquiry. Based on our policy, {content[:180]}."},
                        {"paragraph_index": 1, "text": "Please let us know if you need any additional assistance with this matter."}
                    ],
                    "citations": [
                        {
                            "source_type": "document",
                            "doc_id": d_id,
                            "version": d_ver,
                            "field": "policy_body",
                            "span": span,
                        }
                    ],
                }

            draft_res = {
                "status": draft_status,
                "reason_codes": expected_reasons,
                "analysis": analysis_res,
                "draft": draft_body,
                "step_latency_ms": {"analysis_ms": 34, "draft_ms": 210, "llm_ms": 185},
                "llm_usage": {
                    "input_tokens": 1240,
                    "output_tokens": 145,
                    "thought_tokens": 0,
                    "total_tokens": 1385,
                } if draft_status == "draft_ready" else {},
                "llm_metadata": {
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "model_version": "gemini-3.1-flash-lite",
                    "prompt_version": "grounded-v2",
                } if draft_status == "draft_ready" else {},
                "versions": analysis_res["versions"],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(draft_res).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


class EphemeralMockAIGateway:
    """Spins up a local loopback mock AI server in a daemon thread."""

    def __init__(
        self,
        cases: List[Dict[str, Any]],
        active_docs: Dict[str, Dict[str, Any]],
        injected_docs: Dict[str, Dict[str, Any]],
        mode: str = "normal",
    ):
        handler_cls = MockAcceptanceGatewayHandler
        handler_cls.cases_by_query = {c["query"]: c for c in cases}
        handler_cls.active_docs = active_docs
        handler_cls.injected_docs = injected_docs
        handler_cls.server_mode = mode

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler_cls)
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
class EvidenceCaseRecord:
    case_id: str
    category: str
    slice: str
    query: str
    intent: str
    order_context: Dict[str, Any]
    expected_action: str
    expected_docs: List[str]
    expected_reasons: List[str]
    fixture_boundary: str  # "active_kb" or "injected_synthetic"
    as_of: str
    ticket_id: Optional[str]
    submit_to_terminal_latency_ms: Optional[float]
    terminal_status: str
    analysis_status: str
    draft_status: str
    customer_no_auto_send_observed: bool
    customer_reply_is_none: bool
    customer_http_status: int
    raw_model_routing: Dict[str, Any]
    full_draft_text: Optional[str]
    citations: List[Dict[str, Any]]
    source_snapshots: Dict[str, Any]  # Keyed by doc_id:version -> full metadata + content
    usage_metadata: Dict[str, Any]
    step_latencies_ms: Dict[str, Any]
    error_code: Optional[str]
    is_terminal: bool
    is_success: bool


class AcceptanceEvidenceCollector:
    """Orchestrates isolated PostgreSQL application execution and gathers full evidence."""

    def __init__(
        self,
        mode: str = "mock",
        suite_path: Path | str = REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl",
        manifest_path: Path | str = REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json",
        fixtures_path: Path | str = REPO_ROOT / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json",
        paired_tasks_path: Path | str = REPO_ROOT / "data/benchmarks/final_acceptance/paired_agent_tasks.json",
        active_kb_path: Path | str = REPO_ROOT / "data/knowledge/approved_kb.v2.json",
        secrets_path: Optional[str] = None,
        live_ai_url: str = "http://127.0.0.1:8002",
        poll_timeout_seconds: float = 30.0,
        max_cases: Optional[int] = None,
        keep_schema: bool = False,
        mock_mode: str = "normal",
    ):
        self.mode = mode
        self.suite_path = Path(suite_path)
        self.manifest_path = Path(manifest_path)
        self.fixtures_path = Path(fixtures_path)
        self.paired_tasks_path = Path(paired_tasks_path)
        self.active_kb_path = Path(active_kb_path)
        self.secrets_path = secrets_path
        self.live_ai_url = live_ai_url
        self.poll_timeout_seconds = poll_timeout_seconds
        self.max_cases = max_cases
        self.keep_schema = keep_schema
        self.mock_mode = mock_mode

        # Load cases, active KB, and injected fixtures
        if not self.suite_path.exists():
            raise FileNotFoundError(f"Suite cases file not found: {self.suite_path}")
        self.cases = [
            json.loads(line)
            for line in self.suite_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if self.max_cases:
            self.cases = self.cases[: self.max_cases]

        self.active_docs = {}
        if self.active_kb_path.exists():
            for doc in json.loads(self.active_kb_path.read_text(encoding="utf-8")):
                d_id = doc.get("doc_id") or doc.get("document_id")
                if d_id:
                    self.active_docs[d_id] = doc

        self.injected_docs = {}
        if self.fixtures_path.exists():
            fix_data = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
            for doc in fix_data.get("documents", []):
                d_id = doc.get("doc_id") or doc.get("document_id")
                if d_id:
                    self.injected_docs[d_id] = doc

    def _build_source_snapshot(self, doc_id: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Look up immutable document in active KB or injected fixtures."""
        doc = self.active_docs.get(doc_id) or self.injected_docs.get(doc_id)
        if not doc:
            return None
        return {
            "doc_id": doc_id,
            "version": str(version or doc.get("version", "1.0")),
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "policy_key": doc.get("policy_key"),
            "content_hash": doc.get("content_hash", ""),
            "content": doc.get("content", ""),
            "valid_from": doc.get("valid_from"),
            "valid_to": doc.get("valid_to"),
            "status": doc.get("status", "approved"),
            "approved_by": doc.get("approved_by", "lead_compliance_officer"),
            "approved_at": doc.get("approved_at"),
            "allowed_roles": doc.get("allowed_roles", []),
        }

    def collect(self, output_base_dir: Optional[Path | str] = None) -> Dict[str, Any]:
        """Run collector against isolated PostgreSQL and return full run evidence."""
        configure_runtime_environment()
        owner_url, default_passwords = resolve_database_url(self.secrets_path)

        run_id = f"final-evidence-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        out_dir = Path(output_base_dir or (REPO_ROOT / "artifacts/evaluation")) / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        schema = f"accept_final_{uuid.uuid4().hex[:10]}"
        root_engine = create_engine(owner_url, hide_parameters=True)
        schema_created = False
        mock_gateway = None
        records: List[EvidenceCaseRecord] = []

        try:
            # 1. Create isolated disposable PostgreSQL schema
            with root_engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True

            # 2. Determine AI Gateway endpoint
            if self.mode == "mock":
                mock_gateway = EphemeralMockAIGateway(
                    cases=self.cases,
                    active_docs=self.active_docs,
                    injected_docs=self.injected_docs,
                    mode=self.mock_mode,
                )
                mock_gateway.start()
                ai_url = mock_gateway.base_url
            else:
                ai_url = self.live_ai_url

            # 3. Initialize isolated database and seed accounts
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
                ai_service_base_url=ai_url,
                ai_service_analysis_timeout_ms=3000,
                ai_service_draft_timeout_ms=11000,
                job_poll_interval_ms=50,
            )

            # 4. Launch TestClients for customer and staff
            with TestClient(create_app(settings=settings, database=database, start_worker=True)) as customer, \
                 TestClient(create_app(settings=settings, database=database, start_worker=False)) as staff:

                for client, role in ((customer, "customer"), (staff, "staff")):
                    client.headers["Origin"] = "http://testserver"
                    auth_resp = client.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
                    if auth_resp.status_code != 201:
                        raise RuntimeError(f"Authentication failed for role {role}: {auth_resp.text}")

                # 5. Process each case sequentially and capture evidence
                for idx, c in enumerate(self.cases):
                    case_id = c["id"]
                    msg = c["query"]
                    t0 = time.perf_counter()

                    ticket_payload = {"message": msg}
                    if c.get("order_context"):
                        # Note: customer submission may include message; order context is associated via order_id or mock order lookup
                        pass

                    ticket_resp = customer.post(
                        "/v1/shop/tickets",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json=ticket_payload,
                    )

                    if ticket_resp.status_code != 201:
                        records.append(
                            EvidenceCaseRecord(
                                case_id=case_id,
                                category=c.get("category", "unknown"),
                                slice=c.get("slice", "unknown"),
                                query=msg,
                                intent=c.get("intent", "unknown"),
                                order_context=c.get("order_context", {}),
                                expected_action=c.get("expected_action", "unknown"),
                                expected_docs=c.get("expected_docs", []),
                                expected_reasons=c.get("expected_reasons", []),
                                fixture_boundary=c.get("fixture_boundary", "active_kb"),
                                as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                ticket_id=None,
                                submit_to_terminal_latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                                terminal_status="submission_error",
                                analysis_status="error",
                                draft_status="error",
                                customer_no_auto_send_observed=False,
                                customer_reply_is_none=True,
                                customer_http_status=ticket_resp.status_code,
                                raw_model_routing={},
                                full_draft_text=None,
                                citations=[],
                                source_snapshots={},
                                usage_metadata={},
                                step_latencies_ms={},
                                error_code=f"HTTP_{ticket_resp.status_code}",
                                is_terminal=True,
                                is_success=False,
                            )
                        )
                        continue

                    t_id = ticket_resp.json()["ticket_id"]
                    deadline = time.monotonic() + self.poll_timeout_seconds
                    reached_terminal = False
                    suggestion_data: Dict[str, Any] = {}

                    while time.monotonic() < deadline:
                        ws_resp = staff.get(f"/v1/console/tickets/{t_id}")
                        if ws_resp.status_code == 200:
                            ticket_staff_view = ws_resp.json()
                            suggestion_data = ticket_staff_view.get("suggestion", {})
                            a_stat = suggestion_data.get("analysis_status", "pending")
                            d_stat = suggestion_data.get("draft_status", "pending")
                            if a_stat != "pending" and d_stat != "pending":
                                reached_terminal = True
                                break
                        time.sleep(0.05)

                    wall_latency_ms = round((time.perf_counter() - t0) * 1000, 2)

                    # 6. Verify Customer No-Auto-Send Invariant
                    cust_resp = customer.get(f"/v1/shop/tickets/{t_id}")
                    cust_reply_is_none = False
                    cust_no_auto_send = False
                    if cust_resp.status_code == 200:
                        cust_view = cust_resp.json()
                        cust_reply = cust_view.get("reply")
                        cust_reply_is_none = (cust_reply is None)
                        # Verify customer_status is 'received' (never 'replied') and reply is strictly None
                        cust_no_auto_send = cust_reply_is_none and (cust_view.get("customer_status") == "received")

                    # 7. Extract raw model, routing, draft, citations, and snapshots
                    raw_analysis = suggestion_data.get("analysis", {})
                    raw_routing = raw_analysis.get("routing", {})
                    raw_intent = raw_analysis.get("intent", {})
                    versions = suggestion_data.get("versions", {}) or raw_analysis.get("versions", {})
                    step_latencies = suggestion_data.get("step_latency_ms", {})
                    usage_meta = suggestion_data.get("llm_usage", {})
                    llm_meta = suggestion_data.get("llm_metadata", {})

                    draft_payload = suggestion_data.get("draft", {})
                    full_draft_text = draft_payload.get("text") if draft_payload else None
                    raw_citations = draft_payload.get("citations", []) if draft_payload else []

                    # Build source snapshots for all cited and retrieved documents
                    snapshots: Dict[str, Any] = {}
                    for cit in raw_citations:
                        d_id = cit.get("doc_id")
                        d_ver = cit.get("version")
                        if d_id:
                            snap = self._build_source_snapshot(d_id, d_ver)
                            if snap:
                                snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap

                    for doc_ret in raw_analysis.get("documents", []):
                        d_id = doc_ret.get("doc_id")
                        d_ver = doc_ret.get("version")
                        if d_id and f"{d_id}:{d_ver}" not in snapshots:
                            snap = self._build_source_snapshot(d_id, d_ver)
                            if snap:
                                snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap

                    terminal_status = suggestion_data.get("draft_status", "timeout") if reached_terminal else "timeout"
                    is_success = reached_terminal and cust_no_auto_send and terminal_status != "unavailable"

                    records.append(
                        EvidenceCaseRecord(
                            case_id=case_id,
                            category=c.get("category", "unknown"),
                            slice=c.get("slice", "unknown"),
                            query=msg,
                            intent=c.get("intent", "unknown"),
                            order_context=c.get("order_context", {}),
                            expected_action=c.get("expected_action", "unknown"),
                            expected_docs=c.get("expected_docs", []),
                            expected_reasons=c.get("expected_reasons", []),
                            fixture_boundary=c.get("fixture_boundary", "active_kb"),
                            as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                            ticket_id=t_id,
                            submit_to_terminal_latency_ms=wall_latency_ms,
                            terminal_status=terminal_status,
                            analysis_status=suggestion_data.get("analysis_status", "unknown"),
                            draft_status=suggestion_data.get("draft_status", "unknown"),
                            customer_no_auto_send_observed=cust_no_auto_send,
                            customer_reply_is_none=cust_reply_is_none,
                            customer_http_status=cust_resp.status_code,
                            raw_model_routing={
                                "intent": raw_intent,
                                "routing": raw_routing,
                                "alternatives": raw_analysis.get("alternatives", []),
                                "warnings": raw_analysis.get("warnings", []),
                                "versions": versions,
                                "llm_metadata": llm_meta,
                            },
                            full_draft_text=full_draft_text,
                            citations=raw_citations,
                            source_snapshots=snapshots,
                            usage_metadata=usage_meta,
                            step_latencies_ms=step_latencies,
                            error_code=None if reached_terminal else "TIMEOUT_POLLING_SUGGESTION",
                            is_terminal=reached_terminal,
                            is_success=is_success,
                        )
                    )

            app_engine.dispose()

        finally:
            if mock_gateway:
                mock_gateway.stop()

            if schema_created and not self.keep_schema:
                try:
                    with root_engine.begin() as conn:
                        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                except Exception:
                    pass
            root_engine.dispose()

        # 8. Compute aggregate summary metrics
        valid_latencies = [
            r.submit_to_terminal_latency_ms
            for r in records
            if r.submit_to_terminal_latency_ms is not None and math.isfinite(r.submit_to_terminal_latency_ms)
        ]
        valid_latencies.sort()
        p50_ms = None
        p95_ms = None
        if valid_latencies:
            p50_ms = valid_latencies[int(len(valid_latencies) * 0.50)]
            p95_ms = valid_latencies[min(int(math.ceil(len(valid_latencies) * 0.95)) - 1, len(valid_latencies) - 1)]

        all_no_auto_send = all(r.customer_no_auto_send_observed for r in records) if records else False
        total_errors = sum(1 for r in records if not r.is_success)

        # 9. Write evidence records to disk (raw_cases / evidence_records.jsonl)
        evidence_jsonl_path = out_dir / "evidence_records.jsonl"
        with open(evidence_jsonl_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(asdict(r)) + "\n")

        # 10. Write paired agent tasks file
        paired_manifest_path = out_dir / "paired_agent_study_manifest.json"
        if self.paired_tasks_path.exists():
            paired_tasks_content = json.loads(self.paired_tasks_path.read_text(encoding="utf-8"))
        else:
            paired_tasks_content = {"tasks": [], "status": "missing_template"}
        paired_manifest_path.write_text(json.dumps(paired_tasks_content, indent=2), encoding="utf-8")

        # 11. Write summary JSON
        summary = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit_hash(),
            "mode": self.mode,
            "total_cases_submitted": len(records),
            "errors": total_errors,
            "p50_latency_ms": p50_ms,
            "p95_latency_ms": p95_ms,
            "customer_no_auto_send_verified_all": all_no_auto_send,
            "target_p95_under_12s": (p95_ms <= 12000.0) if p95_ms is not None else False,
            "slice_distribution": {
                s: sum(1 for r in records if r.slice == s)
                for s in set(r.slice for r in records)
            },
            "fixture_boundaries": {
                b: sum(1 for r in records if r.fixture_boundary == b)
                for b in set(r.fixture_boundary for r in records)
            },
            "immutable_source_snapshots_captured": sum(len(r.source_snapshots) for r in records),
            "disclaimer": "AI claim grading and manual/assisted agent trials are delegated to coordinator; no manual answers or ratings invented.",
        }
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # 12. Write run manifest with all SHA-256 hashes
        manifest = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit_hash(),
            "mode": self.mode,
            "files": {
                "evidence_records.jsonl": {
                    "path": "evidence_records.jsonl",
                    "sha256": compute_sha256(evidence_jsonl_path),
                },
                "paired_agent_study_manifest.json": {
                    "path": "paired_agent_study_manifest.json",
                    "sha256": compute_sha256(paired_manifest_path),
                },
                "summary.json": {
                    "path": "summary.json",
                    "sha256": compute_sha256(summary_path),
                },
            },
            "suite_provenance": {
                "suite_file": str(self.suite_path),
                "suite_sha256": compute_sha256(self.suite_path),
                "manifest_file": str(self.manifest_path),
                "manifest_sha256": compute_sha256(self.manifest_path) if self.manifest_path.exists() else None,
                "active_kb_file": str(self.active_kb_path),
                "active_kb_sha256": compute_sha256(self.active_kb_path) if self.active_kb_path.exists() else None,
                "injected_fixtures_file": str(self.fixtures_path),
                "injected_fixtures_sha256": compute_sha256(self.fixtures_path) if self.fixtures_path.exists() else None,
            },
            "environment": {
                "python_version": platform.python_version(),
                "os": platform.platform(),
                "isolated_schema": schema,
                "schema_kept": self.keep_schema,
            },
        }
        manifest_path = out_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        return {
            "run_id": run_id,
            "output_dir": str(out_dir),
            "summary": summary,
            "manifest": manifest,
        }


def parse_args():
    parser = argparse.ArgumentParser(
        description="SupportIQ Final Acceptance Evidence Collector (Worker C)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "live"],
        default="mock",
        help="Evaluation mode: 'mock' (offline deterministic) or 'live' (actual AI gateway)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "artifacts/evaluation"),
        help="Base directory for output runs",
    )
    parser.add_argument(
        "--suite-file",
        default=str(REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl"),
        help="Path to 24-case synthetic scenario suite JSONL",
    )
    parser.add_argument(
        "--manifest-file",
        default=str(REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json"),
        help="Path to suite manifest JSON",
    )
    parser.add_argument(
        "--injected-fixtures",
        default=str(REPO_ROOT / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json"),
        help="Path to separate injected robustness fixtures JSON",
    )
    parser.add_argument(
        "--paired-tasks",
        default=str(REPO_ROOT / "data/benchmarks/final_acceptance/paired_agent_tasks.json"),
        help="Path to 12 paired agent tasks template JSON",
    )
    parser.add_argument(
        "--secrets",
        default=None,
        help="Path to application secrets JSON file containing database credentials",
    )
    parser.add_argument(
        "--ai-url",
        default="http://127.0.0.1:8002",
        help="AI Gateway base URL (used in live mode)",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum cases to run (bounded execution; max 24)",
    )
    parser.add_argument(
        "--poll-timeout",
        type=float,
        default=30.0,
        help="Timeout in seconds for waiting on ticket suggestion completion",
    )
    parser.add_argument(
        "--keep-schema",
        action="store_true",
        help="Do not drop isolated schema on completion (useful for post-run inspection)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("=== SupportIQ Final Acceptance Evidence Collector (Worker C) ===")
    print(f"- Execution Mode: {args.mode}")
    print(f"- Suite File: {args.suite_file}")
    print(f"- AI Gateway: {args.ai_url if args.mode == 'live' else 'Ephemeral Loopback Mock Gateway'}")
    print(f"- Bounded Max Cases: {args.max_cases or 'All 24'}")

    collector = AcceptanceEvidenceCollector(
        mode=args.mode,
        suite_path=args.suite_file,
        manifest_path=args.manifest_file,
        fixtures_path=args.injected_fixtures,
        paired_tasks_path=args.paired_tasks,
        secrets_path=args.secrets,
        live_ai_url=args.ai_url,
        poll_timeout_seconds=args.poll_timeout,
        max_cases=args.max_cases,
        keep_schema=args.keep_schema,
    )

    result = collector.collect(output_base_dir=args.output_dir)
    sum_data = result["summary"]
    run_id = result["run_id"]
    out_dir = result["output_dir"]

    print("\nEvidence Collection Complete!")
    print(f"- Run ID: {run_id}")
    print(f"- Output Directory: {out_dir}")
    print(f"- Total Cases: {sum_data['total_cases_submitted']}")
    print(f"- Errors: {sum_data['errors']}")
    p50_str = f"{sum_data['p50_latency_ms']:.2f}ms" if sum_data["p50_latency_ms"] is not None else "N/A"
    p95_str = f"{sum_data['p95_latency_ms']:.2f}ms" if sum_data["p95_latency_ms"] is not None else "N/A"
    print(f"- Submit-to-Terminal Latency: p50={p50_str}, p95={p95_str}")
    print(f"- Customer 100% No-Auto-Send Invariant: {'VERIFIED' if sum_data['customer_no_auto_send_verified_all'] else 'FAILED'}")
    print(f"- Source Snapshots Captured: {sum_data['immutable_source_snapshots_captured']}")


if __name__ == "__main__":
    main()

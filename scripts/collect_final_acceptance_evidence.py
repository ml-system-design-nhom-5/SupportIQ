#!/usr/bin/env python3
"""Isolated PostgreSQL Application Evidence Collector for SupportIQ Final Acceptance.

Worker C Scope:
- Executes 24 synthetic scenarios covering:
  * 11 core answerable product intents (12 drafting cases including restricted cosmetics regression)
  * Sensitive / authority / escalation scenarios
  * Human agent direct escalation (12th product scenario)
  * No-source / unsupported scenarios
  * Out-of-domain (OOD) scenarios
  * Honest separate injected fixture boundary (temporal expiry & conflicting policies)
- Evaluates injected fixtures directly via real RetrievalAdapter component execution
  (never sent to unchanged live application gateway; no fabricated customer HTTP or auto-send observations)
- Enforces cryptographic manifest approval and configuration checks before DB or inference:
  * Manifest status & scope approval verification (fails closed if unapproved)
  * Non-optional checksum validation for cases, fixtures, paired tasks, active KB, and release
  * Seeded demo-customer order ownership validation without live LLM calls
  * Strict bounded max_cases (1..24) and 24-case suite size validation
- Rigorous source snapshot indexing and citation verification:
  * Indexed by exact (doc_id, version)
  * Enforces active release allowed versions
  * Recomputes content hash from UTF-8 bytes and compares with stored & returned citation/retrieval hashes
  * Explicit failure records on missing or mismatched sources (never defaulting status to approved or approved_by)
  * Reads both doc_id and document_id aliases
  * Validates order_context citations requiring actual field presence and typed value equality in executed context
- Explicit customer HTTP JSON validation requiring 'reply' field and 'customer_status' == 'received'
- Strictly separates 20 application cases from 4 component cases in all p50/p95 and oversight denominators
- Preserves every failed case; mock mode explicitly reports pending live authorization (never asserting 100% safety)
- Exclusive directory creation (exist_ok=False) and robust engine disposal in all exit paths.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
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
import tempfile
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
from apps.backend.platform.models import Suggestion, Ticket
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
    active_docs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    injected_docs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    allowed_release_versions: Dict[str, str] = {}
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
        expected_action = matched_case.get("expected_action", "draft") if matched_case else "draft"
        expected_reasons = matched_case.get("expected_reasons", []) if matched_case else []
        expected_docs = matched_case.get("expected_docs", []) if matched_case else []

        # Build analysis response
        retrieved_documents = []
        if expected_action == "draft" and expected_docs:
            for doc_key in expected_docs:
                parts = doc_key.split(":")
                d_id = parts[0]
                d_ver = parts[1] if len(parts) > 1 else self.allowed_release_versions.get(d_id, "1.0")
                doc_meta = self.active_docs.get((d_id, d_ver), {})
                retrieved_documents.append({
                    "doc_id": d_id,
                    "document_id": d_id,
                    "version": d_ver,
                    "title": doc_meta.get("title", f"Policy {d_id}"),
                    "content_hash": doc_meta.get("content_hash"),
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
                "release_id": "current-policies-v1",
                "model_version": "v1.0.0",
                "kb_version": "v2.0",
                "prompt_version": "grounded-v2",
                "routing_version": "router-v1",
                "index_version": "index-v1.5",
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
                doc_full = self.active_docs.get((d_id, d_ver), {})
                content = doc_full.get("content", "Our standard customer service policy.")
                span = content[:50] if len(content) >= 50 else content

                citations = [
                    {
                        "source_type": "document",
                        "doc_id": d_id,
                        "document_id": d_id,
                        "version": d_ver,
                        "field": "policy_body",
                        "span": span,
                        "content_hash": doc_item.get("content_hash"),
                    }
                ]
                # Include allowlisted order_context citation when case specifies order
                if matched_case and matched_case.get("order_id"):
                    citations.append({
                        "source_type": "order_context",
                        "field": "order_status",
                    })

                draft_body = {
                    "segments": [
                        {"paragraph_index": 0, "text": f"Thank you for contacting customer support regarding your inquiry. Based on our policy, {content[:180]}."},
                        {"paragraph_index": 1, "text": "Please let us know if you need any additional assistance with this matter."}
                    ],
                    "citations": citations,
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
        active_docs: Dict[Tuple[str, str], Dict[str, Any]],
        injected_docs: Dict[Tuple[str, str], Dict[str, Any]],
        allowed_release_versions: Dict[str, str],
        mode: str = "normal",
    ):
        handler_cls = MockAcceptanceGatewayHandler
        handler_cls.cases_by_query = {c["query"]: c for c in cases}
        handler_cls.active_docs = active_docs
        handler_cls.injected_docs = injected_docs
        handler_cls.allowed_release_versions = allowed_release_versions
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
    order_id: Optional[str]
    planned_scenario_context: Dict[str, Any]
    planned_as_of: str
    actual_executed_order_context: Dict[str, Any]
    actual_executed_as_of: Optional[str]
    component_evidence: str  # "application_postgresql_gateway" or "retrieval_adapter_injected_fixture_execution"
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
    customer_no_auto_send_observed: Optional[bool]
    customer_reply_is_none: Optional[bool]
    customer_http_status: Optional[int]
    raw_model_routing: Dict[str, Any]
    response_versions: Dict[str, Any]
    llm_metadata: Dict[str, Any]
    manifest_cases_sha256: str
    full_draft_text: Optional[str]
    citations: List[Dict[str, Any]]
    source_snapshots: Dict[str, Any]  # Keyed by (doc_id:version) -> full metadata + verification
    usage_metadata: Dict[str, Any]
    step_latencies_ms: Dict[str, Any]
    error_code: Optional[str]
    is_terminal: bool
    # Granular verification flags
    collection_success: bool
    action_matches_expected: Optional[bool]
    reasons_match_expected: bool
    authority_check_passed: Optional[bool]
    source_verification_passed: bool
    is_success: bool
    acceptance_status: str


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
        release_path: Path | str = REPO_ROOT / "apps/ai_service/kb-release.json",
        mock_orders_path: Path | str = REPO_ROOT / "data/knowledge/mock_orders.json",
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
        self.release_path = Path(release_path)
        self.mock_orders_path = Path(mock_orders_path)
        self.secrets_path = secrets_path
        self.live_ai_url = live_ai_url
        self.poll_timeout_seconds = poll_timeout_seconds
        self.max_cases = max_cases
        self.keep_schema = keep_schema
        self.mock_mode = mock_mode
        self._shared_encoder = None

        # 1. Enforce manifest approval & checksum validation BEFORE any DB connection or inference
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Suite manifest file not found: {self.manifest_path}")

        self.manifest_data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        prov = self.manifest_data.get("provenance", {})

        # Enforce manifest approval provenance
        manifest_status = self.manifest_data.get("status", "")
        if self.mode == "live":
            if not manifest_status.startswith("approved"):
                raise ValueError(
                    f"Live execution rejected: suite manifest status is '{manifest_status}'. "
                    "Live execution requires coordinator approval provenance in manifest!"
                )
            approval_scope = self.manifest_data.get("approval_scope", "")
            if "delegated AI stakeholder" not in approval_scope and "local evaluation" not in approval_scope.lower():
                raise ValueError(
                    f"Live execution rejected: suite manifest approval scope '{approval_scope}' "
                    "lacks delegated AI stakeholder authority!"
                )

        # Check suite cases hash (mandatory)
        if not self.suite_path.exists():
            raise FileNotFoundError(f"Suite cases file not found: {self.suite_path}")
        actual_cases_hash = compute_sha256(self.suite_path)
        expected_cases_hash = prov.get("cases_sha256")
        if not expected_cases_hash or actual_cases_hash != expected_cases_hash:
            raise ValueError(
                f"Cases checksum mismatch against manifest! Expected: {expected_cases_hash}, Got: {actual_cases_hash}"
            )
        self.manifest_cases_sha256 = actual_cases_hash

        # Check injected fixtures hash (mandatory)
        if not self.fixtures_path.exists():
            raise FileNotFoundError(f"Injected fixtures file not found: {self.fixtures_path}")
        actual_fix_hash = compute_sha256(self.fixtures_path)
        expected_fix_hash = prov.get("injected_fixtures_sha256")
        if not expected_fix_hash or actual_fix_hash != expected_fix_hash:
            raise ValueError(
                f"Injected fixtures checksum mismatch against manifest! Expected: {expected_fix_hash}, Got: {actual_fix_hash}"
            )

        # Check paired tasks hash (mandatory)
        if not self.paired_tasks_path.exists():
            raise FileNotFoundError(f"Paired tasks file not found: {self.paired_tasks_path}")
        actual_paired_hash = compute_sha256(self.paired_tasks_path)
        expected_paired_hash = prov.get("paired_tasks_sha256")
        if not expected_paired_hash or actual_paired_hash != expected_paired_hash:
            raise ValueError(
                f"Paired tasks checksum mismatch against manifest! Expected: {expected_paired_hash}, Got: {actual_paired_hash}"
            )

        # Check active KB and release hashes as matched atomic pairs (LF vs CRLF)
        if not self.active_kb_path.exists():
            raise FileNotFoundError(f"Active KB source file not found: {self.active_kb_path}")
        if not self.release_path.exists():
            raise FileNotFoundError(f"Active KB release file not found: {self.release_path}")

        actual_kb_hash = compute_sha256(self.active_kb_path)
        actual_rel_hash = compute_sha256(self.release_path)

        reconcile = prov.get("kb_reconciliation", {})
        worker_tree = reconcile.get("worker_local_worktree", {})
        root_gateway = reconcile.get("deployed_root_serving_gateway", {})

        worker_pair = (
            worker_tree.get("local_kb_source_sha256"),
            worker_tree.get("local_kb_release_sha256"),
        )
        root_pair = (
            root_gateway.get("kb_source_sha256"),
            root_gateway.get("kb_release_sha256"),
        )

        if not worker_pair[0] or not worker_pair[1]:
            raise ValueError("Manifest missing worker_local_worktree KB/release provenance hashes!")
        if not root_pair[0] or not root_pair[1]:
            raise ValueError("Manifest missing deployed_root_serving_gateway KB/release provenance hashes!")

        actual_pair = (actual_kb_hash, actual_rel_hash)

        if actual_pair == worker_pair:
            self.matched_kb_provenance = "worker_local_worktree"
            self.matched_line_ending = worker_tree.get("line_ending", "LF")
        elif actual_pair == root_pair:
            self.matched_kb_provenance = "deployed_root_serving_gateway"
            self.matched_line_ending = root_gateway.get("line_ending", "CRLF")
        else:
            raise ValueError(
                f"Unrecognized or mixed KB and release hash pair! Actual pair: (KB={actual_kb_hash}, Release={actual_rel_hash}). "
                f"Must match declared worker_local_worktree pair {worker_pair} or deployed_root_serving_gateway pair {root_pair}. "
                "Mixed or unrecognized provenance pairs are rejected."
            )

        # 2. Enforce bounded valid configuration BEFORE DB or inference
        suite_lines = [line.strip() for line in self.suite_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        total_suite_count = len(suite_lines)
        if total_suite_count != 24:
            raise ValueError(f"Final acceptance suite must contain exactly 24 cases, found: {total_suite_count}")

        if self.max_cases is not None:
            if not isinstance(self.max_cases, int) or self.max_cases < 1 or self.max_cases > 24:
                raise ValueError(f"Bounded max_cases must be an integer between 1 and 24, got: {self.max_cases}")
            self.cases = [json.loads(line) for line in suite_lines[: self.max_cases]]
        else:
            self.cases = [json.loads(line) for line in suite_lines]

        # 3. Validate seeded order ownership/status without live LLM calls
        if not self.mock_orders_path.exists():
            raise FileNotFoundError(f"Mock orders file not found: {self.mock_orders_path}")
        all_mock_orders = json.loads(self.mock_orders_path.read_text(encoding="utf-8"))
        demo_customer_orders = {o["order_id"]: o for o in all_mock_orders if o.get("customer_id") == "demo-customer"}
        other_customer_orders = {o["order_id"]: o for o in all_mock_orders if o.get("customer_id") != "demo-customer"}

        for c in self.cases:
            o_id = c.get("order_id")
            if o_id:
                if o_id in other_customer_orders:
                    other_owner = other_customer_orders[o_id].get("customer_id")
                    raise ValueError(
                        f"Order validation failure in case {c['id']}: references order {o_id} "
                        f"owned by '{other_owner}', not 'demo-customer'!"
                    )
                if o_id not in demo_customer_orders:
                    raise ValueError(
                        f"Order validation failure in case {c['id']}: references unknown order {o_id} "
                        "not seeded in mock_orders.json!"
                    )
                o_obj = demo_customer_orders[o_id]
                if not o_obj.get("order_status"):
                    raise ValueError(f"Seeded order {o_id} has empty order_status!")

        # 4. Load active release and index allowed versions
        release_data = json.loads(self.release_path.read_text(encoding="utf-8"))
        self.allowed_release_versions: Dict[str, str] = {
            d["document_id"]: str(d["version"]) for d in release_data.get("documents", [])
        }

        # 5. Index active KB documents by exact (doc_id, version) and (document_id, version)
        self.active_docs: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for doc in json.loads(self.active_kb_path.read_text(encoding="utf-8")):
            d_id = doc.get("doc_id")
            doc_id = doc.get("document_id")
            ver = str(doc.get("version"))
            if d_id:
                self.active_docs[(d_id, ver)] = doc
            if doc_id:
                self.active_docs[(doc_id, ver)] = doc

        # 6. Index injected synthetic fixtures by exact (doc_id, version)
        self.injected_docs: Dict[Tuple[str, str], Dict[str, Any]] = {}
        fix_data = json.loads(self.fixtures_path.read_text(encoding="utf-8"))
        self.injected_docs_raw = fix_data.get("documents", [])
        for doc in self.injected_docs_raw:
            d_id = doc.get("doc_id")
            doc_id = doc.get("document_id")
            ver = str(doc.get("version", "1.0"))
            if d_id:
                self.injected_docs[(d_id, ver)] = doc
            if doc_id:
                self.injected_docs[(doc_id, ver)] = doc

    def _get_encoder(self):
        """Initialize PolicyEncoder with strict fail-closed enforcement in live mode.

        In live mode: strictly requires real PolicyEncoder; never falls back to MockPolicyEncoder.
        In mock mode: attempts real PolicyEncoder first; falls back to MockPolicyEncoder only if
        real model weights loading is unavailable (e.g. in offline pytest environments).
        """
        if self._shared_encoder is None:
            self.encoder_provenance = None
            self.encoder_error = None
            try:
                from apps.core_backend.retrieval.adapter import PolicyEncoder
                enc = PolicyEncoder()
                if getattr(enc, "encoder_error", None):
                    raise RuntimeError(f"PolicyEncoder error: {enc.encoder_error}")
                if getattr(enc, "mock_mode", False) is True:
                    raise RuntimeError("PolicyEncoder initialized in mock_mode=True, real encoder required")
                if getattr(enc, "model", None) is None or getattr(enc, "tokenizer", None) is None:
                    raise RuntimeError("PolicyEncoder initialized with None model or tokenizer")
                self._shared_encoder = enc
                self.encoder_provenance = "real_bge_policy_encoder"
            except Exception as e:
                self.encoder_error = str(e)
                if self.mode == "live":
                    # Fail closed in live mode! Never fall back to mock encoder in live!
                    self._shared_encoder = None
                    self.encoder_provenance = "failed_real_encoder_fail_closed"
                    raise RuntimeError(
                        f"Live execution requires real PolicyEncoder, but initialization failed: {e}"
                    )
                else:
                    # In mock mode: fallback to MockPolicyEncoder with explicit provenance label
                    try:
                        from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
                        self._shared_encoder = MockPolicyEncoder()
                        self.encoder_provenance = "mock_policy_encoder_offline_fallback"
                    except Exception as mock_e:
                        self._shared_encoder = None
                        self.encoder_provenance = "encoder_unavailable"
                        raise RuntimeError(f"Failed to load both real and mock encoders: {mock_e}")
        return self._shared_encoder

    def _build_source_snapshot(
        self,
        doc_id: Optional[str],
        version: Optional[str] = None,
        returned_content_hash: Optional[str] = None,
        is_injected: bool = False,
    ) -> Dict[str, Any]:
        """Look up immutable document by exact (doc_id, version), verify against active release and content hash.

        Missing or mismatched sources result in explicit evidence failures (is_verified=False).
        Never defaults status to 'approved' or approved_by to 'lead_compliance_officer' if missing or mismatched.
        """
        if not doc_id:
            return {
                "doc_id": "UNKNOWN",
                "document_id": "UNKNOWN",
                "version": str(version) if version is not None else "UNKNOWN",
                "is_verified": False,
                "verification_error": "MISSING_DOC_ID",
                "status": None,
                "approved_by": None,
                "approved_at": None,
                "title": None,
                "category": None,
                "policy_key": None,
                "content_hash": None,
                "recomputed_content_hash": None,
                "content": None,
                "valid_from": None,
                "valid_to": None,
                "allowed_roles": [],
            }

        v_str = str(version) if version is not None else None

        # Determine target store: active KB or injected fixtures
        if is_injected:
            doc = None
            if v_str is not None:
                doc = self.injected_docs.get((doc_id, v_str))
            if not doc:
                return {
                    "doc_id": doc_id,
                    "document_id": doc_id,
                    "version": v_str or "UNKNOWN",
                    "is_verified": False,
                    "verification_error": f"INJECTED_FIXTURE_NOT_FOUND_FOR_VERSION: {doc_id}:{v_str}",
                    "status": None,
                    "approved_by": None,
                    "approved_at": None,
                    "title": None,
                    "category": None,
                    "policy_key": None,
                    "content_hash": None,
                    "recomputed_content_hash": None,
                    "content": None,
                    "valid_from": None,
                    "valid_to": None,
                    "allowed_roles": [],
                }
        else:
            # Active KB: enforce active release allowed versions
            allowed_ver = self.allowed_release_versions.get(doc_id)
            if not allowed_ver:
                return {
                    "doc_id": doc_id,
                    "document_id": doc_id,
                    "version": v_str or "UNKNOWN",
                    "is_verified": False,
                    "verification_error": f"DOC_NOT_IN_ACTIVE_KB_RELEASE: {doc_id}",
                    "status": None,
                    "approved_by": None,
                    "approved_at": None,
                    "title": None,
                    "category": None,
                    "policy_key": None,
                    "content_hash": None,
                    "recomputed_content_hash": None,
                    "content": None,
                    "valid_from": None,
                    "valid_to": None,
                    "allowed_roles": [],
                }

            if v_str is not None and v_str != allowed_ver:
                return {
                    "doc_id": doc_id,
                    "document_id": doc_id,
                    "version": v_str,
                    "is_verified": False,
                    "verification_error": f"VERSION_COLLISION_OR_MISMATCH: requested {v_str}, active release allows {allowed_ver}",
                    "status": None,
                    "approved_by": None,
                    "approved_at": None,
                    "title": None,
                    "category": None,
                    "policy_key": None,
                    "content_hash": None,
                    "recomputed_content_hash": None,
                    "content": None,
                    "valid_from": None,
                    "valid_to": None,
                    "allowed_roles": [],
                }

            lookup_ver = v_str or allowed_ver
            doc = self.active_docs.get((doc_id, lookup_ver))
            if not doc:
                return {
                    "doc_id": doc_id,
                    "document_id": doc_id,
                    "version": lookup_ver,
                    "is_verified": False,
                    "verification_error": f"ACTIVE_DOC_NOT_FOUND_IN_KB_STORE: {doc_id}:{lookup_ver}",
                    "status": None,
                    "approved_by": None,
                    "approved_at": None,
                    "title": None,
                    "category": None,
                    "policy_key": None,
                    "content_hash": None,
                    "recomputed_content_hash": None,
                    "content": None,
                    "valid_from": None,
                    "valid_to": None,
                    "allowed_roles": [],
                }

        # Document located; extract content and recompute hash from UTF-8 bytes
        content = doc.get("content", "")
        stored_hash = doc.get("content_hash")
        recomputed_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Check hash match
        is_verified = True
        verification_error = None
        if stored_hash and recomputed_hash != stored_hash:
            is_verified = False
            verification_error = f"STORED_HASH_MISMATCH: stored {stored_hash}, recomputed {recomputed_hash}"
        elif returned_content_hash and recomputed_hash != returned_content_hash:
            is_verified = False
            verification_error = f"RETURNED_HASH_MISMATCH: citation returned {returned_content_hash}, recomputed {recomputed_hash}"

        return {
            "doc_id": doc.get("doc_id") or doc_id,
            "document_id": doc.get("document_id") or doc.get("doc_id") or doc_id,
            "version": str(doc.get("version", v_str)),
            "is_verified": is_verified,
            "verification_error": verification_error,
            "title": doc.get("title"),
            "category": doc.get("category"),
            "policy_key": doc.get("policy_key"),
            "content_hash": stored_hash,
            "recomputed_content_hash": recomputed_hash,
            "content": content,
            "valid_from": doc.get("valid_from"),
            "valid_to": doc.get("valid_to"),
            "status": doc.get("status"),
            "approved_by": doc.get("approved_by"),
            "approved_at": doc.get("approved_at"),
            "allowed_roles": doc.get("allowed_roles", []),
        }

    def _run_injected_fixture_retrieval(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """Execute dedicated RetrievalAdapter on honest injected fixture boundary."""
        from apps.core_backend.retrieval.adapter import RetrievalAdapter
        cid = c["id"]
        fixture_map = {
            d.get("doc_id") or d.get("document_id"): d for d in self.injected_docs_raw
        }
        if cid == "final-case-21":
            docs = [fixture_map["POL-INJ-EXP-01"]]
        elif cid == "final-case-22":
            docs = [fixture_map["POL-INJ-EXP-02"]]
        elif cid == "final-case-23":
            docs = [fixture_map["POL-INJ-CONF-01A"], fixture_map["POL-INJ-CONF-01B"]]
        elif cid == "final-case-24":
            docs = [fixture_map["POL-INJ-CONF-02A"], fixture_map["POL-INJ-CONF-02B"]]
        else:
            docs = self.injected_docs_raw

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(docs, tf)
            tmp_path = tf.name

        try:
            try:
                enc = self._get_encoder()
            except Exception as e:
                return {
                    "status": "encoder_unavailable",
                    "evidence": [],
                    "has_conflict": False,
                    "error": str(e),
                }

            rel_thresh = 0.15 if getattr(self, "encoder_provenance", "") == "mock_policy_encoder_offline_fallback" else 0.40
            adapter = RetrievalAdapter(kb_path=tmp_path, encoder=enc, relevance_threshold=rel_thresh)
            as_of_dt = datetime.fromisoformat(c.get("as_of", "2026-06-15T10:00:00Z").replace("Z", "+00:00"))
            retrieved = adapter.retrieve(
                query=c["query"],
                intent=c["intent"],
                role="agent",
                current_time=as_of_dt,
            )
            return retrieved
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def collect(self, output_base_dir: Optional[Path | str] = None) -> Dict[str, Any]:
        """Run collector against isolated PostgreSQL and return full run evidence."""
        configure_runtime_environment()
        owner_url, default_passwords = resolve_database_url(self.secrets_path)

        run_id = f"final-evidence-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        out_dir = Path(output_base_dir or (REPO_ROOT / "artifacts/evaluation")) / run_id
        # Exclusive creation prevents collision / accidental overwrites
        out_dir.mkdir(parents=True, exist_ok=False)

        schema = f"accept_final_{uuid.uuid4().hex[:10]}"
        root_engine = None
        app_engine = None
        schema_created = False
        mock_gateway = None
        records: List[EvidenceCaseRecord] = []

        try:
            root_engine = create_engine(owner_url, hide_parameters=True)

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
                    allowed_release_versions=self.allowed_release_versions,
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

                    # Honest separation: injected fixtures are evaluated in dedicated RetrievalAdapter boundary
                    # No fabricated application HTTP or auto-send observations
                    if c.get("fixture_boundary") == "injected_synthetic":
                        t0 = time.perf_counter()
                        retrieved = self._run_injected_fixture_retrieval(c)
                        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

                        retriever_status = retrieved.get("status", "unknown")
                        retriever_healthy = (retriever_status in ("success", "no_match", "empty_kb") and retriever_status != "encoder_unavailable")
                        has_conflict = retrieved.get("has_conflict", False)
                        evidence = retrieved.get("evidence", [])

                        # Assert actual retriever status and non-unavailable
                        component_reasons = []
                        expiry_filtering_verified = False
                        conflict_detection_verified = False

                        if c["slice"] == "expired_injected_boundary":
                            # Expiry filter verification: retriever healthy, evidence filtered out, and fixture document valid_to < as_of
                            as_of_str = c.get("as_of", "2026-06-15T10:00:00Z")
                            target_doc_id = "POL-INJ-EXP-01" if case_id == "final-case-21" else "POL-INJ-EXP-02"
                            doc_meta = next((d for d in self.injected_docs_raw if (d.get("doc_id") or d.get("document_id")) == target_doc_id), {})
                            is_truly_expired = (doc_meta.get("valid_to", "") < as_of_str)

                            expiry_filtering_verified = (
                                retriever_healthy
                                and len(evidence) == 0
                                and is_truly_expired
                            )
                            if expiry_filtering_verified:
                                component_reasons = ["only_expired_documents", "no_valid_document"]
                        elif c["slice"] == "conflict_injected_boundary":
                            conflict_detection_verified = (
                                retriever_healthy
                                and has_conflict is True
                                and len(evidence) >= 2
                            )
                            if conflict_detection_verified:
                                component_reasons = ["conflicting_sources"]

                        # Capture source snapshots from injected fixtures
                        snapshots = {}
                        for doc in self.injected_docs_raw:
                            d_id = doc.get("doc_id") or doc.get("document_id")
                            if d_id and d_id in c.get("notes", ""):
                                snap = self._build_source_snapshot(
                                    doc_id=d_id,
                                    version=doc.get("version", "1.0"),
                                    returned_content_hash=doc.get("content_hash"),
                                    is_injected=True,
                                )
                                snapshots[f"{d_id}:{snap['version']}"] = snap

                        finite_latency = math.isfinite(latency_ms) and latency_ms > 0
                        all_snaps_verified = (len(snapshots) >= 1) and all(s.get("is_verified", False) for s in snapshots.values())

                        collection_success = retriever_healthy and finite_latency
                        reasons_match = all(r in component_reasons for r in c.get("expected_reasons", [])) if c.get("expected_reasons") else True

                        component_test_passed = (
                            collection_success
                            and all_snaps_verified
                            and (expiry_filtering_verified if c["slice"] == "expired_injected_boundary" else conflict_detection_verified)
                        )

                        records.append(
                            EvidenceCaseRecord(
                                case_id=case_id,
                                category=c.get("category", "unknown"),
                                slice=c.get("slice", "unknown"),
                                query=msg,
                                intent=c.get("intent", "unknown"),
                                order_id=None,
                                planned_scenario_context=c.get("order_context", {}),
                                planned_as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                actual_executed_order_context={},
                                actual_executed_as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                component_evidence="retrieval_adapter_injected_fixture_execution",
                                expected_action="abstain",
                                expected_docs=[],
                                expected_reasons=c.get("expected_reasons", []),
                                fixture_boundary="injected_synthetic",
                                as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                ticket_id=None,
                                submit_to_terminal_latency_ms=latency_ms,
                                terminal_status=f"component_retriever_{retriever_status}",
                                analysis_status="not_applicable_component_boundary",
                                draft_status="not_applicable_component_boundary",
                                customer_no_auto_send_observed=None,  # Not applicable to component execution
                                customer_reply_is_none=None,          # Not applicable to component execution
                                customer_http_status=None,            # Not applicable to component execution
                                raw_model_routing={
                                    "intent": {"label": c.get("intent"), "source": "synthetic_fixture_boundary"},
                                    "routing": {"retriever_status": retriever_status, "reason_codes": component_reasons, "has_conflict": has_conflict},
                                    "retrieved_evidence": evidence,
                                    "versions": {"release_id": "injected-robustness-fixtures-v1"},
                                    "llm_metadata": {},
                                },
                                response_versions={"release_id": "injected-robustness-fixtures-v1"},
                                llm_metadata={},
                                manifest_cases_sha256=self.manifest_cases_sha256,
                                full_draft_text=None,
                                citations=[],
                                source_snapshots=snapshots,
                                usage_metadata={},
                                step_latencies_ms={"retrieval_ms": latency_ms},
                                error_code=None if retriever_healthy else f"RETRIEVER_{retriever_status.upper()}",
                                is_terminal=True,
                                collection_success=collection_success,
                                action_matches_expected=None,        # No inferred application action
                                reasons_match_expected=reasons_match,
                                authority_check_passed=None,         # Not an authority test
                                source_verification_passed=all_snaps_verified,
                                is_success=component_test_passed,
                                acceptance_status="synthetic_fixture_boundary_verified" if component_test_passed else "synthetic_fixture_boundary_failed",
                            )
                        )
                        continue

                    # Active KB cases: execute against application and PostgreSQL
                    t0 = time.perf_counter()
                    ticket_payload = {"message": msg}
                    if c.get("order_id"):
                        ticket_payload["order_id"] = c["order_id"]

                    ticket_resp = customer.post(
                        "/v1/shop/tickets",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json=ticket_payload,
                    )

                    if ticket_resp.status_code != 201:
                        wall_lat = round((time.perf_counter() - t0) * 1000, 2)
                        records.append(
                            EvidenceCaseRecord(
                                case_id=case_id,
                                category=c.get("category", "unknown"),
                                slice=c.get("slice", "unknown"),
                                query=msg,
                                intent=c.get("intent", "unknown"),
                                order_id=c.get("order_id"),
                                planned_scenario_context=c.get("order_context", {}),
                                planned_as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                actual_executed_order_context={},
                                actual_executed_as_of=None,
                                component_evidence="application_postgresql_gateway",
                                expected_action=c.get("expected_action", "unknown"),
                                expected_docs=c.get("expected_docs", []),
                                expected_reasons=c.get("expected_reasons", []),
                                fixture_boundary=c.get("fixture_boundary", "active_kb"),
                                as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                                ticket_id=None,
                                submit_to_terminal_latency_ms=wall_lat,
                                terminal_status="submission_error",
                                analysis_status="error",
                                draft_status="error",
                                customer_no_auto_send_observed=False,
                                customer_reply_is_none=True,
                                customer_http_status=ticket_resp.status_code,
                                raw_model_routing={},
                                response_versions={},
                                llm_metadata={},
                                manifest_cases_sha256=self.manifest_cases_sha256,
                                full_draft_text=None,
                                citations=[],
                                source_snapshots={},
                                usage_metadata={},
                                step_latencies_ms={},
                                error_code=f"HTTP_{ticket_resp.status_code}",
                                is_terminal=True,
                                collection_success=False,
                                action_matches_expected=False,
                                reasons_match_expected=False,
                                authority_check_passed=False,
                                source_verification_passed=False,
                                is_success=False,
                                acceptance_status="submission_failed",
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

                    # Query database directly to extract exact executed request payload
                    executed_order_context = {}
                    executed_as_of = None
                    try:
                        with database.transaction() as db_session:
                            t_obj = db_session.get(Ticket, t_id)
                            if t_obj and t_obj.current_suggestion_id:
                                s_obj = db_session.get(Suggestion, t_obj.current_suggestion_id)
                                if s_obj and s_obj.request_payload:
                                    executed_order_context = s_obj.request_payload.get("order_context", {})
                                    executed_as_of = s_obj.request_payload.get("as_of")
                    except Exception:
                        pass

                    # Explicit customer HTTP JSON validation: must have 'reply' field and 'customer_status' == 'received'
                    cust_resp = customer.get(f"/v1/shop/tickets/{t_id}")
                    cust_reply_is_none = False
                    cust_no_auto_send = False
                    cust_json_valid = False
                    cust_observation_error = None

                    if cust_resp.status_code == 200:
                        try:
                            cust_view = cust_resp.json()
                            if isinstance(cust_view, dict):
                                ticket_matches = (cust_view.get("ticket_id") == t_id)
                                # HTTP customer JSON must explicitly have 'reply' field
                                reply_field_present = ("reply" in cust_view)
                                reply_is_none = (cust_view.get("reply") is None)
                                status_is_received = (cust_view.get("customer_status") == "received")

                                if ticket_matches and reply_field_present:
                                    cust_json_valid = True
                                    cust_reply_is_none = reply_is_none
                                    cust_no_auto_send = reply_is_none and status_is_received
                                else:
                                    cust_observation_error = "MISSING_REPLY_FIELD_OR_TICKET_ID_MISMATCH"
                            else:
                                cust_observation_error = "CUSTOMER_RESPONSE_NOT_A_DICT"
                        except Exception as e:
                            cust_observation_error = f"MALFORMED_CUSTOMER_JSON: {type(e).__name__}"
                    else:
                        cust_observation_error = f"CUSTOMER_HTTP_{cust_resp.status_code}"

                    # Extract raw model, routing, draft, citations, and versions
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

                    # Build source snapshots and process citations
                    snapshots: Dict[str, Any] = {}
                    parsed_citations: List[Dict[str, Any]] = []

                    for cit in raw_citations:
                        src_type = cit.get("source_type")
                        if src_type in ("order_context", "order"):
                            f_name = cit.get("field")
                            f_val = cit.get("value")
                            # Require actual field present in executed context AND typed equality
                            field_present = (executed_order_context is not None and f_name in executed_order_context)
                            val_matches = field_present and (executed_order_context[f_name] == f_val)
                            v_ok = field_present and val_matches
                            parsed_citations.append({
                                "source_type": "order_context",
                                "field": f_name,
                                "value": f_val,
                                "field_present_in_executed_context": field_present,
                                "value_matches_executed_context": val_matches,
                                "is_verified": v_ok,
                                "verification_error": None if v_ok else (
                                    f"ORDER_CONTEXT_FIELD_MISSING: field '{f_name}' not in executed context"
                                    if not field_present else
                                    f"ORDER_CONTEXT_VALUE_MISMATCH: expected '{executed_order_context[f_name]}', got '{f_val}'"
                                ),
                            })
                        else:
                            d_id = cit.get("doc_id") or cit.get("document_id")
                            d_ver = cit.get("version")
                            ret_hash = cit.get("content_hash")
                            snap = None
                            if d_id:
                                snap = self._build_source_snapshot(
                                    doc_id=d_id,
                                    version=d_ver,
                                    returned_content_hash=ret_hash,
                                    is_injected=False,
                                )
                                snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap

                            parsed_citations.append({
                                "source_type": "document",
                                "doc_id": d_id,
                                "document_id": d_id,
                                "version": d_ver,
                                "field": cit.get("field", "policy_body"),
                                "span": cit.get("span"),
                                "content_hash": ret_hash,
                                "is_verified": snap["is_verified"] if snap else False,
                                "verification_error": snap["verification_error"] if snap else "SNAPSHOT_CREATION_FAILED",
                            })

                    # Also capture source snapshots for retrieved analysis documents
                    for doc_ret in raw_analysis.get("documents", []):
                        d_id = doc_ret.get("document_id") or doc_ret.get("doc_id")
                        d_ver = doc_ret.get("version")
                        ret_hash = doc_ret.get("content_hash")
                        if d_id and f"{d_id}:{d_ver}" not in snapshots:
                            snap = self._build_source_snapshot(
                                doc_id=d_id,
                                version=d_ver,
                                returned_content_hash=ret_hash,
                                is_injected=False,
                            )
                            snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap

                    terminal_status = suggestion_data.get("draft_status", "timeout") if reached_terminal else "timeout"
                    finite_latency = math.isfinite(wall_latency_ms) and wall_latency_ms > 0

                    # 1. Collection success: pipeline and observation completed without crash/timeout/parse error
                    collection_success = (
                        reached_terminal
                        and cust_json_valid
                        and cust_no_auto_send
                        and finite_latency
                        and terminal_status in ("draft_ready", "abstained", "escalation_recommended", "unavailable")
                    )

                    # 2. Action correctness: terminal state matches expected outcome
                    action_matches = False
                    if c["expected_action"] == "draft":
                        action_matches = (terminal_status == "draft_ready")
                    elif c["expected_action"] == "escalate":
                        action_matches = (terminal_status == "escalation_recommended")
                    elif c["expected_action"] == "abstain":
                        action_matches = (terminal_status == "abstained")

                    # 3. Reasons correctness: returned reason codes contain expected reason codes
                    actual_reasons = set(raw_routing.get("reason_codes", [])) | set(suggestion_data.get("reason_codes", []))
                    expected_reasons = c.get("expected_reasons", [])
                    reasons_match = all(r in actual_reasons for r in expected_reasons) if expected_reasons else True

                    # 4. Authority check: sensitive escalation requires authority flag
                    if c.get("slice") == "sensitive_escalation" or "requires_authority" in expected_reasons:
                        authority_check_passed = ("requires_authority" in actual_reasons)
                    else:
                        authority_check_passed = True

                    # 5. Source verification: all citations AND snapshots verified; expected documents present
                    all_citations_verified = (
                        all(cit.get("is_verified", False) for cit in parsed_citations)
                        if parsed_citations else True
                    )
                    all_snapshots_verified = (
                        all(s.get("is_verified", False) for s in snapshots.values())
                        if snapshots else True
                    )
                    if c["expected_action"] == "draft":
                        has_expected_docs = True
                        for exp_doc in c.get("expected_docs", []):
                            exp_d_id = exp_doc.split(":")[0]
                            if not any(s.get("doc_id") == exp_d_id or s.get("document_id") == exp_d_id for s in snapshots.values()):
                                has_expected_docs = False
                                break
                        source_verification_passed = (
                            (len(snapshots) >= 1)
                            and all_snapshots_verified
                            and all_citations_verified
                            and has_expected_docs
                        )
                    else:
                        source_verification_passed = all_snapshots_verified and all_citations_verified

                    is_case_success = (
                        collection_success
                        and action_matches
                        and reasons_match
                        and authority_check_passed
                        and source_verification_passed
                    )

                    # Acceptance status: in mock mode, dry run pending live authorization; in live mode, live result
                    if self.mode == "mock":
                        acceptance_status = "mock_dry_run_pending_coordinator_live_authorization"
                    else:
                        acceptance_status = "live_acceptance_passed" if is_case_success else "live_acceptance_failed"

                    records.append(
                        EvidenceCaseRecord(
                            case_id=case_id,
                            category=c.get("category", "unknown"),
                            slice=c.get("slice", "unknown"),
                            query=msg,
                            intent=c.get("intent", "unknown"),
                            order_id=c.get("order_id"),
                            planned_scenario_context=c.get("order_context", {}),
                            planned_as_of=c.get("as_of", "2026-06-15T10:00:00Z"),
                            actual_executed_order_context=executed_order_context,
                            actual_executed_as_of=executed_as_of,
                            component_evidence="application_postgresql_gateway",
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
                            response_versions=versions,
                            llm_metadata=llm_meta,
                            manifest_cases_sha256=self.manifest_cases_sha256,
                            full_draft_text=full_draft_text,
                            citations=parsed_citations,
                            source_snapshots=snapshots,
                            usage_metadata=usage_meta,
                            step_latencies_ms=step_latencies,
                            error_code=cust_observation_error or (None if reached_terminal else "TIMEOUT_POLLING_SUGGESTION"),
                            is_terminal=reached_terminal,
                            collection_success=collection_success,
                            action_matches_expected=action_matches,
                            reasons_match_expected=reasons_match,
                            authority_check_passed=authority_check_passed,
                            source_verification_passed=source_verification_passed,
                            is_success=is_case_success,
                            acceptance_status=acceptance_status,
                        )
                    )

        finally:
            if mock_gateway:
                mock_gateway.stop()

            if app_engine:
                try:
                    app_engine.dispose()
                except Exception:
                    pass

            if schema_created and not self.keep_schema and root_engine:
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

        # 6. Strictly separate application cases from component fixture cases
        app_records = [r for r in records if r.component_evidence == "application_postgresql_gateway"]
        fixture_records = [r for r in records if r.component_evidence == "retrieval_adapter_injected_fixture_execution"]

        # Application latency metrics strictly over application cases
        app_latencies = [
            r.submit_to_terminal_latency_ms
            for r in app_records
            if r.submit_to_terminal_latency_ms is not None and math.isfinite(r.submit_to_terminal_latency_ms)
        ]
        app_latencies.sort()
        app_p50_ms = None
        app_p95_ms = None
        if app_latencies:
            app_p50_ms = app_latencies[int(len(app_latencies) * 0.50)]
            app_p95_ms = app_latencies[min(int(math.ceil(len(app_latencies) * 0.95)) - 1, len(app_latencies) - 1)]

        app_no_auto_send_all = (
            all(r.customer_no_auto_send_observed is True for r in app_records)
            if app_records else False
        )
        app_errors = sum(1 for r in app_records if not r.is_success)

        # Component fixture latency metrics strictly over component cases
        fix_latencies = [
            r.submit_to_terminal_latency_ms
            for r in fixture_records
            if r.submit_to_terminal_latency_ms is not None and math.isfinite(r.submit_to_terminal_latency_ms)
        ]
        fix_latencies.sort()
        fix_p50_ms = fix_latencies[int(len(fix_latencies) * 0.50)] if fix_latencies else None
        fix_p95_ms = fix_latencies[min(int(math.ceil(len(fix_latencies) * 0.95)) - 1, len(fix_latencies) - 1)] if fix_latencies else None
        fix_errors = sum(1 for r in fixture_records if not r.is_success)

        total_errors = app_errors + fix_errors

        # 7. Write evidence records to disk (preserving all records, including failures)
        evidence_jsonl_path = out_dir / "evidence_records.jsonl"
        with open(evidence_jsonl_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(asdict(r)) + "\n")

        # 8. Write paired agent tasks template
        paired_manifest_path = out_dir / "paired_agent_study_manifest.json"
        if self.paired_tasks_path.exists():
            paired_tasks_content = json.loads(self.paired_tasks_path.read_text(encoding="utf-8"))
        else:
            paired_tasks_content = {"tasks": [], "status": "missing_template"}
        paired_manifest_path.write_text(json.dumps(paired_tasks_content, indent=2), encoding="utf-8")

        # 9. Write summary JSON with separated application and component blocks
        summary = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit_hash(),
            "mode": self.mode,
            "acceptance_status": (
                "mock_dry_run_pending_coordinator_live_authorization"
                if self.mode == "mock"
                else ("live_acceptance_verified" if total_errors == 0 else "live_acceptance_failed")
            ),
            "total_cases_submitted": len(records),
            "total_all_criteria_passed": sum(1 for r in records if r.is_success),
            "total_errors": total_errors,
            # Application boundary metrics (strictly separated)
            "application_metrics": {
                "cases_submitted": len(app_records),
                "collection_success_count": sum(1 for r in app_records if r.collection_success),
                "collection_failure_count": sum(1 for r in app_records if not r.collection_success),
                "action_correctness_count": sum(1 for r in app_records if r.action_matches_expected is True),
                "reasons_correctness_count": sum(1 for r in app_records if r.reasons_match_expected is True),
                "authority_check_passed_count": sum(1 for r in app_records if r.authority_check_passed is True),
                "source_verification_passed_count": sum(1 for r in app_records if r.source_verification_passed is True),
                "all_criteria_passed_count": sum(1 for r in app_records if r.is_success),
                "errors": app_errors,
                "customer_tickets_inspected": len(app_records),
                "customer_no_auto_send_verified_all": app_no_auto_send_all,
                "p50_latency_ms": app_p50_ms,
                "p95_latency_ms": app_p95_ms,
                "target_p95_under_12s": (app_p95_ms <= 12000.0) if app_p95_ms is not None else False,
            },
            # Component fixture metrics (strictly separated)
            "component_fixture_metrics": {
                "cases_submitted": len(fixture_records),
                "encoder_provenance": getattr(self, "encoder_provenance", "unknown"),
                "collection_success_count": sum(1 for r in fixture_records if r.collection_success),
                "expiry_filtering_verified_count": sum(1 for r in fixture_records if r.slice == "expired_injected_boundary" and r.is_success),
                "conflict_detection_verified_count": sum(1 for r in fixture_records if r.slice == "conflict_injected_boundary" and r.is_success),
                "source_verification_passed_count": sum(1 for r in fixture_records if r.source_verification_passed is True),
                "all_criteria_passed_count": sum(1 for r in fixture_records if r.is_success),
                "errors": fix_errors,
                "p50_latency_ms": fix_p50_ms,
                "p95_latency_ms": fix_p95_ms,
            },
            "active_kb_provenance": {
                "matched_kb_provenance": getattr(self, "matched_kb_provenance", "unknown"),
                "matched_line_ending": getattr(self, "matched_line_ending", "unknown"),
            },
            "slice_distribution": {
                s: sum(1 for r in records if r.slice == s)
                for s in sorted(set(r.slice for r in records))
            },
            "fixture_boundaries": {
                b: sum(1 for r in records if r.fixture_boundary == b)
                for b in sorted(set(r.fixture_boundary for r in records))
            },
            "component_evidence_distribution": {
                c: sum(1 for r in records if r.component_evidence == c)
                for c in sorted(set(r.component_evidence for r in records))
            },
            "immutable_source_snapshots_captured": sum(len(r.source_snapshots) for r in records),
            "manifest_cases_sha256": self.manifest_cases_sha256,
            "disclaimer": (
                "AI claim grading and manual/assisted agent trials are delegated to coordinator; no manual answers, times, or signoffs invented. "
                "In mock mode, synthetic gold responses are dry-run verification only and are never used to assert 100% production safety. "
                "Local evaluation approved by coordinator under delegated AI stakeholder authority (msg_01db6107a2e0); no instructor or crossgroup claim."
            ),
        }
        summary_path = out_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # 10. Write run manifest with all SHA-256 hashes
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
                "injected_fixtures_file": str(self.fixtures_path),
                "injected_fixtures_sha256": compute_sha256(self.fixtures_path) if self.fixtures_path.exists() else None,
                "matched_kb_provenance": getattr(self, "matched_kb_provenance", "unknown"),
                "matched_line_ending": getattr(self, "matched_line_ending", "unknown"),
                "active_kb_served_root_sha256": "f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec",
                "active_kb_local_lf_sha256": compute_sha256(self.active_kb_path) if self.active_kb_path.exists() else None,
                "active_kb_release_local_lf_sha256": compute_sha256(self.release_path) if self.release_path.exists() else None,
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
    app_meta = sum_data["application_metrics"]
    fix_meta = sum_data["component_fixture_metrics"]

    print("\nEvidence Collection Complete!")
    print(f"- Run ID: {run_id}")
    print(f"- Output Directory: {out_dir}")
    print(f"- Acceptance Status: {sum_data['acceptance_status']}")
    print(f"- Total Cases: {sum_data['total_cases_submitted']}")
    print(f"- Application Cases: {app_meta['cases_submitted']} (Collection Success: {app_meta['collection_success_count']}, Action Correctness: {app_meta['action_correctness_count']}, Errors: {app_meta['errors']})")
    app_p50 = f"{app_meta['p50_latency_ms']:.2f}ms" if app_meta['p50_latency_ms'] is not None else "N/A"
    app_p95 = f"{app_meta['p95_latency_ms']:.2f}ms" if app_meta['p95_latency_ms'] is not None else "N/A"
    print(f"- Application Latency: p50={app_p50}, p95={app_p95} (Under 12s: {app_meta['target_p95_under_12s']})")
    print(f"- Application Customer 100% No-Auto-Send: {'VERIFIED' if app_meta['customer_no_auto_send_verified_all'] else 'FAILED'}")
    print(f"- Component Fixture Cases: {fix_meta['cases_submitted']} (Expiry Verified: {fix_meta['expiry_filtering_verified_count']}, Conflict Verified: {fix_meta['conflict_detection_verified_count']}, Errors: {fix_meta['errors']})")
    print(f"- Source Snapshots Captured: {sum_data['immutable_source_snapshots_captured']}")


if __name__ == "__main__":
    main()

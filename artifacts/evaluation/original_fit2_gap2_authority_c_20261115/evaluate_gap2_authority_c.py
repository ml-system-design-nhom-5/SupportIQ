"""Worker C Independent Security & API Verification for Safety Gap 2 (Authority, Outage & Self-Approval).

Strictly isolated execution:
- Uses an isolated disposable PostgreSQL schema (dropped via CASCADE on exit) seeded with synthetic data.
- Never modifies source, models, datasets, runtime config, .local/ai.env, or real customer/prod records.
- Never prints or writes credentials, passwords, or database URLs.
- Executes the pre-frozen matrix in frozen_gap2_case_matrix.json against actual FastAPI routes, PostgreSQL
  triggers/locks, SuggestionWorker, and Engine/AI_REASONS contract.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
import uuid

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
MATRIX_PATH = OUT_DIR / "frozen_gap2_case_matrix.json"

sys.path.insert(0, str(REPO))

from apps.ai_service.engine import Engine  # noqa: E402
from apps.backend.main import create_app  # noqa: E402
from apps.backend.platform.config import Settings  # noqa: E402
from apps.backend.platform.database import Database  # noqa: E402
from apps.backend.platform.models import Account, AuditEntry, Order, Suggestion, SuggestionJob, Ticket  # noqa: E402
from apps.backend.seed import account_id, seed  # noqa: E402
from apps.backend.tickets import service as ticket_service  # noqa: E402
from apps.backend.tickets.jobs import AI_REASONS, SuggestionWorker, validate_analysis  # noqa: E402
from apps.core_backend.llm.gemini import ORDER_CONTEXT_ALLOWED_FIELDS  # noqa: E402
from apps.core_backend.safety import has_authority_request  # noqa: E402

INVARIANT_PINS: dict[str, str] = {
    "apps/core_backend/safety.py": "45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000",
    "apps/core_backend/retrieval/adapter.py": "3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f",
    "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json": "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39",
    "artifacts/models/trained/distilbert-supportiq/model.safetensors": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "data/knowledge/approved_kb.v2.json": "f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec",
    "apps/ai_service/kb-release.json": "cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804",
    "apps/core_backend/config/policies/intent_policy.v2.json": "8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7",
    ".local/training-cap-20261114.json": "bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922",
    ".local/ai.env": "26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87",
}

EXPECTED_AI_REASONS_29 = {
    "low_confidence", "signal_disagreement", "out_of_scope_intent", "human_agent_requested",
    "requires_authority", "no_valid_document", "only_expired_documents", "conflicting_sources",
    "missing_information", "insufficient_evidence", "source_review_overdue", "grounding_failed",
    "llm_unavailable", "llm_invalid_output", "budget_exceeded",
    "ai_service_unavailable", "ml_timeout", "ml_error", "ml_unavailable",
    "encoder_unavailable", "encoder_failure", "encoder_failed",
    "llm_timeout", "llm_rate_limited", "llm_insufficient_evidence",
    "selective_rejected", "low_margin", "invalid_model_output", "explicit_human_request",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_invariants() -> dict[str, Any]:
    observed = {}
    mismatches = []
    for rel, expected in INVARIANT_PINS.items():
        got = _sha256(REPO / rel)
        observed[rel] = got
        if got != expected:
            mismatches.append({"path": rel, "expected": expected, "observed": got})

    cap = json.loads((REPO / ".local/training-cap-20261114.json").read_text(encoding="utf-8"))
    cap_ok = (
        cap.get("additional_attempt_limit") == 2
        and cap.get("additional_attempts_started") == 2
        and cap.get("training_stopped") is True
        and cap.get("no_more_training_authorized") is True
    )
    if not cap_ok:
        mismatches.append({"path": ".local/training-cap-20261114.json", "error": "training_cap_not_2_of_2_stop"})

    sensitive_refs: list[str] = []
    for p in (REPO / "apps").rglob("*.py"):
        if "SENSITIVE_KEYWORDS" in p.read_text(encoding="utf-8", errors="ignore"):
            sensitive_refs.append(str(p.relative_to(REPO)).replace("\\", "/"))

    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, text=True).strip()
    diff_core = subprocess.check_output(
        ["git", "diff", "--name-only", "40c734389cbfe18d86ecb7d38b8407cb60494e50..HEAD", "--", "apps/", "data/"],
        cwd=REPO,
        text=True,
    ).splitlines()

    return {
        "git_head": git_head,
        "git_branch": git_branch,
        "diff_since_slice1_40c73438_apps_data": diff_core,
        "pinned_sha256": observed,
        "mismatches": mismatches,
        "sensitive_keywords_refs_in_apps": sensitive_refs,
        "training_cap_2_of_2_stopped": cap_ok,
        "passed": len(mismatches) == 0 and len(sensitive_refs) == 0 and diff_core == ["apps/backend/tickets/service.py"],
    }


def _load_pg_secrets() -> dict[str, Any]:
    path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", str(REPO / ".local/application.json")))
    if not path.exists():
        raise FileNotFoundError("Missing .local/application.json for disposable PG schema test")
    return json.loads(path.read_text(encoding="utf-8"))


def _make_disposable_pg_app(ai_service_base_url: str | None = None):
    local = _load_pg_secrets()
    owner_url = local["database_url_owner"]
    schema = f"test_gap2_c_{uuid.uuid4().hex[:16]}"
    root = create_engine(owner_url)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
    database = Database(engine)
    database.create_schema()
    passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
    seed(database, passwords)
    settings = Settings(
        database_url_app=local.get("database_url_app", owner_url),
        database_url_owner=owner_url,
        allowed_origins=["http://testserver"],
        session_cookie_secure=False,
        ai_service_base_url=ai_service_base_url,
    )
    app = create_app(settings=settings, database=database, start_worker=False)
    return root, schema, engine, database, settings, passwords, app


def _dispose_pg(root, schema: str, engine) -> None:
    engine.dispose()
    with root.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    root.dispose()


def _login(app, passwords: dict[str, str], role: str, login_name: str | None = None) -> TestClient:
    client = TestClient(app, headers={"Origin": "http://testserver"})
    res = client.post("/v1/sessions", json={"login_name": login_name or f"{role}-1", "password": passwords[role]})
    if res.status_code != 201:
        raise RuntimeError(f"Login failed for {login_name or role}: {res.status_code}")
    return client


def _post(client: TestClient, path: str, body: dict[str, Any], key: str | None = None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def _claim_job(database: Database, ticket_id: str) -> tuple[str, str, dict[str, Any]]:
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        sug = session.get(Suggestion, t.current_suggestion_id)
        job = session.get(SuggestionJob, sug.suggestion_id)
        job.lease_token = str(uuid.uuid4())
        return sug.suggestion_id, job.lease_token, dict(sug.request_payload)


def _valid_analysis_payload(intent: str = "track_order", recommendation: str = "draft", reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "intent": {"label": intent, "probability": 0.94, "confidence_band": "high"},
        "alternatives": [],
        "routing": {"recommendation": recommendation, "reason_codes": reasons or []},
        "documents": [],
        "warnings": [],
        "versions": {"release_id": "rel-gap2-c", "model_version": "fit2-orig"},
        "step_latency_ms": {"analysis": 12},
    }


def _valid_draft_ready_payload(analysis: dict[str, Any], text_body: str = "Your order is on the way.") -> dict[str, Any]:
    return {
        "status": "draft_ready",
        "reason_codes": [],
        "analysis": analysis,
        "draft": {
            "segments": [{"segment_id": "s1", "paragraph_index": 0, "text": text_body, "citation_ids": []}],
            "citations": [],
            "text": text_body,
        },
        "versions": analysis["versions"],
        "step_latency_ms": {"draft": 15},
    }


def _problem_code(res) -> str | None:
    try:
        t = res.json().get("type", "")
        return t.split(":")[-1] if ":" in t else t
    except Exception:
        return None


def _ticket_state(database: Database, ticket_id: str) -> dict[str, Any]:
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        sug = session.get(Suggestion, t.current_suggestion_id) if t.current_suggestion_id else None
        audits = session.scalars(select(AuditEntry.event_type).where(AuditEntry.ticket_id == ticket_id)).all()
        return {
            "status": t.status,
            "is_authority_required": t.is_authority_required,
            "has_reply": t.reply is not None,
            "current_suggestion_id": t.current_suggestion_id,
            "draft_status": (sug.payload or {}).get("draft_status") if sug else None,
            "reason_codes": (sug.payload or {}).get("reason_codes") if sug else [],
            "audit_events": list(audits),
            "reply_sent_audit_count": sum(1 for ev in audits if ev == "reply.sent"),
        }


def run_group_a_authority_outage(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    # Isolated schema 1: AI off + pseudonymize failure + intent_override
    root1, s1, eng1, db1, set1, pw1, app1 = _make_disposable_pg_app(ai_service_base_url=None)
    # Isolated schema 2: AI enabled for pending / timeout / sticky worker draft
    root2, s2, eng2, db2, set2, pw2, app2 = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-c:8002")
    try:
        c1 = _login(app1, pw1, "customer")
        st1 = _login(app1, pw1, "staff")
        c2 = _login(app2, pw2, "customer")
        st2 = _login(app2, pw2, "staff")

        for case in cases:
            cid, mode = case["id"], case["mode"]
            if mode == "ai_off":
                tr = _post(c1, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ws = st1.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st1, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct staff attempt."})
                st = _ticket_state(db1, tid)
                ok = (
                    tr.status_code == 201
                    and ws["is_authority_required"] is True
                    and "send_reply" not in ws["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                    and st["is_authority_required"] is True
                    and "reply.sent" not in st["audit_events"]
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "error_code": _problem_code(rr), "allowed_actions": ws["allowed_actions"], "db_state": st})

            elif mode == "ai_pending":
                tr = _post(c2, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ws = st2.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st2, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct while pending."})
                st = _ticket_state(db2, tid)
                ok = (
                    tr.status_code == 201
                    and ws["is_authority_required"] is True
                    and "send_reply" not in ws["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                    and st["is_authority_required"] is True
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "error_code": _problem_code(rr), "db_state": st})

            elif mode == "ml_timeout":
                tr = _post(c2, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ident, tok, payload = _claim_job(db2, tid)

                class _TimeoutHttp:
                    def post(self, url, json=None, timeout=None):
                        raise httpx.ReadTimeout("simulated ml timeout")

                SuggestionWorker(db2, set2, http_client=_TimeoutHttp()).process(ident, tok, payload)
                ws = st2.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st2, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct after timeout."})
                st = _ticket_state(db2, tid)
                ok = (
                    st["draft_status"] == "unavailable"
                    and "ml_timeout" in st["reason_codes"]
                    and ws["is_authority_required"] is True
                    and "send_reply" not in ws["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                    and st["is_authority_required"] is True
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "error_code": _problem_code(rr), "db_state": st})

            elif mode == "pseudonymization_failed":
                orig_pseudo = ticket_service.pseudonymize
                try:
                    def _raise_pseudo(text_in, known):
                        raise ValueError("simulated privacy failure")

                    ticket_service.pseudonymize = _raise_pseudo
                    tr = _post(c1, "/v1/shop/tickets", {"message": case["message"]})
                finally:
                    ticket_service.pseudonymize = orig_pseudo
                tid = tr.json()["ticket_id"]
                ws = st1.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st1, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct after privacy failure."})
                st = _ticket_state(db1, tid)
                ok = (
                    st["reason_codes"] == ["pseudonymization_failed"]
                    and ws["is_authority_required"] is True
                    and "send_reply" not in ws["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                    and st["is_authority_required"] is True
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "error_code": _problem_code(rr), "db_state": st})

            elif mode == "intent_override_sensitive":
                tr = _post(c1, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                # Initially non-authority
                ws_before = st1.get(f"/v1/console/tickets/{tid}").json()
                with db1.transaction() as session:
                    t = session.get(Ticket, tid)
                    sug = session.get(Suggestion, t.current_suggestion_id)
                    pl = dict(sug.payload)
                    pl["analysis_status"] = "ready"
                    sug.payload = pl
                ov = _post(st1, f"/v1/console/tickets/{tid}/suggestions", {"intent_override": case["intent_override"]})
                ws_after = st1.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st1, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct after sensitive override."})
                st = _ticket_state(db1, tid)
                ok = (
                    ws_before["is_authority_required"] is False
                    and ov.status_code == 202
                    and ws_after["is_authority_required"] is True
                    and "send_reply" not in ws_after["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "override_status": ov.status_code, "reply_status": rr.status_code, "error_code": _problem_code(rr), "db_state": st})

            elif mode == "sticky_override_and_worker_draft":
                tr = _post(c2, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ident, tok, payload = _claim_job(db2, tid)
                analysis = _valid_analysis_payload(intent="track_order", recommendation="draft", reasons=[])
                draft = _valid_draft_ready_payload(analysis)

                class _BogusDraftHttp:
                    def post(self, url, json=None, timeout=None):
                        return httpx.Response(200, json=analysis if url.endswith("/analyses") else draft, request=httpx.Request("POST", url))

                SuggestionWorker(db2, set2, http_client=_BogusDraftHttp()).process(ident, tok, payload)
                ov = _post(st2, f"/v1/console/tickets/{tid}/suggestions", {"intent_override": "track_order"})
                ident2, tok2, payload2 = _claim_job(db2, tid)
                SuggestionWorker(db2, set2, http_client=_BogusDraftHttp()).process(ident2, tok2, payload2)
                ws = st2.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(st2, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Direct after bogus worker draft + benign override."})
                st = _ticket_state(db2, tid)
                ok = (
                    ov.status_code == 202
                    and ws["is_authority_required"] is True
                    and "send_reply" not in ws["allowed_actions"]
                    and rr.status_code == 403
                    and _problem_code(rr) == "authority-required"
                    and not st["has_reply"]
                    and st["is_authority_required"] is True
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "error_code": _problem_code(rr), "db_state": st})
    finally:
        _dispose_pg(root1, s1, eng1)
        _dispose_pg(root2, s2, eng2)
    return results


def run_group_b_approval_and_promotion(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        cid, mode = case["id"], case["mode"]
        if mode in ("other_manager_approves", "legacy_admin_approves"):
            root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url=None)
            try:
                cust = _login(app, pw, "customer")
                staff = _login(app, pw, "staff")
                approver = _login(app, pw, case["approver_role"])
                tr = _post(cust, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                pr = _post(staff, f"/v1/console/tickets/{tid}/reply-proposals", {"basis": "no_ai_draft", "body": "Proposed authority reply."})
                pid = pr.json()["proposal_id"]
                ap = _post(approver, f"/v1/console/tickets/{tid}/replies", {"basis": "reply_proposal", "proposal_id": pid, "body": "Approved authority reply."})
                st = _ticket_state(db, tid)
                ok = pr.status_code == 201 and ap.status_code == 201 and st["status"] == "closed" and st["has_reply"] and "reply.sent" in st["audit_events"]
                results.append({"id": cid, "mode": mode, "passed": ok, "proposal_status": pr.status_code, "approve_status": ap.status_code, "db_state": st})
            finally:
                _dispose_pg(root, schema, eng)
        else:
            # Role promotion self-approval across ALL 4 reply bases on BOTH authority & normal tickets WITH draft_ready!
            root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-c:8002")
            try:
                cust = _login(app, pw, "customer")
                staff = _login(app, pw, "staff")
                admin = _login(app, pw, "admin")
                mgr = _login(app, pw, "manager")
                tr = _post(cust, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ident, tok, payload = _claim_job(db, tid)
                analysis = _valid_analysis_payload(intent="return_policy", recommendation="draft", reasons=[])
                draft = _valid_draft_ready_payload(analysis, "Here is the return policy summary.")

                class _ReadyHttp:
                    def post(self, url, json=None, timeout=None):
                        return httpx.Response(200, json=analysis if url.endswith("/analyses") else draft, request=httpx.Request("POST", url))

                SuggestionWorker(db, settings, http_client=_ReadyHttp()).process(ident, tok, payload)
                pr = _post(staff, f"/v1/console/tickets/{tid}/reply-proposals", {"basis": "ai_draft", "suggestion_id": ident, "body": "Staff draft proposal."})
                pid = pr.json()["proposal_id"]
                staff_acct_id = account_id("staff-1")
                promo = _post(admin, f"/v1/admin/accounts/{staff_acct_id}/role-changes", {"role": "manager"})
                stale_check = staff.get(f"/v1/console/tickets/{tid}")
                promoted_mgr = _login(app, pw, "staff", login_name="staff-1")
                ws_promoted = promoted_mgr.get(f"/v1/console/tickets/{tid}").json()

                basis_bodies = {
                    "reply_proposal": {"basis": "reply_proposal", "proposal_id": pid, "body": "Self approve proposal."},
                    "no_ai_draft": {"basis": "no_ai_draft", "suggestion_id": ident, "body": "Bypass via no_ai_draft."},
                    "ai_draft": {"basis": "ai_draft", "suggestion_id": ident, "body": "Bypass via ai_draft."},
                    "rejected_ai_draft": {"basis": "rejected_ai_draft", "suggestion_id": ident, "staff_reason_codes": ["tone_or_clarity"], "body": "Bypass via rejected_ai_draft."},
                }
                basis_results = {}
                for bname in case["bases"]:
                    r = _post(promoted_mgr, f"/v1/console/tickets/{tid}/replies", basis_bodies[bname])
                    basis_results[bname] = {"status": r.status_code, "error_code": _problem_code(r)}

                st_mid = _ticket_state(db, tid)
                # Verify another manager can approve cleanly afterwards
                other_ap = _post(mgr, f"/v1/console/tickets/{tid}/replies", {"basis": "reply_proposal", "proposal_id": pid, "body": "Manager-1 approved proposal."})
                st_end = _ticket_state(db, tid)

                all_403 = all(v["status"] == 403 and v["error_code"] == "self-approval-forbidden" for v in basis_results.values())
                ok = (
                    pr.status_code == 201
                    and promo.status_code == 201
                    and stale_check.status_code == 401
                    and ws_promoted["allowed_actions"] == []
                    and all_403
                    and not st_mid["has_reply"]
                    and st_mid["status"] == "awaiting_approval"
                    and other_ap.status_code == 201
                    and st_end["status"] == "closed"
                )
                results.append({
                    "id": cid,
                    "mode": mode,
                    "passed": ok,
                    "old_session_status": stale_check.status_code,
                    "promoted_allowed_actions": ws_promoted["allowed_actions"],
                    "basis_attempts": basis_results,
                    "other_manager_status": other_ap.status_code,
                    "db_state_end": st_end,
                })
            finally:
                _dispose_pg(root, schema, eng)
    return results


def run_group_c_and_contracts(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url=None)
    try:
        c1 = _login(app, pw, "customer", login_name="customer-1")
        c2 = _login(app, pw, "customer", login_name="customer-2")
        staff = _login(app, pw, "staff")

        for case in cases:
            cid, mode = case["id"], case["mode"]
            if mode in ("normal_staff_manual_reply_ai_off", "negated_normative_control"):
                tr = _post(c1, "/v1/shop/tickets", {"message": case["message"]})
                tid = tr.json()["ticket_id"]
                ws = staff.get(f"/v1/console/tickets/{tid}").json()
                rr = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Checked ORD-1001, shipment in transit."})
                st = _ticket_state(db, tid)
                ok = (
                    tr.status_code == 201
                    and ws["is_authority_required"] is False
                    and "send_reply" in ws["allowed_actions"]
                    and rr.status_code == 201
                    and st["status"] == "closed"
                    and st["has_reply"]
                    and "reply.sent" in st["audit_events"]
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "reply_status": rr.status_code, "db_state": st})

            elif mode == "cross_customer_and_role_isolation":
                tr = _post(c1, "/v1/shop/tickets", {"message": "Track ORD-1001"})
                tid = tr.json()["ticket_id"]
                with db.transaction() as session:
                    c1_order = session.scalar(select(Order.order_id).where(Order.customer_id == session.get(Account, account_id("customer-1")).customer_id).limit(1))
                c2_get = c2.get(f"/v1/shop/tickets/{tid}")
                c2_order_ticket = _post(c2, "/v1/shop/tickets", {"order_id": c1_order, "message": "Give me c1 order info"})
                cust_console = c1.get("/v1/console/tickets")
                ok = c2_get.status_code == 404 and c2_order_ticket.status_code == 404 and cust_console.status_code == 403
                results.append({"id": cid, "mode": mode, "passed": ok, "c2_get_ticket": c2_get.status_code, "c2_c1_order": c2_order_ticket.status_code, "cust_console": cust_console.status_code})

            elif mode == "idempotency_replay_and_conflict":
                tr = _post(c1, "/v1/shop/tickets", {"message": "Delivery status please."})
                tid = tr.json()["ticket_id"]
                ikey = f"idemp-{uuid.uuid4().hex}"
                r1 = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "First manual reply."}, key=ikey)
                r2 = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "First manual reply."}, key=ikey)
                r3 = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Mutated body same key."}, key=ikey)
                with db.transaction() as session:
                    sent_audits = session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.ticket_id == tid, AuditEntry.event_type == "reply.sent"))
                ok = r1.status_code == 201 and r2.status_code == 201 and r1.json()["reply_id"] == r2.json()["reply_id"] and r3.status_code == 409 and _problem_code(r3) == "idempotency-key-reused" and sent_audits == 1
                results.append({"id": cid, "mode": mode, "passed": ok, "r1": r1.status_code, "r2": r2.status_code, "r3": r3.status_code, "reply_sent_audits": sent_audits})

            elif mode == "closed_ticket_sequential_and_concurrent_race":
                tr = _post(c1, "/v1/shop/tickets", {"message": "Where is my order?"})
                tid = tr.json()["ticket_id"]

                def _send_one(idx: int):
                    cli = _login(app, pw, "staff")
                    return _post(cli, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": f"Concurrent reply {idx}"}).status_code

                with ThreadPoolExecutor(max_workers=2) as pool:
                    statuses = sorted(list(pool.map(_send_one, [1, 2])))
                prop_after = _post(staff, f"/v1/console/tickets/{tid}/reply-proposals", {"basis": "no_ai_draft", "body": "Late proposal"})
                with db.transaction() as session:
                    sent_audits = session.scalar(select(func.count()).select_from(AuditEntry).where(AuditEntry.ticket_id == tid, AuditEntry.event_type == "reply.sent"))
                ok = (
                    statuses == [201, 409]
                    and prop_after.status_code == 409
                    and _problem_code(prop_after) == "invalid-ticket-state"
                    and sent_audits == 1
                )
                results.append({"id": cid, "mode": mode, "passed": ok, "concurrent_statuses": statuses, "late_proposal_status": prop_after.status_code, "late_proposal_error": _problem_code(prop_after), "reply_sent_audits": sent_audits})

            elif mode == "concurrent_worker_store_and_pg_trigger":
                root_w, schema_w, eng_w, db_w, set_w, pw_w, app_w = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-c:8002")
                try:
                    cw = _login(app_w, pw_w, "customer")
                    tr = _post(cw, "/v1/shop/tickets", {"message": "I will contact my lawyer unless refunded."})
                    tid = tr.json()["ticket_id"]
                    ident, tok, _ = _claim_job(db_w, tid)
                    worker = SuggestionWorker(db_w, set_w)
                    routine_analysis = _valid_analysis_payload(intent="return_policy", recommendation="draft", reasons=[])
                    routine_draft = _valid_draft_ready_payload(routine_analysis)

                    def _store_task(i: int):
                        worker.store(ident, tok, "analysis" if i % 2 == 0 else "draft", routine_analysis if i % 2 == 0 else routine_draft, 5 + i)

                    with ThreadPoolExecutor(max_workers=3) as pool:
                        list(pool.map(_store_task, [0, 1, 2]))

                    trigger_blocked = False
                    trigger_msg = ""
                    try:
                        with eng_w.begin() as conn:
                            conn.execute(text("UPDATE tickets SET is_authority_required = FALSE WHERE ticket_id = :tid"), {"tid": tid})
                    except SQLAlchemyError as exc:
                        trigger_blocked = True
                        trigger_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)

                    st = _ticket_state(db_w, tid)
                    ok = st["is_authority_required"] is True and trigger_blocked and "Authority cannot be cleared" in trigger_msg
                    results.append({"id": cid, "mode": mode, "passed": ok, "db_state": st, "pg_trigger_blocked": trigger_blocked, "pg_trigger_error_present": "Authority cannot be cleared" in trigger_msg})
                finally:
                    _dispose_pg(root_w, schema_w, eng_w)

            elif mode == "bounded_29_ai_reasons_reject_unknown_and_order_context_parity":
                # 1. Exact 29 AI_REASONS match
                exact_29 = (len(AI_REASONS) == 29 and set(AI_REASONS) == EXPECTED_AI_REASONS_29)
                # 2. Unknown reason rejected by validate_analysis
                unknown_rejected = False
                try:
                    validate_analysis(_valid_analysis_payload(recommendation="abstain", reasons=["made_up_unknown_reason"]))
                except ValueError:
                    unknown_rejected = True
                # 3. SuggestionWorker fails closed when AI gateway returns unknown code
                root_u, schema_u, eng_u, db_u, set_u, pw_u, app_u = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-c:8002")
                try:
                    cu = _login(app_u, pw_u, "customer")
                    tr = _post(cu, "/v1/shop/tickets", {"message": "Check order ORD-1001"})
                    tid = tr.json()["ticket_id"]
                    ident, tok, payload = _claim_job(db_u, tid)
                    bad_analysis = _valid_analysis_payload(recommendation="abstain", reasons=["rogue_uncontracted_reason"])

                    class _RogueHttp:
                        def post(self, url, json=None, timeout=None):
                            return httpx.Response(200, json=bad_analysis, request=httpx.Request("POST", url))

                    SuggestionWorker(db_u, set_u, http_client=_RogueHttp()).process(ident, tok, payload)
                    st = _ticket_state(db_u, tid)
                    worker_fail_closed = (st["draft_status"] == "unavailable" and "rogue_uncontracted_reason" not in st["reason_codes"] and "ai_service_unavailable" in st["reason_codes"])

                    with db_u.transaction() as session:
                        ord_row = session.scalar(select(Order).where(Order.order_id == "ORD-1001"))
                        oc_keys = sorted(ticket_service.order_context(ord_row).keys())
                        all_orders = session.scalars(select(Order)).all()
                        refund_order = next((o for o in all_orders if o.payload.get("refund")), None)
                        oc_refund_keys = sorted(ticket_service.order_context(refund_order).keys()) if refund_order else oc_keys
                finally:
                    _dispose_pg(root_u, schema_u, eng_u)

                allowed_10 = list(ORDER_CONTEXT_ALLOWED_FIELDS)
                missing_4 = [f for f in allowed_10 if f not in oc_refund_keys]
                ok = exact_29 and unknown_rejected and worker_fail_closed
                results.append({
                    "id": cid,
                    "mode": mode,
                    "passed": ok,
                    "ai_reasons_count": len(AI_REASONS),
                    "ai_reasons_exact_29": exact_29,
                    "unknown_reason_rejected_by_validate_analysis": unknown_rejected,
                    "worker_fail_closed_on_unknown_reason": worker_fail_closed,
                    "order_context_nonrefund_fields": oc_keys,
                    "order_context_refund_fields": oc_refund_keys,
                    "order_context_refund_count": len(oc_refund_keys),
                    "order_context_allowed_fields": allowed_10,
                    "order_context_allowed_count": len(allowed_10),
                    "order_context_parity_missing_fields": missing_4,
                })
    finally:
        _dispose_pg(root, schema, eng)
    return results


def main() -> None:
    t0 = time.perf_counter()
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_sha = _sha256(MATRIX_PATH)
    cases = matrix["cases"]

    invariants = _check_invariants()
    grp_a = run_group_a_authority_outage([c for c in cases if c["group"] == "authority_outage"])
    grp_b = run_group_b_approval_and_promotion([c for c in cases if c["group"] == "approval_and_self_approval"])
    grp_c = run_group_c_and_contracts([c for c in cases if c["group"] in ("controls_and_concurrency", "reason_contract_and_parity")])

    all_cases = grp_a + grp_b + grp_c
    failed_cases = [c["id"] for c in all_cases if not c.get("passed")]
    verdict = "PASS" if (invariants["passed"] and not failed_cases and len(all_cases) == len(cases)) else "BLOCK"

    out = {
        "schema_version": "original_fit2_gap2_authority_c.v1",
        "frozen_matrix_path": str(MATRIX_PATH.relative_to(REPO)).replace("\\", "/"),
        "frozen_matrix_sha256": matrix_sha,
        "verdict": verdict,
        "total_matrix_cases": len(cases),
        "executed_cases": len(all_cases),
        "passed_cases": len(all_cases) - len(failed_cases),
        "failed_cases": failed_cases,
        "invariants": invariants,
        "group_a_authority_outage": grp_a,
        "group_b_approval_and_self_approval": grp_b,
        "group_c_controls_concurrency_contracts": grp_c,
        "duration_seconds": round(time.perf_counter() - t0, 2),
    }

    report_path = OUT_DIR / "gap2_security_verification.json"
    report_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    manifest = {
        "branch": invariants["git_branch"],
        "git_head": invariants["git_head"],
        "command": ".venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_gap2_authority_c_20261115/evaluate_gap2_authority_c.py",
        "verdict": verdict,
        "executed_cases": len(all_cases),
        "passed_cases": len(all_cases) - len(failed_cases),
        "failed_cases": failed_cases,
        "duration_seconds": out["duration_seconds"],
        "sha256": {
            "frozen_gap2_case_matrix.json": matrix_sha,
            "evaluate_gap2_authority_c.py": _sha256(OUT_DIR / "evaluate_gap2_authority_c.py"),
            "gap2_security_verification.json": _sha256(report_path),
        },
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DONE VERDICT={verdict} EXECUTED={len(all_cases)}/{len(cases)} PASSED={len(all_cases) - len(failed_cases)} FAILED={failed_cases} DUR_S={out['duration_seconds']}")


if __name__ == "__main__":
    main()

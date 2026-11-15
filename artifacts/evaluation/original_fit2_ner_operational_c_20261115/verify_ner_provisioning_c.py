"""Worker C Independent Real-NER Provisioning & Fail-Closed Verification.

Runs in isolated fresh Python subprocesses and a disposable PostgreSQL schema
(dropped via CASCADE) with httpx.MockTransport (zero external/paid HTTP calls).
Separates real spaCy en_core_web_sm NER execution from mocked AI HTTP transport.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("PSYCOPG_IMPL", "python")
pg_bin = Path("F:/PostgreSQL/bin")
if pg_bin.exists() and str(pg_bin) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{pg_bin};{os.environ.get('PATH', '')}"

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Account, Ticket
from apps.backend.seed import seed
from apps.backend.tickets import privacy as privacy_mod
from apps.backend.tickets.jobs import SuggestionJob, SuggestionWorker

OUT_DIR = Path(__file__).resolve().parent


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_wheel_provenance() -> dict:
    expected_sha = "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
    expected_url = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    spacy_dist = md.distribution("spacy")
    sm_dist = md.distribution("en_core_web_sm")
    direct_url_raw = sm_dist.read_text("direct_url.json") or "{}"
    direct_url = json.loads(direct_url_raw)
    actual_sha = ((direct_url.get("archive_info") or {}).get("hashes") or {}).get("sha256")
    actual_url = direct_url.get("url")
    return {
        "spacy_version": spacy_dist.version,
        "en_core_web_sm_version": sm_dist.version,
        "direct_url": actual_url,
        "direct_url_sha256": actual_sha,
        "matches_official_expectation": (
            spacy_dist.version == "3.8.18"
            and sm_dist.version == "3.8.0"
            and actual_url == expected_url
            and actual_sha == expected_sha
        ),
    }


def _run_fresh_process_real_ner_and_limits() -> dict:
    code = r"""
import json
from unittest.mock import patch
from apps.backend.platform.config import Settings
from apps.backend.tickets import privacy as p

s = Settings(ai_service_base_url="http://127.0.0.1:8002")
assert s.require_privacy_ner is True
assert p.is_privacy_ner_available() is True

samples = {
    "en_free_form": ("Hi, I am Michael Johnson living in Seattle asking about order ORD-1001.", {}),
    "en_multi": ("Please tell Robert Chen at Central Park in New York that bob@example.com called.", {}),
    "neg_order_facts": ("Order placed on 2026-11-10 for 1402000 VND with 30000 VND shipping is in transit.", {}),
    "limit_len2_state": ("Ship my package to WA today please.", {}),
    "limit_street_nosuffix": ("Deliver to 742 Evergreen Terrace quickly.", {}),
    "limit_vi_unaccented": ("Xin chao toi la anh nam o quan 1", {}),
    "limit_vi_accented": ("Tôi là Nguyễn Văn Minh ở 123 Đường Lê Lợi Quận 1", {}),
}
out = {}
for k, (txt, known) in samples.items():
    masked, pmap = p.pseudonymize(txt, known, require_ner=True)
    p.validate_egress_payload({"message": masked, "order_context": {}, "as_of": "2026-11-15T10:00:00Z"}, require_ner=True)
    restored = p.restore(masked, pmap)
    out[k] = {"input": txt, "masked": masked, "pmap": pmap, "roundtrip_ok": restored == txt}

# Failure injection fail-closed inside fresh process after NER was loaded
fail_modes = {}
for label, exc in (("missing_none", None), ("load_runtime_error", RuntimeError("ner_broken"))):
    def _raiser():
        if exc is not None:
            raise exc
        return None
    with patch.object(p, "_get_spacy_nlp", _raiser):
        pseudo_blocked = False
        egress_blocked = False
        try:
            p.pseudonymize("Hello Alice", {}, require_ner=True)
        except ValueError:
            pseudo_blocked = True
        try:
            p.validate_egress_payload({"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"}, require_ner=True)
        except ValueError:
            egress_blocked = True
        fail_modes[label] = {"pseudonymize_blocked": pseudo_blocked, "egress_blocked": egress_blocked}

print(json.dumps({"samples": out, "fail_modes": fail_modes}))
"""
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


@contextmanager
def _disposable_pg():
    local = json.loads((REPO / ".local/application.json").read_text(encoding="utf-8"))
    pw = local["passwords"]
    base_url = local["database_url_owner"]
    schema = f"test_ner_op_c_{uuid.uuid4().hex[:8]}"
    root = create_engine(base_url, hide_parameters=True)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    eng = create_engine(base_url, connect_args={"options": f"-csearch_path={schema}"}, hide_parameters=True)
    db = Database(eng)
    db.create_schema()
    seed(db, pw)
    try:
        yield db, base_url, schema, pw
    finally:
        db.engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        root.dispose()


def _run_real_ner_e2e_mock_http() -> dict:
    with _disposable_pg() as (db, base_url, schema, pw):
        settings = Settings(
            database_url_app=f"{base_url}?options=-csearch_path%3D{schema}",
            database_url_owner=base_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
            ai_service_base_url="http://mock-ai.local:8002",
        )
        app = create_app(settings=settings, database=db, start_worker=False)

        captured_requests = []

        def _handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            captured_requests.append({"path": request.url.path, "body": body})
            msg = body.get("message", "")
            # Mock response referencing masked placeholders present in outbound message
            draft_text = f"Hello [NAME_1] in [ADDRESS_1], thank you for reaching out."
            if request.url.path.endswith("/v1/analyses"):
                return httpx.Response(200, json={
                    "intent": {"label": "shipping_status", "probability": 0.96, "confidence_band": "high", "source": "model", "score_kind": "calibrated_temperature", "model_mode": "trained", "verified": True},
                    "alternatives": [],
                    "is_in_scope": True,
                    "documents": [],
                    "routing": {"recommendation": "draft", "reason_codes": []},
                    "warnings": [],
                    "versions": {"release_id": "mock-rel"},
                    "step_latency_ms": {"analysis": 5},
                })
            return httpx.Response(200, json={
                "status": "draft_ready",
                "reason_codes": [],
                "analysis": {
                    "intent": {"label": "shipping_status", "probability": 0.96, "confidence_band": "high", "source": "model", "score_kind": "calibrated_temperature", "model_mode": "trained", "verified": True},
                    "alternatives": [],
                    "is_in_scope": True,
                    "documents": [],
                    "routing": {"recommendation": "draft", "reason_codes": []},
                    "warnings": [],
                    "versions": {"release_id": "mock-rel"},
                    "step_latency_ms": {"analysis": 5},
                },
                "draft": {"segments": [{"paragraph_index": 0, "text": draft_text}], "citations": []},
                "versions": {"release_id": "mock-rel"},
                "step_latency_ms": {"analysis": 5, "llm": 10},
            })

        mock_http = httpx.Client(transport=httpx.MockTransport(_handler), trust_env=False)
        try:
            cust = TestClient(app)
            cust.post("/v1/sessions", json={"login_name": "customer-1", "password": pw["customer"]}, headers={"origin": "http://testserver"}).raise_for_status()
            staff = TestClient(app)
            staff.post("/v1/sessions", json={"login_name": "staff-1", "password": pw["staff"]}, headers={"origin": "http://testserver"}).raise_for_status()

            ready_resp = cust.get("/health/ready")
            ready_json = ready_resp.json()

            # 1. Real spaCy NER positive flow (name + city not in DB known!) -> worker MockTransport
            privacy_mod._SPACY_NLP = None
            raw_msg = "Hi, I am Michael Johnson living in Seattle checking order ORD-1001."
            t_resp = cust.post("/v1/shop/tickets", json={"message": raw_msg}, headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())})
            t_resp.raise_for_status()
            tid = t_resp.json()["ticket_id"]

            with db.transaction() as session:
                t = session.get(Ticket, tid)
                job = session.get(SuggestionJob, t.current_suggestion_id)
                sid = job.suggestion_id
                tok = str(uuid.uuid4())
                job.lease_token = tok
                from apps.backend.platform.models import Suggestion
                sug = session.get(Suggestion, sid)
                req_pl = dict(sug.request_payload)
                pmap_db = dict(sug.pseudonym_map)

            SuggestionWorker(db, settings, http_client=mock_http).process(sid, tok, req_pl)
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            restored_draft = " ".join(seg["text"] for seg in (ws["suggestion"].get("draft") or {}).get("segments", []))

            wire_dump = json.dumps(captured_requests)
            no_raw_pii_on_wire = (
                "Michael Johnson" not in wire_dump
                and "Seattle" not in wire_dump
                and "ORD-1001" not in wire_dump
                and "pseudonym_map" not in wire_dump
            )

            # 2. Fault-injected intake fail-closed makes 0 extra HTTP calls
            calls_before_fault = len(captured_requests)
            orig_get = privacy_mod._get_spacy_nlp
            privacy_mod._get_spacy_nlp = lambda: None
            try:
                f_resp = cust.post("/v1/shop/tickets", json={"message": "Hi I am Robert Chen from Chicago"}, headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())})
                f_resp.raise_for_status()
                ftid = f_resp.json()["ticket_id"]
                fws = staff.get(f"/v1/console/tickets/{ftid}").json()
            finally:
                privacy_mod._get_spacy_nlp = orig_get
            calls_after_fault = len(captured_requests)

            return {
                "health_ready": ready_json,
                "wire_request_count": len(captured_requests),
                "wire_paths": [r["path"] for r in captured_requests],
                "wire_message": captured_requests[0]["body"]["message"] if captured_requests else None,
                "db_pseudonym_map_keys": sorted(pmap_db.keys()),
                "no_raw_pii_on_wire": no_raw_pii_on_wire,
                "restored_draft": restored_draft,
                "fault_injection_reason_codes": fws["suggestion"]["reason_codes"],
                "fault_injection_draft_status": fws["suggestion"]["draft_status"],
                "fault_injection_extra_http_calls": calls_after_fault - calls_before_fault,
                "retry_disabled_on_fault": "retry_suggestion" not in fws["allowed_actions"],
            }
        finally:
            mock_http.close()


def main() -> None:
    t0 = time.perf_counter()
    wheel = _check_wheel_provenance()
    fresh = _run_fresh_process_real_ner_and_limits()
    e2e = _run_real_ner_e2e_mock_http()

    en_free = fresh["samples"]["en_free_form"]
    en_multi = fresh["samples"]["en_multi"]
    neg = fresh["samples"]["neg_order_facts"]

    passed = (
        wheel["matches_official_expectation"]
        and en_free["roundtrip_ok"]
        and "Michael Johnson" not in en_free["masked"]
        and "Seattle" not in en_free["masked"]
        and "ORD-1001" not in en_free["masked"]
        and en_multi["roundtrip_ok"]
        and "Robert Chen" not in en_multi["masked"]
        and "bob@example.com" not in en_multi["masked"]
        and neg["masked"] == neg["input"]
        and neg["pmap"] == {}
        and fresh["fail_modes"]["missing_none"] == {"pseudonymize_blocked": True, "egress_blocked": True}
        and fresh["fail_modes"]["load_runtime_error"] == {"pseudonymize_blocked": True, "egress_blocked": True}
        and e2e["health_ready"].get("privacy_ner_available") is True
        and e2e["wire_request_count"] == 2
        and e2e["no_raw_pii_on_wire"] is True
        and "Michael Johnson" in e2e["restored_draft"]
        and "Seattle" in e2e["restored_draft"]
        and e2e["fault_injection_reason_codes"] == ["pseudonymization_failed"]
        and e2e["fault_injection_extra_http_calls"] == 0
        and e2e["retry_disabled_on_fault"] is True
    )

    out = {
        "verdict": "PASS" if passed else "BLOCK",
        "duration_seconds": round(time.perf_counter() - t0, 2),
        "wheel_provenance": wheel,
        "fresh_process_real_ner": fresh,
        "real_ner_intake_worker_mock_http_e2e": e2e,
    }
    (OUT_DIR / "ner_provisioning_verification.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VERDICT={out['verdict']} WIRE_CALLS={e2e['wire_request_count']} DUR_S={out['duration_seconds']}")


if __name__ == "__main__":
    main()

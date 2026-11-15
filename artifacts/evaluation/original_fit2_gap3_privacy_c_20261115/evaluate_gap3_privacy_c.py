"""Worker C Independent Gap 3 Privacy Code Closure Verification.

Strictly bounded & isolated:
- Runs against disposable PostgreSQL schemas (dropped via CASCADE on exit) with synthetic data.
- Zero spaCy/pip downloads, zero runtime .env edits, zero app restarts, zero external LLM/network calls.
- Proves backend intake + worker HTTP egress boundaries under strict NER, fail-closed forged-job defenses,
  canonical masked transport, and sentinel-free span pseudonymization/restoration.
- Explicitly separates fake-NER boundary logic verification from operational spaCy/en_core_web_sm provisioning.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import uuid

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent
MATRIX_PATH = OUT_DIR / "frozen_gap3_case_matrix.json"

sys.path.insert(0, str(REPO))

from apps.backend.main import create_app  # noqa: E402
from apps.backend.platform.config import Settings  # noqa: E402
from apps.backend.platform.database import Database  # noqa: E402
from apps.backend.platform.models import AuditEntry, Order, Suggestion, SuggestionJob, Ticket  # noqa: E402
from apps.backend.seed import seed  # noqa: E402
from apps.backend.tickets import privacy as privacy_mod  # noqa: E402
from apps.backend.tickets.jobs import SuggestionWorker  # noqa: E402
from apps.core_backend.llm.gemini import ORDER_CONTEXT_ALLOWED_SET  # noqa: E402

INVARIANT_PINS: dict[str, str] = {
    "apps/core_backend/safety.py": "45d11761d95e00323e410f43b4bf4c6ff499c120c0cc5d89bcc3f30856c5e000",
    "apps/core_backend/retrieval/adapter.py": "3bd797dab79da0b89e5cdeb25a668ba704e31120523cb09824bb4b64264b5f8f",
    "apps/core_backend/llm/gemini.py": "c6dd495724472d160f967869ee7553aea2e74a3828bfded8bf45fb39146d865b",
    "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/model.safetensors": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "artifacts/models/candidates/reconstructed-fit2-supcon-20261113/calibration_manifest.json": "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39",
    "artifacts/models/trained/distilbert-supportiq/model.safetensors": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "data/knowledge/approved_kb.v2.json": "f8dcfbbdbb9cb2cd7a09d2ec12e0149083fdd4fa04931df6261fc4d1e6425fec",
    "apps/ai_service/kb-release.json": "cf450a72758e3d68ac7453802b5bc6c042ef2eddb9a6c4fa76483d4009c42804",
    "apps/core_backend/config/policies/intent_policy.v2.json": "8789ee26acdac2e105fea90942a1129553ca98db4b182fcc4d74880b1f537be7",
    ".local/training-cap-20261114.json": "bc0445e07cca46e7285539a921691050378cdf9ceb3fdfe2cfe911b90bfde922",
    ".local/ai.env": "26d083c75acd962010f2fbd0185af3e72e315d2bafc8d753046e51df6e8fce87",
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

    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO, text=True).strip()
    diff_apps = subprocess.check_output(
        ["git", "diff", "--name-only", "d3c4c2a0b6ac5cf789ef409305345c7154acc1da..HEAD", "--", "apps/"],
        cwd=REPO,
        text=True,
    ).splitlines()

    return {
        "git_head": git_head,
        "git_branch": git_branch,
        "diff_since_gap2_d3c4c2a0_apps": sorted(diff_apps),
        "pinned_sha256": observed,
        "mismatches": mismatches,
        "training_cap_2_of_2_stopped": cap_ok,
        "spacy_installed": importlib.util.find_spec("spacy") is not None,
        "passed": len(mismatches) == 0 and cap_ok,
    }


def _load_pg_secrets() -> dict[str, Any]:
    path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", str(REPO / ".local/application.json")))
    if not path.exists():
        raise FileNotFoundError("Missing .local/application.json for disposable PG schema test")
    return json.loads(path.read_text(encoding="utf-8"))


def _make_disposable_pg_app(ai_service_base_url: str | None = "http://mock-ai-gap3:8002"):
    local = _load_pg_secrets()
    owner_url = local["database_url_owner"]
    schema = f"test_gap3_c_{uuid.uuid4().hex[:16]}"
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


@contextmanager
def _patch_spacy(fn):
    orig_get = privacy_mod._get_spacy_nlp
    orig_cache = privacy_mod._SPACY_NLP
    privacy_mod._get_spacy_nlp = fn
    try:
        yield
    finally:
        privacy_mod._get_spacy_nlp = orig_get
        privacy_mod._SPACY_NLP = orig_cache


class _FakeEnt:
    def __init__(self, text: str, label_: str, start_char: int, end_char: int) -> None:
        self.text, self.label_, self.start_char, self.end_char = text, label_, start_char, end_char


class _FakeDoc:
    def __init__(self, ents: list[_FakeEnt]) -> None:
        self.ents = ents


def _fake_ner_factory(targets: list[tuple[str, str]]):
    def _nlp(text_in: str) -> _FakeDoc:
        ents: list[_FakeEnt] = []
        for needle, label in targets:
            idx = 0
            while True:
                pos = text_in.find(needle, idx)
                if pos == -1:
                    break
                ents.append(_FakeEnt(needle, label, pos, pos + len(needle)))
                idx = pos + len(needle)
        return _FakeDoc(ents)

    return lambda: _nlp


def _login(app, passwords: dict[str, str], role: str, login_name: str | None = None) -> TestClient:
    cli = TestClient(app, headers={"Origin": "http://testserver"})
    r = cli.post("/v1/sessions", json={"login_name": login_name or f"{role}-1", "password": passwords[role]})
    if r.status_code != 201:
        raise RuntimeError(f"Login failed for {login_name or role}: {r.status_code}")
    return cli


def _post(client: TestClient, path: str, body: dict[str, Any], key: str | None = None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def _claim_job(database: Database, ticket_id: str) -> tuple[str, str, dict[str, Any]]:
    with database.transaction() as session:
        t = session.get(Ticket, ticket_id)
        sug = session.get(Suggestion, t.current_suggestion_id)
        job = session.get(SuggestionJob, sug.suggestion_id)
        job.lease_token = str(uuid.uuid4())
        return sug.suggestion_id, job.lease_token, dict(sug.request_payload)


def _seed_tampered_job(database: Database, customer_id: str, req_payload: dict[str, Any], pmap: dict[str, str] | None = None) -> tuple[str, str]:
    tid = f"TCK-{uuid.uuid4().hex[:8].upper()}"
    sid = str(uuid.uuid4())
    tok = str(uuid.uuid4())
    with database.transaction() as session:
        t = Ticket(ticket_id=tid, customer_id=customer_id, created_at=datetime.now(timezone.utc), status="open", handling_mode="assisted", is_authority_required=False)
        session.add(t)
        session.flush()
        payload = {"suggestion_id": sid, "trigger": "ticket_created", "analysis_status": "pending", "draft_status": "pending", "reason_codes": [], "warnings": [], "trace_id": "t-c", "versions": None, "step_latency_ms": {}}
        session.add(Suggestion(suggestion_id=sid, ticket_id=tid, created_at=t.created_at, payload=payload, request_payload=req_payload, pseudonym_map=pmap or {}))
        session.flush()
        session.add(SuggestionJob(suggestion_id=sid, attempts=1, lease_token=tok))
        t.current_suggestion_id = sid
    return sid, tok


def run_group_a_strict_enforcement() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    local = _load_pg_secrets()
    db_url = local["database_url_app"]

    # 1. g3-cfg-strict-default
    default_s = Settings(database_url_app=db_url)
    rejected_urls = []
    for url in ("http://localhost:8002", "http://127.0.0.1:8002", "https://ai.example.com", ""):
        try:
            Settings(database_url_app=db_url, ai_service_base_url=url, require_privacy_ner=False)
            rejected_urls.append(False)
        except ValidationError:
            rejected_urls.append(True)
    rejected_envs = []
    orig_env = os.environ.get("SUPPORTIQ_REQUIRE_PRIVACY_NER")
    try:
        for val in ("false", "0", "no", "off", "FALSE"):
            os.environ["SUPPORTIQ_REQUIRE_PRIVACY_NER"] = val
            try:
                Settings(database_url_app=db_url, ai_service_base_url="http://localhost:8002")
                rejected_envs.append(False)
            except ValidationError:
                rejected_envs.append(True)
    finally:
        if orig_env is None:
            os.environ.pop("SUPPORTIQ_REQUIRE_PRIVACY_NER", None)
        else:
            os.environ["SUPPORTIQ_REQUIRE_PRIVACY_NER"] = orig_env
    results.append({
        "id": "g3-cfg-strict-default",
        "passed": default_s.require_privacy_ner is True and all(rejected_urls) and all(rejected_envs),
        "default_require_privacy_ner": default_s.require_privacy_ner,
        "url_rejections": len(rejected_urls),
        "env_rejections": len(rejected_envs),
    })

    # Disposable PG schema for intake & worker strict checks
    root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-gap3:8002")
    try:
        cust = _login(app, pw, "customer")
        staff = _login(app, pw, "staff")
        mgr = _login(app, pw, "manager")

        # 2. g3-intake-missing-ner
        with _patch_spacy(lambda: None):
            r = _post(cust, "/v1/shop/tickets", {"message": "Where is ORD-1001 for Alice Smith?"})
            tid = r.json()["ticket_id"]
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            with db.transaction() as session:
                jobs = session.scalar(select(func.count()).select_from(SuggestionJob).where(SuggestionJob.suggestion_id == ws["suggestion"]["suggestion_id"]))
                aud = session.scalars(select(AuditEntry).where(AuditEntry.ticket_id == tid, AuditEntry.event_type == "message.pseudonymized")).first()
                aud_outcome = aud.data.get("outcome") if aud else None
        results.append({
            "id": "g3-intake-missing-ner",
            "passed": r.status_code == 201 and ws["suggestion"]["draft_status"] == "unavailable" and ws["suggestion"]["reason_codes"] == ["pseudonymization_failed"] and jobs == 0 and aud_outcome == "failed" and "retry_suggestion" not in ws["allowed_actions"],
            "draft_status": ws["suggestion"]["draft_status"],
            "reason_codes": ws["suggestion"]["reason_codes"],
            "jobs_queued": jobs,
            "audit_outcome": aud_outcome,
            "allowed_actions": ws["allowed_actions"],
        })

        # 3. g3-intake-load-exc
        def _boom_load():
            raise OSError("en_core_web_sm missing on disk")
        secret = "SecretLoadCustomer"
        with _patch_spacy(_boom_load):
            r = _post(cust, "/v1/shop/tickets", {"message": f"Hi I am {secret}, check ORD-1001"})
            tid = r.json()["ticket_id"]
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            with db.transaction() as session:
                sug = session.get(Suggestion, ws["suggestion"]["suggestion_id"])
                aud_str = json.dumps([a.data for a in session.scalars(select(AuditEntry).where(AuditEntry.ticket_id == tid)).all()])
                jobs = session.scalar(select(func.count()).select_from(SuggestionJob).where(SuggestionJob.suggestion_id == sug.suggestion_id))
                leak = secret in json.dumps(sug.payload) or secret in aud_str
        results.append({
            "id": "g3-intake-load-exc",
            "passed": ws["suggestion"]["reason_codes"] == ["pseudonymization_failed"] and jobs == 0 and not leak,
            "reason_codes": ws["suggestion"]["reason_codes"],
            "jobs_queued": jobs,
            "secret_leaked_in_payload_or_audit": leak,
        })

        # 4. g3-intake-runtime-exc
        def _boom_nlp(_text: str):
            raise RuntimeError("runtime inference segfault")
        secret_rt = "SecretRuntimeUser"
        with _patch_spacy(lambda: _boom_nlp):
            r = _post(cust, "/v1/shop/tickets", {"message": f"Help {secret_rt} on ORD-1001"})
            tid = r.json()["ticket_id"]
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            with db.transaction() as session:
                sug = session.get(Suggestion, ws["suggestion"]["suggestion_id"])
                jobs = session.scalar(select(func.count()).select_from(SuggestionJob).where(SuggestionJob.suggestion_id == sug.suggestion_id))
                leak = secret_rt in json.dumps(sug.payload)
        results.append({
            "id": "g3-intake-runtime-exc",
            "passed": ws["suggestion"]["reason_codes"] == ["pseudonymization_failed"] and jobs == 0 and not leak,
            "reason_codes": ws["suggestion"]["reason_codes"],
            "jobs_queued": jobs,
            "secret_leaked": leak,
        })

        # 5. g3-worker-direct-strict (production None, real httpx.Client, MockTransport+URL, duck stub+URL)
        http_calls = 0

        def _spy_handler(req: httpx.Request) -> httpx.Response:
            nonlocal http_calls
            http_calls += 1
            return httpx.Response(500, json={"detail": "must not be called"})

        class _DuckSpy:
            def post(self, url, json=None, timeout=None):
                nonlocal http_calls
                http_calls += 1
                raise AssertionError("Must not be called")

        configs = [
            ("none_prod", settings, None),
            ("real_httpx_client", settings, httpx.Client()),
            ("mock_transport_with_url", settings, httpx.Client(transport=httpx.MockTransport(_spy_handler))),
            ("duck_stub_with_url_and_false_flag", SimpleNamespace(ai_service_base_url="http://mock-ai-gap3:8002", require_privacy_ner=False, ai_service_analysis_timeout_ms=3000, ai_service_draft_timeout_ms=5000), _DuckSpy()),
        ]
        modes_ok = {}
        with _patch_spacy(lambda: None):
            for label, cfg, client_obj in configs:
                with db.transaction() as session:
                    cust_id = session.scalar(select(Ticket.customer_id).limit(1))
                sid, tok = _seed_tampered_job(db, cust_id, {"message": "Clean masked text [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"})
                worker = SuggestionWorker(db, cfg, http_client=client_obj)
                if isinstance(client_obj, httpx.Client):
                    try:
                        worker.process(sid, tok, {"message": "Clean masked text [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"})
                    finally:
                        client_obj.close()
                else:
                    worker.process(sid, tok, {"message": "Clean masked text [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"})
                with db.transaction() as session:
                    pl = session.get(Suggestion, sid).payload
                modes_ok[label] = pl.get("reason_codes") == ["pseudonymization_failed"] and http_calls == 0
        results.append({
            "id": "g3-worker-direct-strict",
            "passed": all(modes_ok.values()) and http_calls == 0,
            "http_calls": http_calls,
            "modes_ok": modes_ok,
        })

        # 6. g3-authority-sticky-manual
        with _patch_spacy(lambda: None):
            r = _post(cust, "/v1/shop/tickets", {"message": "My lawyer demands a bank dispute exception now."})
            tid = r.json()["ticket_id"]
            ws = staff.get(f"/v1/console/tickets/{tid}").json()
            staff_reply = _post(staff, f"/v1/console/tickets/{tid}/replies", {"basis": "no_ai_draft", "body": "Blocked manual send."})
            prop = _post(staff, f"/v1/console/tickets/{tid}/reply-proposals", {"basis": "no_ai_draft", "body": "Proposal after privacy fail."})
            pid = prop.json()["proposal_id"]
            ap = _post(mgr, f"/v1/console/tickets/{tid}/replies", {"basis": "reply_proposal", "proposal_id": pid, "body": "Manager manual approval."})
            with db.transaction() as session:
                t = session.get(Ticket, tid)
                ok = (
                    ws["is_authority_required"] is True
                    and "retry_suggestion" not in ws["allowed_actions"]
                    and staff_reply.status_code == 403
                    and prop.status_code == 201
                    and ap.status_code == 201
                    and t.is_authority_required is True
                    and t.status == "closed"
                )
        results.append({
            "id": "g3-authority-sticky-manual",
            "passed": ok,
            "staff_reply_status": staff_reply.status_code,
            "proposal_status": prop.status_code,
            "manager_approve_status": ap.status_code,
        })
    finally:
        _dispose_pg(root, schema, eng)
    return results


def run_group_b_egress_and_forged_jobs() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-gap3:8002")
    http_calls = 0

    def _fail_spy(req: httpx.Request) -> httpx.Response:
        nonlocal http_calls
        http_calls += 1
        return httpx.Response(500, json={"detail": "unexpected HTTP egress"})

    try:
        mock_http = httpx.Client(transport=httpx.MockTransport(_fail_spy))
        with db.transaction() as session:
            cust_id = session.scalar(select(Order.customer_id).limit(1))

        def _run_bad_worker(req_payload: Any, pmap: dict[str, str] | None = None, with_fake_ner: bool = True) -> dict[str, Any]:
            sid, tok = _seed_tampered_job(db, cust_id, req_payload if isinstance(req_payload, dict) else {"raw": req_payload}, pmap)
            ctx = _patch_spacy(_fake_ner_factory([])) if with_fake_ner else _patch_spacy(lambda: None)
            with ctx:
                SuggestionWorker(db, settings, http_client=mock_http).process(sid, tok, req_payload)
            with db.transaction() as session:
                return dict(session.get(Suggestion, sid).payload)

        # 1. g3-egress-extra-nested
        c_pre = http_calls
        pl1 = _run_bad_worker({"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z", "pseudonym_map": {"[NAME_1]": "Bob"}})
        pl2 = _run_bad_worker({"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z", "extra": {"nested": "bad"}})
        results.append({
            "id": "g3-egress-extra-nested",
            "passed": http_calls == c_pre and pl1["reason_codes"] == ["pseudonymization_failed"] and pl2["reason_codes"] == ["pseudonymization_failed"],
            "http_calls": http_calls - c_pre,
        })

        # 2. g3-egress-raw-msg-pii
        c_pre = http_calls
        bad_msgs = [
            "Email me at alice@example.com",
            "Call +84 912 345 678 now",
            "Ship to 123 Nguyen Hue Street",
            "Card 4111111111111111 leaked",
            "Order ORD-1001 leaked",
            "Tracking TRK-998811 leaked",
            "Txn TXN-554433 leaked",
            "Legacy sentinel \x00P0\x00 leaked",
        ]
        pls = [_run_bad_worker({"message": m, "order_context": {}, "as_of": "2026-11-15T10:00:00Z"}) for m in bad_msgs]
        results.append({
            "id": "g3-egress-raw-msg-pii",
            "passed": http_calls == c_pre and all(p["reason_codes"] == ["pseudonymization_failed"] for p in pls),
            "checked_vectors": len(bad_msgs),
            "http_calls": http_calls - c_pre,
        })

        # 3. g3-egress-orderctx-pii
        c_pre = http_calls
        bad_ctxs = [
            {"order_status": "shipped to alice@example.com"},
            {"order_status": "call 0912345678"},
            {"order_status": "at 123 Nguyen Hue Street"},
            {"order_status": "shipped", "customer_note": "extra"},
            {"order_status": "shipped", "payment_status": "paid"},
            {"order_total": {"amount_minor": True, "currency": "VND"}},
            {"order_total": {"amount_minor": 1000, "currency": "VND", "extra": 1}},
            {"placed_at": "invalid-date"},
        ]
        pls = [_run_bad_worker({"message": "Hi [NAME_1]", "order_context": ctx, "as_of": "2026-11-15T10:00:00Z"}) for ctx in bad_ctxs]
        results.append({
            "id": "g3-egress-orderctx-pii",
            "passed": http_calls == c_pre and all(p["reason_codes"] == ["pseudonymization_failed"] for p in pls),
            "checked_vectors": len(bad_ctxs),
            "http_calls": http_calls - c_pre,
        })

        # 4. g3-egress-asof-intent
        c_pre = http_calls
        bad_meta = [
            {"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00"},
            {"message": "Hi [NAME_1]", "order_context": {}, "as_of": "not-a-date"},
            {"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z", "intent_override": "email bob@example.com"},
            {"message": "Hi [NAME_1]", "order_context": {}, "as_of": "2026-11-15T10:00:00Z", "intent_override": {"bad": 1}},
        ]
        pls = [_run_bad_worker(m) for m in bad_meta]
        results.append({
            "id": "g3-egress-asof-intent",
            "passed": http_calls == c_pre and all(p["reason_codes"] == ["pseudonymization_failed"] for p in pls),
            "checked_vectors": len(bad_meta),
            "http_calls": http_calls - c_pre,
        })

        # 5. g3-egress-known-db-map
        c_pre = http_calls
        secret_name = "Nguyen Thi Lan"
        pl = _run_bad_worker(
            {"message": f"Hello {secret_name} check status", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"},
            pmap={"[NAME_1]": secret_name},
        )
        results.append({
            "id": "g3-egress-known-db-map",
            "passed": http_calls == c_pre and pl["reason_codes"] == ["pseudonymization_failed"] and secret_name not in json.dumps(pl),
            "http_calls": http_calls - c_pre,
            "secret_absent_from_payload": secret_name not in json.dumps(pl),
        })

        # 6. g3-egress-stale-ner-race
        c_pre = http_calls
        cust = _login(app, pw, "customer")
        staff = _login(app, pw, "staff")
        with _patch_spacy(_fake_ner_factory([("Tran Bao", "PERSON")])):
            tr = _post(cust, "/v1/shop/tickets", {"message": "Hi I am Tran Bao checking my parcel."})
        tid = tr.json()["ticket_id"]
        sid, tok, req_pl = _claim_job(db, tid)
        with _patch_spacy(lambda: None):
            SuggestionWorker(db, settings, http_client=mock_http).process(sid, tok, req_pl)
        ws = staff.get(f"/v1/console/tickets/{tid}").json()
        results.append({
            "id": "g3-egress-stale-ner-race",
            "passed": http_calls == c_pre and ws["suggestion"]["reason_codes"] == ["pseudonymization_failed"] and "retry_suggestion" not in ws["allowed_actions"],
            "http_calls": http_calls - c_pre,
            "allowed_actions": ws["allowed_actions"],
        })

        # 7. g3-error-no-map-exfil
        err_msgs = []
        raw_secret = "SecretExfilName"
        for probe in (
            {"message": f"Email secret.exfil@example.com and {raw_secret}", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"},
            {"message": "Ok [NAME_1]", "order_context": {"order_status": "phone +84901234567"}, "as_of": "2026-11-15T10:00:00Z"},
        ):
            try:
                with _patch_spacy(_fake_ner_factory([])):
                    privacy_mod.validate_egress_payload(probe, require_ner=True, forbidden_values=(raw_secret,))
            except ValueError as exc:
                err_msgs.append(str(exc))
        leaked_err = any(tok in m for m in err_msgs for tok in ("secret.exfil@example.com", raw_secret, "+84901234567"))
        results.append({
            "id": "g3-error-no-map-exfil",
            "passed": len(err_msgs) == 2 and not leaked_err,
            "captured_errors": err_msgs,
        })

        # 8. g3-unknown-placeholder-vs-forged
        c_pre = http_calls
        with _patch_spacy(_fake_ner_factory([])):
            masked_unk, map_unk = privacy_mod.pseudonymize("Ref token [FOOBAR_1] from customer portal", {}, require_ner=True)
            masked_real_lit, map_real_lit = privacy_mod.pseudonymize("Printed [EMAIL_1] vs real alice@example.com", {}, require_ner=True)
        # Unknown literal [FOOBAR_1] passes egress validation; forged DB mapping [EMAIL_1]->forged@example.com stays blocked
        unk_allowed = False
        with _patch_spacy(_fake_ner_factory([])):
            privacy_mod.validate_egress_payload({"message": masked_unk, "order_context": {}, "as_of": "2026-11-15T10:00:00Z"}, require_ner=True)
            unk_allowed = True
        forged_blocked = _run_bad_worker(
            {"message": "Leaked forged@example.com", "order_context": {}, "as_of": "2026-11-15T10:00:00Z"},
            pmap={"[EMAIL_1]": "forged@example.com"},
        )
        # [LITERAL_1] containing "[EMAIL_1]" in pmap must NOT falsely reject masked [LITERAL_1]
        lit_map_ok = False
        with _patch_spacy(_fake_ner_factory([])):
            privacy_mod.validate_egress_payload({"message": masked_real_lit, "order_context": {}, "as_of": "2026-11-15T10:00:00Z"}, require_ner=True, forbidden_values=("alice@example.com",))
            lit_map_ok = True
        results.append({
            "id": "g3-unknown-placeholder-vs-forged",
            "passed": unk_allowed and masked_unk == "Ref token [FOOBAR_1] from customer portal" and map_unk == {} and map_real_lit.get("[LITERAL_1]") == "[EMAIL_1]" and forged_blocked["reason_codes"] == ["pseudonymization_failed"] and lit_map_ok and http_calls == c_pre,
            "masked_unknown": masked_unk,
            "map_literal_isolated": map_real_lit,
        })
    finally:
        mock_http.close()
        _dispose_pg(root, schema, eng)
    return results


def run_group_c_positive_and_spans() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    root, schema, eng, db, settings, pw, app = _make_disposable_pg_app(ai_service_base_url="http://mock-ai-gap3:8002")
    captured_requests: list[dict[str, Any]] = []

    def _ai_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured_requests.append({"url": str(request.url), "body": body})
        analysis = {
            "intent": {"label": "track_order", "probability": 0.95, "confidence_band": "high"},
            "alternatives": [],
            "routing": {"recommendation": "draft", "reason_codes": []},
            "documents": [],
            "warnings": [],
            "versions": {"release_id": "rel-gap3-c", "model_version": "fit2-orig"},
            "step_latency_ms": {"analysis": 10},
        }
        if request.url.path.endswith("/analyses"):
            return httpx.Response(200, json=analysis)
        draft = {
            "status": "draft_ready",
            "reason_codes": [],
            "analysis": analysis,
            "draft": {
                "segments": [{"segment_id": "s1", "paragraph_index": 0, "text": "Hello [NAME_1], order [ORDER_ID_1] is shipping.", "citation_ids": []}],
                "citations": [],
            },
            "versions": analysis["versions"],
            "step_latency_ms": {"draft": 12},
        }
        return httpx.Response(200, json=draft)

    mock_http = httpx.Client(transport=httpx.MockTransport(_ai_handler))
    try:
        cust = _login(app, pw, "customer")
        staff = _login(app, pw, "staff")
        with _patch_spacy(_fake_ner_factory([("Tran Minh", "PERSON"), ("Hanoi", "GPE")])):
            tr = _post(cust, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": "Hi, I am Tran Minh in Hanoi asking about ORD-1001."})
        tid = tr.json()["ticket_id"]
        sid, tok, req_pl = _claim_job(db, tid)
        with _patch_spacy(_fake_ner_factory([])):
            SuggestionWorker(db, settings, http_client=mock_http).process(sid, tok, req_pl)
        ws = staff.get(f"/v1/console/tickets/{tid}").json()

        wire_json = json.dumps(captured_requests)
        first_body = captured_requests[0]["body"] if captured_requests else {}
        oc_keys = set((first_body.get("order_context") or {}).keys())
        pos_ok = (
            len(captured_requests) == 2
            and captured_requests[0]["url"].endswith("/v1/analyses")
            and captured_requests[1]["url"].endswith("/v1/drafts")
            and "Tran Minh" not in wire_json
            and "Hanoi" not in wire_json
            and "ORD-1001" not in wire_json
            and "pseudonym_map" not in first_body
            and oc_keys <= ORDER_CONTEXT_ALLOWED_SET
            and "order_id" not in oc_keys
            and "tracking_code" not in oc_keys
            and "Tran Minh" in ws["suggestion"]["draft"]["text"]
            and "ORD-1001" in ws["suggestion"]["draft"]["text"]
        )
        results.append({
            "id": "g3-pos-masked-e2e-transport",
            "passed": pos_ok,
            "http_call_count": len(captured_requests),
            "wire_message": first_body.get("message"),
            "wire_order_context_keys": sorted(oc_keys),
            "restored_draft_text": ws["suggestion"]["draft"]["text"],
        })
    finally:
        mock_http.close()
        _dispose_pg(root, schema, eng)

    # Remaining span & positive unit boundary probes
    with _patch_spacy(_fake_ner_factory([])):
        # 2. g3-pos-ordinary-dates-money
        msg_ord = "Ordered on 2026-11-10 at 2026-11-15T12:00:00+07:00, qty 3 for 1402000 VND."
        m_ord, map_ord = privacy_mod.pseudonymize(msg_ord, {}, require_ner=True)
        privacy_mod.validate_egress_payload({
            "message": m_ord,
            "order_context": {
                "order_status": "shipped",
                "placed_at": "2026-11-10T07:00:00Z",
                "order_total": {"amount_minor": 1402000, "currency": "VND"},
                "shipping_cost": {"amount_minor": 0, "currency": "VND"},
                "shipment_status": "in_transit",
            },
            "as_of": "2026-11-15T12:00:00+07:00",
        }, require_ner=True)
        results.append({
            "id": "g3-pos-ordinary-dates-money",
            "passed": m_ord == msg_ord and map_ord == {},
        })

        # 3. g3-span-literal-forgery
        txt_lit = "Your form showed [EMAIL_1] when I typed bob@example.com"
        m_lit, map_lit = privacy_mod.pseudonymize(txt_lit, {}, require_ner=True)
        rest_lit = privacy_mod.restore(m_lit, map_lit)
        results.append({
            "id": "g3-span-literal-forgery",
            "passed": "[LITERAL_1]" in m_lit and "[EMAIL_1]" in m_lit and rest_lit == txt_lit,
            "masked": m_lit,
        })

        # 4. g3-span-nested-nul-unicode
        txt_nu = "Xin chào \x00 nested [[EMAIL_1]] từ lan@example.com"
        m_nu, map_nu = privacy_mod.pseudonymize(txt_nu, {}, require_ner=True)
        rest_nu = privacy_mod.restore(m_nu, map_nu)
        results.append({
            "id": "g3-span-nested-nul-unicode",
            "passed": "lan@example.com" not in m_nu and rest_nu == txt_nu,
        })

        # 5. g3-span-p0p1-short-known
        txt_p = "Priority P0 ticket for customer P1 with alice@example.com"
        m_p, map_p = privacy_mod.pseudonymize(txt_p, {"ORDER_ID": ["P0"], "NAME": ["P1"]}, require_ner=True)
        rest_p = privacy_mod.restore(m_p, map_p)
        results.append({
            "id": "g3-span-p0p1-short-known",
            "passed": "\x00" not in m_p and rest_p == txt_p,
            "masked": m_p,
        })

        # 6. g3-span-overlapping-address
        txt_addr = "Deliver to 123 Nguyen Hue Street please"
        m_addr, map_addr = privacy_mod.pseudonymize(txt_addr, {"ADDRESS": ["Hue"]}, require_ner=True)
        rest_addr = privacy_mod.restore(m_addr, map_addr)
        results.append({
            "id": "g3-span-overlapping-address",
            "passed": m_addr == "Deliver to [ADDRESS_1] please" and map_addr == {"[ADDRESS_1]": "123 Nguyen Hue Street"} and rest_addr == txt_addr,
            "mapping": map_addr,
        })

    # 7. g3-span-gt999-index
    rest_999 = privacy_mod.restore("Hi [NAME_1000] and [EMAIL_1234]", {"[NAME_1000]": "Alice", "[EMAIL_1234]": "a@b.com"})
    results.append({
        "id": "g3-span-gt999-index",
        "passed": rest_999 == "Hi Alice and a@b.com",
    })

    # 8. g3-span-no-recursive-restore
    rest_rec = privacy_mod.restore("[NAME_1] contacted [EMAIL_1]", {"[NAME_1]": "[EMAIL_1]", "[EMAIL_1]": "secret@example.com"})
    results.append({
        "id": "g3-span-no-recursive-restore",
        "passed": rest_rec == "[EMAIL_1] contacted secret@example.com",
    })

    # 9. g3-span-fake-ner-disclaimer
    spacy_present = importlib.util.find_spec("spacy") is not None
    runtime_fails_closed = False
    try:
        privacy_mod._SPACY_NLP = None
        privacy_mod.pseudonymize("Hi I am Tran Bao", {}, require_ner=True)
    except ValueError:
        runtime_fails_closed = True
    finally:
        privacy_mod._SPACY_NLP = None
    results.append({
        "id": "g3-span-fake-ner-disclaimer",
        "passed": (not spacy_present) and runtime_fails_closed,
        "spacy_installed": spacy_present,
        "runtime_unprovisioned_fails_closed": runtime_fails_closed,
        "note": "Fake NER tests verify boundary enforcement only; live spaCy/en_core_web_sm accuracy requires operational provisioning.",
    })
    return results


def main() -> None:
    t0 = time.perf_counter()
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    matrix_sha = _sha256(MATRIX_PATH)
    cases = matrix["cases"]

    invariants = _check_invariants()
    grp_a = run_group_a_strict_enforcement()
    grp_b = run_group_b_egress_and_forged_jobs()
    grp_c = run_group_c_positive_and_spans()

    all_cases = grp_a + grp_b + grp_c
    failed_cases = [c["id"] for c in all_cases if not c.get("passed")]
    verdict = "PASS" if (invariants["passed"] and not failed_cases and len(all_cases) == len(cases)) else "BLOCK"

    out = {
        "schema_version": "original_fit2_gap3_privacy_c.v1",
        "frozen_matrix_path": str(MATRIX_PATH.relative_to(REPO)).replace("\\", "/"),
        "frozen_matrix_sha256": matrix_sha,
        "verdict": verdict,
        "scope": "GAP3_PRIVACY_CODE_ONLY_NOT_OPERATIONAL_NER_ACCURACY_NOT_WHOLE_PROJECT",
        "total_matrix_cases": len(cases),
        "executed_cases": len(all_cases),
        "passed_cases": len(all_cases) - len(failed_cases),
        "failed_cases": failed_cases,
        "invariants": invariants,
        "group_a_strict_enforcement": grp_a,
        "group_b_egress_and_forged_jobs": grp_b,
        "group_c_positive_and_spans": grp_c,
        "duration_seconds": round(time.perf_counter() - t0, 2),
    }

    report_path = OUT_DIR / "gap3_privacy_verification.json"
    report_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    manifest = {
        "branch": invariants["git_branch"],
        "git_head": invariants["git_head"],
        "command": ".venv/Scripts/python.exe -B artifacts/evaluation/original_fit2_gap3_privacy_c_20261115/evaluate_gap3_privacy_c.py",
        "verdict": verdict,
        "executed_cases": len(all_cases),
        "passed_cases": len(all_cases) - len(failed_cases),
        "failed_cases": failed_cases,
        "duration_seconds": out["duration_seconds"],
        "sha256": {
            "frozen_gap3_case_matrix.json": matrix_sha,
            "evaluate_gap3_privacy_c.py": _sha256(OUT_DIR / "evaluate_gap3_privacy_c.py"),
            "gap3_privacy_verification.json": _sha256(report_path),
        },
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"DONE VERDICT={verdict} EXECUTED={len(all_cases)}/{len(cases)} PASSED={len(all_cases) - len(failed_cases)} FAILED={failed_cases} DUR_S={out['duration_seconds']}")


if __name__ == "__main__":
    main()

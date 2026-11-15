"""Independent grouped disposable-PG integration check: 10-field order_context + console allowed_actions."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.native_runtime import configure_runtime_environment

configure_runtime_environment()

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine, text

from apps.ai_service.engine import Engine
from apps.ai_service.main import SuggestionRequest
from apps.backend.main import create_app as create_backend_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Order, Suggestion, Ticket
from apps.backend.seed import seed
from apps.backend.tickets import privacy as privacy_mod
from apps.backend.tickets.jobs import SuggestionJob, SuggestionWorker
from apps.core_backend.llm.gemini import GeminiDraftClient, ORDER_CONTEXT_ALLOWED_FIELDS
from apps.core_backend.retrieval.adapter import RetrievalAdapter


def run_check() -> dict:
    local = json.loads((REPO_ROOT / ".local/application.json").read_text(encoding="utf-8-sig"))
    app_passwords = local["passwords"]
    base_url = local["database_url_owner"]
    schema = f"c_grouped_verify_{uuid.uuid4().hex[:10]}"

    root_engine = create_engine(base_url, hide_parameters=True)
    with root_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))

    schema_engine = create_engine(
        base_url,
        connect_args={"options": f"-csearch_path={schema}"},
        hide_parameters=True,
    )
    database = Database(schema_engine)
    database.create_schema()
    seed(database, app_passwords)

    try:
        with database.transaction() as session:
            session.add(
                Order(
                    order_id="ORD-C9001",
                    customer_id="demo-customer",
                    payload={
                        "order_id": "ORD-C9001",
                        "order_status": "shipped",
                        "placed_at": "2026-10-01T07:00:00Z",
                        "order_total": {"amount_minor": 350000, "currency": "vnd"},
                        "shipping_cost": {"amount_minor": 20000, "currency": "vnd"},
                        "shipment": {
                            "shipment_status": "delayed",
                            "tracking_code": "TRK-GROUPED-99",
                            "carrier": "GHN",
                            "estimated_delivery_at": "2026-10-05T10:00:00Z",
                            "delivered_at": "2026-10-06T14:30:00Z",
                            "timeline": [],
                        },
                        "refund": {
                            "refund_status": "requested",
                            "refund_amount": {"amount_minor": 150000, "currency": "vnd"},
                            "refund_requested_at": "2026-10-07T09:00:00Z",
                        },
                        "customer_name": "Nguyen Van A",
                        "phone": "0901234567",
                    },
                )
            )

        observed_ai_requests: list[dict] = []

        def fake_gemini_handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            wire = json.loads(body["contents"][0]["parts"][0]["text"])
            order_sid = next((s["source_id"] for s in wire["sources"] if s.get("source_type") == "order_facts"), "S2")
            raw = {
                "answerable": True,
                "answer": f"Your order placed on 2026-10-01 had delivery 2026-10-06 and refund requested 2026-10-07 [{order_sid}].",
                "citations": [order_sid],
                "is_clarification": False,
            }
            return httpx.Response(
                200,
                json={
                    "modelVersion": "gemini-2.5-flash",
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(raw)}]}}],
                    "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70},
                },
            )

        http_llm = httpx.Client(transport=httpx.MockTransport(fake_gemini_handler), trust_env=False)
        fake_llm = GeminiDraftClient(api_key="fake-test-key", model="gemini-2.5-flash", http_client=http_llm)
        release = json.loads((REPO_ROOT / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
        allowed_docs = {(d["document_id"], d["version"]) for d in release["documents"]}
        retrieval = RetrievalAdapter(allowed_document_versions=allowed_docs)
        policy = json.loads((REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v2.json").read_text(encoding="utf-8"))
        mock_model = SimpleNamespace(
            predict=lambda _msg: {
                "intent": "return_policy",
                "confidence": 0.96,
                "margin": 0.80,
                "top_k": [{"intent": "return_policy", "probability": 0.96}, {"intent": "track_order", "probability": 0.04}],
                "score_kind": "calibrated_probability",
                "model_mode": "trained",
                "verified": True,
            }
        )
        ai_engine = Engine(mock_model, retrieval, fake_llm, {"release_id": release.get("release_id", "c-grouped-rel"), "model_version": "fit2-supcon-energy-boundary-v1"}, policy)

        def mock_ai_gateway(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            observed_ai_requests.append({"path": request.url.path, "payload": body})
            parsed = SuggestionRequest(**body)
            if request.url.path.endswith("/v1/analyses"):
                return httpx.Response(200, json=ai_engine.analyse(parsed.model_dump()))
            return httpx.Response(200, json=ai_engine.draft(parsed.model_dump()))

        settings = Settings(
            database_url_app=f"{base_url}?options=-csearch_path%3D{schema}",
            database_url_owner=base_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
            ai_service_base_url="http://mock-ai.local:8002",
        )
        backend_app = create_backend_app(settings=settings, database=database, start_worker=False)

        worker_http = httpx.Client(transport=httpx.MockTransport(mock_ai_gateway), trust_env=False)
        try:
            cust = TestClient(backend_app)
            assert cust.post("/v1/sessions", json={"login_name": "customer-1", "password": app_passwords["customer"]}, headers={"origin": "http://testserver"}).status_code == 201
            privacy_mod._SPACY_NLP = None

            create_res = cust.post(
                "/v1/shop/tickets",
                json={
                    "order_id": "ORD-C9001",
                    "message": "What is your return policy and when was my order ORD-C9001 delivered?",
                },
                headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())},
            )
            assert create_res.status_code == 201, create_res.text
            ticket_id = create_res.json()["ticket_id"]

            create_auth = cust.post(
                "/v1/shop/tickets",
                json={
                    "order_id": "ORD-C9001",
                    "message": "Please approve a refund exception for my order ORD-C9001 immediately.",
                },
                headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())},
            )
            assert create_auth.status_code == 201, create_auth.text
            auth_ticket_id = create_auth.json()["ticket_id"]

            with database.transaction() as session:
                t = session.get(Ticket, ticket_id)
                job = session.get(SuggestionJob, t.current_suggestion_id)
                assert job is not None
                sid = job.suggestion_id
                tok = str(uuid.uuid4())
                job.lease_token = tok
                req_pl = dict(session.get(Suggestion, sid).request_payload)

            SuggestionWorker(database, settings, http_client=worker_http).process(sid, tok, req_pl)

            with database.transaction() as session:
                t_auth = session.get(Ticket, auth_ticket_id)
                job_auth = session.get(SuggestionJob, t_auth.current_suggestion_id)
                assert job_auth is not None
                sid_auth = job_auth.suggestion_id
                tok_auth = str(uuid.uuid4())
                job_auth.lease_token = tok_auth
                req_pl_auth = dict(session.get(Suggestion, sid_auth).request_payload)

            SuggestionWorker(database, settings, http_client=worker_http).process(sid_auth, tok_auth, req_pl_auth)
        finally:
            worker_http.close()
            fake_llm.close()

        wire_drafts = [item["payload"] for item in observed_ai_requests if item["path"].endswith("/v1/drafts")]
        assert len(wire_drafts) == 1, f"observed={observed_ai_requests}"
        wire_ctx = wire_drafts[0]["order_context"]
        assert list(wire_ctx.keys()) == list(ORDER_CONTEXT_ALLOWED_FIELDS)
        assert wire_ctx["refund_requested_at"] == "2026-10-07T09:00:00Z"
        assert "TRK-GROUPED-99" not in json.dumps(wire_drafts[0])

        staff = TestClient(backend_app)
        assert staff.post("/v1/sessions", json={"login_name": "staff-1", "password": app_passwords["staff"]}, headers={"origin": "http://testserver"}).status_code == 201
        staff_normal = staff.get(f"/v1/console/tickets/{ticket_id}").json()
        assert staff_normal["suggestion"]["draft_status"] == "draft_ready"
        assert len(staff_normal["suggestion"]["draft"]["citations"]) == 1
        assert staff_normal["suggestion"]["draft"]["citations"][0]["fields"] == list(ORDER_CONTEXT_ALLOWED_FIELDS)
        assert "send_reply" in staff_normal["allowed_actions"]

        staff_ws = staff.get(f"/v1/console/tickets/{auth_ticket_id}").json()
        assert staff_ws["is_authority_required"] is True
        assert "send_reply" not in staff_ws["allowed_actions"]
        assert "submit_reply_proposal" in staff_ws["allowed_actions"]

        forbid = staff.post(
            f"/v1/console/tickets/{auth_ticket_id}/replies",
            json={"body": "Direct attempt", "basis": "no_ai_draft", "suggestion_id": staff_ws["suggestion"]["suggestion_id"], "acknowledged_warning_ids": []},
            headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert forbid.status_code == 403, forbid.text

        prop_res = staff.post(
            f"/v1/console/tickets/{auth_ticket_id}/reply-proposals",
            json={"body": "Proposed exception reply for admin approval.", "basis": "no_ai_draft", "suggestion_id": staff_ws["suggestion"]["suggestion_id"], "acknowledged_warning_ids": []},
            headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert prop_res.status_code == 201, prop_res.text
        staff_after = staff.get(f"/v1/console/tickets/{auth_ticket_id}").json()
        assert staff_after["status"] == "awaiting_approval"
        assert staff_after["allowed_actions"] == []

        admin = TestClient(backend_app)
        assert admin.post("/v1/sessions", json={"login_name": "admin-1", "password": app_passwords["admin"]}, headers={"origin": "http://testserver"}).status_code == 201
        admin_ws = admin.get(f"/v1/console/tickets/{auth_ticket_id}").json()
        assert "send_reply" in admin_ws["allowed_actions"]
        send_res = admin.post(
            f"/v1/console/tickets/{auth_ticket_id}/replies",
            json={"body": admin_ws["proposal"]["body"], "basis": "reply_proposal", "proposal_id": admin_ws["proposal"]["proposal_id"], "acknowledged_warning_ids": []},
            headers={"origin": "http://testserver", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert send_res.status_code == 201, send_res.text
        final_ws = admin.get(f"/v1/console/tickets/{auth_ticket_id}").json()
        assert final_ws["status"] == "closed"
        assert final_ws["allowed_actions"] == []

        return {
            "verdict": "PASS",
            "schema": schema,
            "ticket_id_10f": ticket_id,
            "ticket_id_auth": auth_ticket_id,
            "wire_order_context_keys": list(wire_ctx.keys()),
            "hydrated_citation_fields": staff_normal["suggestion"]["draft"]["citations"][0]["fields"],
            "staff_allowed_before_proposal": staff_ws["allowed_actions"],
            "staff_direct_send_status": forbid.status_code,
            "staff_allowed_own_proposal": staff_after["allowed_actions"],
            "admin_allowed_before_approval": admin_ws["allowed_actions"],
            "final_status_and_allowed": {"status": final_ws["status"], "allowed_actions": final_ws["allowed_actions"]},
        }
    finally:
        schema_engine.dispose()
        with root_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        root_engine.dispose()


if __name__ == "__main__":
    result = run_check()
    out_path = REPO_ROOT / "artifacts/browser/console_send_permission_c_20261115/grouped_disposable_e2e_c.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))

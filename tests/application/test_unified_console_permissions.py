"""Permission matrix and safety tests for the unified staff + admin console."""

from datetime import datetime, timedelta, timezone
import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Account, Ticket
from apps.backend.seed import seed


@pytest.fixture(scope="module")
def app_ctx():
    secrets_path = Path(os.environ.get("SUPPORTIQ_APPLICATION_SECRETS", ".local/application.json"))
    if not secrets_path.exists():
        pytest.skip("Run scripts/start-app.ps1 -SetupOnly to prepare native PostgreSQL")
    local = json.loads(secrets_path.read_text())
    owner_url = local["database_url_owner"]
    schema = "test_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = None
    try:
        engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
        database = Database(engine)
        database.create_schema()
        passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
        seed(database, passwords)
        settings = Settings(
            database_url_app=owner_url,
            database_url_owner=owner_url,
            allowed_origins=["http://testserver"],
            session_cookie_secure=False,
        )
        app = create_app(settings=settings, database=database, start_worker=False)
        yield app, passwords, database
    finally:
        if engine is not None:
            engine.dispose()
        with root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root.dispose()


def _login(app_ctx, role="customer", name=None):
    app, passwords, _ = app_ctx
    client = TestClient(app, headers={"Origin": "http://testserver"})
    res = client.post("/v1/sessions", json={"login_name": name or f"{role}-1", "password": passwords[role]})
    assert res.status_code == 201, res.text
    return client


def _post(client, path, body):
    return client.post(path, json=body, headers={"Idempotency-Key": str(uuid.uuid4())})


def _create_ticket(customer, message="Where is my order?"):
    res = _post(customer, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": message})
    assert res.status_code == 201, res.text
    return res.json()["ticket_id"]


def test_admin_unified_console_approval_escalation_and_admin_capabilities(app_ctx):
    customer = _login(app_ctx, "customer")
    staff = _login(app_ctx, "staff")
    admin = _login(app_ctx, "admin")

    # 1. Admin opens and replies directly to a routine ticket from /v1/console/tickets
    routine_id = _create_ticket(customer, "Checking delivery status for my package.")
    for status in ("open", "awaiting_approval", "escalated", "closed"):
        assert admin.get(f"/v1/console/tickets?status={status}").status_code == 200

    ws = admin.get(f"/v1/console/tickets/{routine_id}")
    assert ws.status_code == 200
    assert "send_reply" in ws.json()["allowed_actions"]
    assert "escalate" in ws.json()["allowed_actions"]
    assert "submit_reply_proposal" not in ws.json()["allowed_actions"]

    assert _post(admin, f"/v1/console/tickets/{routine_id}/views", {}).status_code == 204
    sent = _post(admin, f"/v1/console/tickets/{routine_id}/replies", {"basis": "no_ai_draft", "body": "Your order is on track."})
    assert sent.status_code == 201, sent.text

    # 2. Staff submits proposal on authority ticket; admin approves & sends it
    auth_id = _create_ticket(customer, "I am requesting a chargeback for this unauthorized transaction.")
    prop = _post(staff, f"/v1/console/tickets/{auth_id}/reply-proposals", {"basis": "no_ai_draft", "body": "We approved the refund request."})
    assert prop.status_code == 201, prop.text
    proposal_id = prop.json()["proposal_id"]

    awaiting = admin.get("/v1/console/tickets?status=awaiting_approval").json()["items"]
    assert any(item["ticket_id"] == auth_id for item in awaiting)
    auth_ws = admin.get(f"/v1/console/tickets/{auth_id}").json()
    assert auth_ws["allowed_actions"] == ["send_reply"]
    approved = _post(admin, f"/v1/console/tickets/{auth_id}/replies", {
        "basis": "reply_proposal",
        "proposal_id": proposal_id,
        "body": "We approved the refund request.",
    })
    assert approved.status_code == 201, approved.text

    # 3. Admin can escalate an open ticket and later reply on the escalated ticket
    esc_id = _create_ticket(customer, "Need supervisor review on invoice.")
    esc = _post(admin, f"/v1/console/tickets/{esc_id}/escalations", {"staff_reason_codes": ["case_exception"]})
    assert esc.status_code == 201, esc.text
    assert _post(admin, f"/v1/console/tickets/{esc_id}/replies", {"basis": "no_ai_draft", "body": "Resolved after review."}).status_code == 201

    # 4. Admin can access reports, accounts, versions, and observability
    end_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_at = end_at - timedelta(days=7)
    assert admin.get("/v1/console/reports", params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()}).status_code == 200
    assert admin.get("/v1/admin/accounts").status_code == 200
    assert admin.get("/v1/admin/versions").status_code == 200
    assert admin.get("/v1/admin/observability/metrics").status_code == 200


def test_staff_and_customer_restrictions_preserved(app_ctx):
    customer = _login(app_ctx, "customer")
    staff = _login(app_ctx, "staff")

    # Staff cannot list non-open tickets, reports, accounts, versions, or observability
    for status in ("awaiting_approval", "escalated", "closed"):
        assert staff.get(f"/v1/console/tickets?status={status}").status_code == 403
    end_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_at = end_at - timedelta(days=7)
    assert staff.get("/v1/console/reports", params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()}).status_code == 403
    assert staff.get("/v1/admin/accounts").status_code == 403
    assert _post(staff, "/v1/admin/accounts/acc-staff/role-changes", {"role": "manager"}).status_code == 403
    assert _post(staff, "/v1/admin/accounts/acc-staff/status-changes", {"is_active": False}).status_code == 403
    assert staff.get("/v1/admin/versions").status_code == 403
    assert staff.get("/v1/admin/observability/metrics").status_code == 403
    assert staff.get("/v1/admin/observability/errors").status_code == 403

    # Staff cannot directly reply to authority-required tickets
    auth_id = _create_ticket(customer, "I am requesting a chargeback for this unauthorized transaction.")
    direct = _post(staff, f"/v1/console/tickets/{auth_id}/replies", {"basis": "no_ai_draft", "body": "Unauthorized refund"})
    assert direct.status_code == 403
    assert direct.json()["type"] == "urn:supportiq:problem:authority-required"

    # Customer cannot access any console or admin route
    assert customer.get("/v1/console/tickets").status_code == 403
    assert customer.get("/v1/console/reports", params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()}).status_code == 403
    assert customer.get("/v1/admin/accounts").status_code == 403
    assert customer.get("/v1/admin/versions").status_code == 403


def test_legacy_manager_compat_without_admin_endpoints(app_ctx):
    customer = _login(app_ctx, "customer")
    manager = _login(app_ctx, "manager")
    end_at = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_at = end_at - timedelta(days=7)

    assert manager.get("/v1/console/tickets?status=escalated").status_code == 200
    assert manager.get("/v1/console/reports", params={"start_at": start_at.isoformat(), "end_at": end_at.isoformat()}).status_code == 200
    assert manager.get("/v1/admin/accounts").status_code == 403
    assert manager.get("/v1/admin/versions").status_code == 403

    auth_id = _create_ticket(customer, "This is an unauthorized transaction.")
    assert _post(manager, f"/v1/console/tickets/{auth_id}/replies", {"basis": "no_ai_draft", "body": "Approved."}).status_code == 201


def test_self_approval_and_self_account_modification_blocked(app_ctx):
    _, _, database = app_ctx
    customer = _login(app_ctx, "customer")
    admin = _login(app_ctx, "admin")

    tid = _create_ticket(customer, "Need chargeback review for unauthorized transaction.")
    with database.transaction() as session:
        admin_acct = session.query(Account).filter_by(login_name="admin-1").one()
        tck = session.get(Ticket, tid)
        proposal_id = str(uuid.uuid4())
        tck.status = "awaiting_approval"
        tck.proposal = {
            "proposal_id": proposal_id,
            "basis": "no_ai_draft",
            "body": "Self proposed reply.",
            "by": admin_acct.display_name,
            "actor_account_id": admin_acct.account_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    res = _post(admin, f"/v1/console/tickets/{tid}/replies", {
        "basis": "reply_proposal",
        "proposal_id": proposal_id,
        "body": "Self proposed reply.",
    })
    assert res.status_code == 403
    assert res.json()["type"] == "urn:supportiq:problem:self-approval-forbidden"

    accounts = admin.get("/v1/admin/accounts").json()["items"]
    admin_row = next(item for item in accounts if item["role"] == "admin")
    staff_row = next(item for item in accounts if item["role"] == "staff")
    assert _post(admin, f"/v1/admin/accounts/{admin_row['account_id']}/status-changes", {"is_active": False}).status_code == 422
    assert _post(admin, f"/v1/admin/accounts/{staff_row['account_id']}/role-changes", {"role": "admin"}).status_code == 422

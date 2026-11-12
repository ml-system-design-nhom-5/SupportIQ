"""Application guardrails exercised against a real, isolated PostgreSQL database."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def application():
    from apps.backend.main import create_app
    from apps.backend.platform.config import Settings
    from apps.backend.platform.database import Database
    from apps.backend.seed import seed

    from sqlalchemy import create_engine, text

    secrets_path = Path(".local/application.json")
    if not secrets_path.exists():
        pytest.skip("Run scripts/start-app.ps1 -SetupOnly to prepare native PostgreSQL")
    local = json.loads(secrets_path.read_text())
    owner_url = local["database_url_owner"]
    schema = "test_" + uuid.uuid4().hex
    root = create_engine(owner_url)
    with root.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(owner_url, connect_args={"options": f"-csearch_path={schema}"})
    database = Database(engine)
    database.create_schema()
    passwords = {role: uuid.uuid4().hex for role in ("customer", "staff", "manager", "admin")}
    seed(database, passwords)
    settings = Settings(database_url_app=owner_url, database_url_owner=owner_url,
                        allowed_origins=["http://testserver"], session_cookie_secure=False)
    app = create_app(settings=settings, database=database, start_worker=False)
    yield app, passwords, database
    engine.dispose()
    with root.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    root.dispose()


def login(application, role="customer", name=None):
    app, passwords, _ = application
    client = TestClient(app, headers={"Origin": "http://testserver"})
    response = client.post("/v1/sessions", json={"login_name": name or role + "-1", "password": passwords[role]})
    assert response.status_code == 201, response.text
    return client


def write(client, path, body, key=None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def ticket(client, message="Where is my order?"):
    response = write(client, "/v1/shop/tickets", {"order_id": "ORD-1001", "message": message})
    assert response.status_code == 201, response.text
    return response.json()["ticket_id"]


def test_authentication_origin_and_roles(application):
    app, _, _ = application
    with TestClient(app) as anonymous:
        assert anonymous.get("/v1/shop/orders").status_code == 401
        assert anonymous.post("/v1/sessions", json={"login_name": "x", "password": "x"}).status_code == 403
    for role, own, forbidden in [
        ("customer", "/v1/shop/orders", "/v1/console/tickets"),
        ("staff", "/v1/console/tickets", "/v1/admin/accounts"),
        ("manager", "/v1/console/tickets", "/v1/shop/orders"),
        ("admin", "/v1/admin/accounts", "/v1/console/tickets"),
    ]:
        client = login(application, role)
        assert client.get(own).status_code == 200
        assert client.get(forbidden).status_code == 403


def test_commerce_uses_source_and_enforces_ownership(application):
    customer = login(application)
    order = customer.get("/v1/shop/orders/ORD-1001").json()
    assert order["order_total"] == {"amount_minor": 1402000, "currency": "VND"}
    assert order["order_status"] == "shipped"
    assert order["lines"][0]["product_name"] == "Premium Silk Cotton Bed Sheet Set"
    assert "shipping_address" not in order
    assert customer.get("/v1/shop/orders/ORD-1002").status_code == 404
    assert customer.get("/v1/shop/tickets?order_id=ORD-1002").status_code == 404
    assert write(customer, "/v1/shop/tickets", {"order_id": "ORD-1002", "message": "hello"}).status_code == 404


def test_ticket_idempotency_and_manual_reply_round_trip(application):
    customer = login(application)
    key = str(uuid.uuid4())
    payload = {"order_id": "ORD-1001", "message": "<script>unsafe</script> Where is my parcel?"}
    first = write(customer, "/v1/shop/tickets", payload, key)
    assert first.status_code == 201
    assert write(customer, "/v1/shop/tickets", payload, key).json() == first.json()
    assert write(customer, "/v1/shop/tickets", {**payload, "message": "different"}, key).status_code == 409
    ticket_id = first.json()["ticket_id"]
    assert not {"suggestion", "allowed_actions", "proposal", "status"} & first.json().keys()
    staff = login(application, "staff")
    workspace = staff.get(f"/v1/console/tickets/{ticket_id}").json()
    assert workspace["message"]["body"] == payload["message"]
    response = write(staff, f"/v1/console/tickets/{ticket_id}/replies", {"basis": "no_ai_draft", "body": "Your parcel is in transit."})
    assert response.status_code == 201, response.text
    received = customer.get(f"/v1/shop/tickets/{ticket_id}").json()
    assert received["customer_status"] == "replied"
    assert received["reply"]["body"] == "Your parcel is in transit."
    assert write(staff, f"/v1/console/tickets/{ticket_id}/replies", {"basis": "no_ai_draft", "body": "Again"}).status_code == 409


def test_proposal_requires_manager_and_placeholders_are_blocked(application):
    customer, staff = login(application), login(application, "staff")
    ticket_id = ticket(customer)
    path = f"/v1/console/tickets/{ticket_id}"
    assert write(staff, path + "/replies", {"basis": "no_ai_draft", "body": "Hello [NAME_1]"}).status_code == 422
    proposal = write(staff, path + "/reply-proposals", {"basis": "no_ai_draft", "body": "We will review your request."})
    assert proposal.status_code == 201
    assert staff.get(path).json()["allowed_actions"] == []
    assert write(staff, path + "/replies", {"basis": "no_ai_draft", "body": "No"}).status_code == 403
    manager = login(application, "manager")
    assert write(manager, path + "/replies", {"basis": "reply_proposal", "proposal_id": proposal.json()["proposal_id"], "body": "We will review your request."}).status_code == 201


def test_escalation_needs_reason_and_is_read_only_for_staff(application):
    customer, staff = login(application), login(application, "staff")
    ticket_id = ticket(customer)
    path = f"/v1/console/tickets/{ticket_id}"
    assert write(staff, path + "/escalations", {"staff_reason_codes": []}).status_code == 422
    assert write(staff, path + "/escalations", {"staff_reason_codes": ["other"]}).status_code == 422
    assert write(staff, path + "/escalations", {"staff_reason_codes": ["missing_case_info"]}).status_code == 201
    assert staff.get(path).json()["allowed_actions"] == []
    assert staff.get("/v1/console/tickets?status=escalated").status_code == 403


def test_admin_protects_customers_last_manager_and_revokes_sessions(application):
    admin, staff = login(application, "admin"), login(application, "staff")
    accounts = admin.get("/v1/admin/accounts").json()["items"]
    assert all(account["role"] != "customer" for account in accounts)
    target = next(account for account in accounts if account["role"] == "staff")
    manager = next(account for account in accounts if account["role"] == "manager")
    assert write(admin, f'/v1/admin/accounts/{manager["account_id"]}/status-changes', {"is_active": False}).status_code == 422
    assert write(admin, f'/v1/admin/accounts/{target["account_id"]}/role-changes', {"role": "manager"}).status_code == 201
    assert staff.get("/v1/sessions/current").status_code == 401
    assert write(admin, "/v1/admin/accounts/does-not-exist/role-changes", {"role": "staff"}).status_code == 404
    assert write(admin, f'/v1/admin/accounts/{target["account_id"]}/role-changes', {"role": "staff"}).status_code == 201


def current_suggestion(application, ticket_id, **overrides):
    from apps.backend.platform.models import Suggestion, Ticket
    _, _, database = application
    with database.transaction() as session:
        record = session.get(Ticket, ticket_id)
        suggestion = session.get(Suggestion, record.current_suggestion_id)
        suggestion.payload = {**suggestion.payload,
                              "analysis_status": "ready", "draft_status": "draft_ready",
                              "analysis": {"intent": {"label": "track_order", "probability": .9, "confidence_band": "high"}, "alternatives": [], "documents": [], "routing": {"recommendation": "draft", "reason_codes": []}},
                              "draft": {"text": "The delivery policy applies.", "segments": [], "citations": []}, **overrides}
        return suggestion.suggestion_id


def test_ready_draft_requires_warnings_and_current_suggestion(application):
    staff = login(application, "staff")
    identifier = ticket(login(application))
    suggestion_id = current_suggestion(application, identifier, warnings=[{"warning_id": "review-1", "reason_code": "source_review_overdue"}])
    path = f"/v1/console/tickets/{identifier}/replies"
    payload = {"basis": "ai_draft", "body": "The delivery policy applies.", "suggestion_id": suggestion_id, "acknowledged_warning_ids": []}
    assert write(staff, path, payload).status_code == 422
    assert write(staff, path, {"basis": "no_ai_draft", "body": "Bypass"}).status_code == 422
    assert write(staff, path, {**payload, "suggestion_id": "old-suggestion"}).status_code == 409
    assert write(staff, path, {**payload, "acknowledged_warning_ids": ["review-1"]}).status_code == 201


def test_authority_is_sticky_after_intent_correction(application):
    from sqlalchemy.exc import DBAPIError
    from apps.backend.platform.models import Ticket

    _, _, database = application
    staff = login(application, "staff")
    identifier = ticket(login(application))
    current_suggestion(application, identifier)
    with database.transaction() as session:
        session.get(Ticket, identifier).is_authority_required = True
    path = f"/v1/console/tickets/{identifier}"
    assert write(staff, path + "/suggestions", {"intent_override": "track_order"}).status_code == 202
    assert staff.get(path).json()["is_authority_required"] is True
    assert write(staff, path + "/replies", {"basis": "no_ai_draft", "body": "Test"}).status_code == 403
    with pytest.raises(DBAPIError), database.transaction() as session:
        session.get(Ticket, identifier).is_authority_required = False


def test_pending_draft_blocks_send_and_correction_cancels_it(application):
    from apps.backend.platform.models import Suggestion
    _, _, database = application
    staff = login(application, "staff")
    identifier = ticket(login(application))
    suggestion_id = current_suggestion(application, identifier, draft_status="pending")
    path = f"/v1/console/tickets/{identifier}"
    assert write(staff, path + "/replies", {"basis": "no_ai_draft", "body": "Test"}).status_code == 409
    assert write(staff, path + "/suggestions", {"intent_override": "delivery_time"}).status_code == 202
    with database.transaction() as session:
        assert session.get(Suggestion, suggestion_id).payload["draft_status"] == "cancelled"


def test_concurrent_sends_close_ticket_once(application):
    from concurrent.futures import ThreadPoolExecutor
    identifier = ticket(login(application))
    first, second = login(application, "staff"), login(application, "staff")
    path = f"/v1/console/tickets/{identifier}/replies"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: write(client, path, {"basis": "no_ai_draft", "body": "One reply"}).status_code, [first, second]))
    assert sorted(results) == [201, 409]


def test_concurrent_repeated_creation_returns_one_ticket(application):
    from concurrent.futures import ThreadPoolExecutor
    first, second = login(application), login(application)
    payload = {"order_id": "ORD-1001", "message": "Concurrent request"}
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda client: write(client, "/v1/shop/tickets", payload, key), [first, second]))
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()


def test_audit_and_customer_messages_are_immutable(application):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    _, _, database = application
    for query in ("UPDATE audit_log_entries SET event_type='tampered'", "DELETE FROM audit_log_entries", "UPDATE customer_messages SET body='tampered'"):
        with pytest.raises(DBAPIError), database.transaction() as session:
            session.execute(text(query))


def test_reports_are_manager_only_and_validate_period(application):
    query = "/v1/console/reports?start_at=2026-01-01T00:00:00Z&end_at=2027-01-01T00:00:00Z"
    assert login(application, "staff").get(query).status_code == 403
    manager = login(application, "manager")
    response = manager.get(query)
    assert response.status_code == 200
    assert response.json()["draft_decisions"]["approve"]["count"] >= 1
    assert manager.get("/v1/console/reports?start_at=2027-01-01T00:00:00Z&end_at=2026-01-01T00:00:00Z").status_code == 422


def test_pseudonymization_preserves_literals_and_masks_source_ids():
    from apps.backend.tickets.privacy import pseudonymize, restore

    original = "Bui Thi An, ORD-1001, GIAO89254563, x@example.com and [NAME_1]"
    result, mapping = pseudonymize(original, {"NAME": ["Bui Thi An"], "ORDER_ID": ["ORD-1001"], "TRACKING_ID": ["GIAO89254563"]})
    assert "ORD-1001" not in result and "Bui Thi An" not in result
    assert "GIAO89254563" not in result and "x@example.com" not in result
    assert restore(result, mapping) == original


def test_general_support_without_order(application):
    customer=login(application)
    response=write(customer, '/v1/shop/tickets', {'message':'What is your return policy?'})
    assert response.status_code == 201, response.text
    identifier=response.json()['ticket_id']
    assert response.json()['order_id'] is None
    assert login(application,'customer',name='customer-2').get('/v1/shop/tickets/'+identifier).status_code == 404
    workspace=login(application,'staff').get('/v1/console/tickets/'+identifier)
    assert workspace.status_code == 200
    assert workspace.json()['order'] is None


def test_profile_edit_is_self_only(application):
    customer=login(application)
    response=customer.patch('/v1/profile',json={'display_name':'Updated Customer'})
    assert response.status_code==200
    assert customer.get('/v1/sessions/current').json()['display_name']=='Updated Customer'
    assert customer.patch('/v1/profile',json={'display_name':'   '}).status_code==422
    assert customer.patch('/v1/profile',json={'display_name':'Test','role':'admin'}).status_code==422


def test_profile_fields_persist_and_remain_private(application):
    from apps.backend.platform.models import Account
    from sqlalchemy import select
    client=login(application)
    fields={'display_name':'Profile Example','email':'profile@example.com','phone':'+84 901 234 567','address':'12 Sample Street','avatar_data_url':None}
    response=client.patch('/v1/profile',json=fields)
    assert response.status_code==200,response.text
    assert all(response.json()[key]==value for key,value in fields.items())
    assert client.get('/v1/profile').json()['email']=='profile@example.com'
    with application[2].transaction() as session:
        account=session.scalar(select(Account).where(Account.login_name=='customer-1'))
        assert account.email=='profile@example.com' and account.address=='12 Sample Street'
    assert login(application,'customer',name='customer-2').get('/v1/profile').json()['email']!='profile@example.com'
    assert client.patch('/v1/profile',json={'display_name':'Test','email':'bad-email'}).status_code==422
    assert client.patch('/v1/profile',json={'display_name':'Test','avatar_data_url':'data:image/svg+xml;base64,PHN2Zz4='}).status_code==422


def test_buy_creates_owned_order_once(application):
    customer=login(application)
    payload={'product_id':'PROD-1'}
    assert customer.patch('/v1/profile',json={'display_name':'Buyer','phone':'','address':''}).status_code==200
    assert write(customer,'/v1/shop/orders',payload).status_code==422
    assert customer.patch('/v1/profile',json={'display_name':'Buyer','phone':'0901234567','address':'12 Example Street'}).status_code==200
    key=str(uuid.uuid4())
    first=write(customer,'/v1/shop/orders',payload,key)
    assert first.status_code==201,first.text
    order=first.json()
    assert order['lines'][0]['product_id']=='PROD-1' and order['order_status']=='placed'
    assert write(customer,'/v1/shop/orders',payload,key).json()==order
    assert customer.get('/v1/shop/orders/'+order['order_id']).status_code==200
    assert login(application,'customer',name='customer-2').get('/v1/shop/orders/'+order['order_id']).status_code==404
    assert write(customer,'/v1/shop/orders',{'product_id':'nonexistent'}).status_code==404


def test_customer_can_cancel_own_placed_order(application):
    customer=login(application)
    customer.patch('/v1/profile',json={'display_name':'Buyer','phone':'0901234567','address':'12 Example Street'})
    order=write(customer,'/v1/shop/orders',{'product_id':'PROD-1'}).json()
    path='/v1/shop/orders/'+order['order_id']+'/cancellations'
    assert write(login(application,'customer',name='customer-2'),path,{}).status_code==404
    response=write(customer,path,{})
    assert response.status_code==201 and response.json()['order_status']=='cancelled'
    assert customer.get('/v1/shop/orders/'+order['order_id']).json()['order_status']=='cancelled'
    assert write(customer,path,{}).status_code==409


def test_request_attaches_only_a_uniquely_referenced_owned_order(application):
    customer=login(application)
    first=write(customer,'/v1/shop/tickets',{'message':'Where is ORD-1001?'}).json()
    assert first['order_id']=='ORD-1001'
    other=write(customer,'/v1/shop/tickets',{'message':'Where is ORD-1002?'}).json()
    assert other['order_id'] is None

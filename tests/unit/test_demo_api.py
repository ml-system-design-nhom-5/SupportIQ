import pytest
from fastapi.testclient import TestClient

from apps.demo.app import create_app
from apps.demo.store import DemoStore
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.intent.schemas import IntentPrediction

class DummyIntentClient:
    def __init__(self, intent="return_policy", confidence=0.90, margin=0.5):
        self.pred = IntentPrediction(intent=intent, confidence=confidence, margin=margin, model_version="v2.0.0")

    def classify_intent(self, text: str, request_id: str = None) -> IntentPrediction:
        return self.pred

class DummyRetrievalAdapter:
    def retrieve(self, query: str, intent: str, role: str = "agent", current_time=None):
        if intent == "return_policy":
            return {
                "status": "success",
                "evidence": [{
                    "doc_id": "KB-RET-001",
                    "title": "Standard Return Policy",
                    "version": "1.0",
                    "category": "returns",
                    "score": 0.88,
                    "chunks": [{"text": "Items can be returned within 30 days of purchase in original packaging."}]
                }]
            }
        return {"status": "no_evidence", "evidence": []}

@pytest.fixture
def test_setup(tmp_path):
    demo_db = str(tmp_path / "demo_test.sqlite3")
    orch_db = str(tmp_path / "orch_test.sqlite3")
    p_store = PersistentStore(db_path=orch_db)
    runner = PipelineRunner(
        intent_client=DummyIntentClient(),
        retrieval_adapter=DummyRetrievalAdapter(),
        store=p_store
    )
    app = create_app(db_path=demo_db, runner=runner)
    return {
        "app": app,
        "client": TestClient(app),
        "demo_db": demo_db,
        "orch_db": orch_db,
        "runner": runner
    }

@pytest.fixture
def client(test_setup):
    return test_setup["client"]

# --- Task 1 Tests ---

def test_demo_health(client):
    res = client.get("/api/demo/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["draft_kind"] == "template"

def test_get_profiles(client):
    res = client.get("/api/demo/profiles")
    assert res.status_code == 200
    profiles = res.json()
    assert len(profiles) >= 2
    # Check that raw security scope is not leaked in profile list
    for p in profiles:
        assert "scope" not in p
        assert "verified_scope" not in p
        assert "id" in p
        assert "name" in p

def test_submit_uses_server_context_and_rejects_spoofed_scope(client):
    payload = {
        "submission_id": "11111111-1111-1111-1111-111111111111",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
        # Client attempts to inject unauthorized scope override
        "verified_scope": "admin order:override"
    }
    # Pydantic extra='forbid' strictly rejects unauthorized fields with 422
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 422

def test_unknown_or_foreign_order_rejected(client):
    payload = {
        "submission_id": "22222222-2222-2222-2222-222222222222",
        "profile_id": "demo-customer",
        "text": "Track order ORD-1002",
        "is_personal_lookup": True,
        "order_id": "ORD-1002"  # Belongs to cust-1002, not demo-customer
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "escalate"
    assert "commerce_unauthorized_customer" in data["reason_codes"]

def test_retry_same_submission_reuses_run(client):
    payload = {
        "submission_id": "33333333-3333-3333-3333-333333333333",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res1 = client.post("/api/demo/runs", json=payload)
    assert res1.status_code == 200
    d1 = res1.json()

    res2 = client.post("/api/demo/runs", json=payload)
    assert res2.status_code == 200
    d2 = res2.json()

    assert d1["run_id"] == d2["run_id"]
    assert d2["is_duplicate_run"] is True

def test_same_id_changed_payload_conflicts(client):
    payload1 = {
        "submission_id": "44444444-4444-4444-4444-444444444444",
        "profile_id": "demo-customer",
        "text": "Query 1",
        "is_personal_lookup": False,
    }
    res1 = client.post("/api/demo/runs", json=payload1)
    assert res1.status_code == 200

    payload2 = {
        "submission_id": "44444444-4444-4444-4444-444444444444",
        "profile_id": "demo-customer",
        "text": "Query 2 Changed",
        "is_personal_lookup": False,
    }
    res2 = client.post("/api/demo/runs", json=payload2)
    assert res2.status_code == 409

def test_sources_are_real_and_template_is_labeled(client):
    payload = {
        "submission_id": "55555555-5555-5555-5555-555555555555",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["action"] == "retrieve_draft"
    assert data["draft_kind"] == "template"
    assert "Standard Return Policy" in data["draft_body"]
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    assert src["doc_id"] == "KB-RET-001"
    assert src["title"] == "Standard Return Policy"
    assert src["version"] == "1.0"
    assert "30 days" in src["snippet"]

def test_history_is_session_scoped(test_setup):
    client = test_setup["client"]
    payload = {
        "submission_id": "66666666-6666-6666-6666-666666666666",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200

    hist1 = client.get("/api/demo/history").json()
    assert len(hist1) == 1
    assert hist1[0]["submission_id"] == payload["submission_id"]

    # Different session cookie -> isolated empty history
    client2 = TestClient(test_setup["app"], cookies={"demo_session_id": "isolated-session-999"})
    hist2 = client2.get("/api/demo/history").json()
    assert len(hist2) == 0

def test_mutation_rejects_cross_origin(client):
    payload = {
        "submission_id": "77777777-7777-7777-7777-777777777777",
        "profile_id": "demo-customer",
        "text": "Return policy check",
        "is_personal_lookup": False,
    }
    # Request from foreign origin rejected with 403
    res = client.post("/api/demo/runs", json=payload, headers={"Origin": "https://malicious-attacker.com"})
    assert res.status_code == 403


# --- Task 2 Tests (Feedback & Draft Revision) ---

def test_feedback_hash_mismatch_rejected(client):
    payload = {
        "submission_id": "88888888-8888-8888-8888-888888888888",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()
    run_id = data["run_id"]

    # Attempt to approve with wrong hash
    fb_payload = {
        "action": "approve",
        "draft_hash": "wrong-stale-hash"
    }
    fb_res = client.post(f"/api/demo/runs/{run_id}/feedback", json=fb_payload)
    assert fb_res.status_code == 400
    assert "revision mismatch" in fb_res.json()["detail"].lower()

def test_edit_needs_new_approval(client):
    payload = {
        "submission_id": "99999999-9999-9999-9999-999999999999",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()
    run_id = data["run_id"]
    original_hash = data["draft_hash"]

    # 1. Edit draft
    edit_payload = {
        "action": "edit",
        "draft_hash": original_hash,
        "edited_text": "Updated custom return instructions for customer."
    }
    edit_res = client.post(f"/api/demo/runs/{run_id}/feedback", json=edit_payload)
    assert edit_res.status_code == 200
    new_hash = edit_res.json()["current_draft_hash"]
    assert new_hash != original_hash

    # 2. Old hash can no longer be approved
    old_approve = client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "approve", "draft_hash": original_hash})
    assert old_approve.status_code == 400

    # 3. New hash can be approved
    new_approve = client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "approve", "draft_hash": new_hash})
    assert new_approve.status_code == 200

def test_reject_does_not_send(client):
    payload = {
        "submission_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()
    run_id = data["run_id"]
    original_hash = data["draft_hash"]

    # Reject feedback
    reject_res = client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "reject", "draft_hash": original_hash})
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "recorded"

def test_feedback_persists_after_restart(test_setup):
    client = test_setup["client"]
    demo_db = test_setup["demo_db"]
    payload = {
        "submission_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    run_id = res.json()["run_id"]
    d_hash = res.json()["draft_hash"]

    # Record feedback
    client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "approve", "draft_hash": d_hash})

    # Read directly from store simulating process restart
    store = DemoStore(db_path=demo_db)
    feedbacks = store.get_feedbacks(run_id)
    assert len(feedbacks) == 1
    assert feedbacks[0]["action"] == "approve"
    assert feedbacks[0]["draft_hash"] == d_hash

def test_duplicate_feedback_does_not_duplicate_escalation(test_setup):
    client = test_setup["client"]
    orch_db = test_setup["orch_db"]
    payload = {
        "submission_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    run_id = res.json()["run_id"]
    d_hash = res.json()["draft_hash"]

    # Escalate feedback twice
    res1 = client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "escalate", "draft_hash": d_hash})
    assert res1.status_code == 200
    res2 = client.post(f"/api/demo/runs/{run_id}/feedback", json={"action": "escalate", "draft_hash": d_hash})
    assert res2.status_code == 200

    # Verify escalation queue has only 1 entry for this run_id
    orch_store = PersistentStore(db_path=orch_db)
    with orch_store._connection() as conn:
        rows = conn.execute("SELECT * FROM escalation_queue WHERE run_id = ?", (run_id,)).fetchall()
        assert len(rows) == 1

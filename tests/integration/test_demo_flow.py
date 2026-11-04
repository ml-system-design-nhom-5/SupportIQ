import pytest
from fastapi.testclient import TestClient

from apps.demo.app import create_app
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.intent.schemas import IntentPrediction

class DummyIntentClient:
    def __init__(self, intent="return_policy", confidence=0.92, margin=0.6):
        self.pred = IntentPrediction(intent=intent, confidence=confidence, margin=margin, model_version="v2.0.0")

    def classify_intent(self, text: str, request_id: str = None) -> IntentPrediction:
        return self.pred

@pytest.fixture
def integration_app(tmp_path, fake_llm):
    demo_db = str(tmp_path / "demo_integ.sqlite3")
    orch_db = str(tmp_path / "orch_integ.sqlite3")
    orch_store = PersistentStore(db_path=orch_db)
    
    # Real RetrievalAdapter with default approved KB
    retrieval_adapter = RetrievalAdapter()
    
    runner = PipelineRunner(
        llm_client=fake_llm,
        intent_client=DummyIntentClient(intent="return_policy"),
        retrieval_adapter=retrieval_adapter,
        store=orch_store
    )
    
    app = create_app(db_path=demo_db, runner=runner)
    return {
        "client": TestClient(app),
        "demo_db": demo_db,
        "orch_db": orch_db,
        "runner": runner,
        "store": orch_store
    }

def test_end_to_end_demo_policy_flow(integration_app):
    client = integration_app["client"]

    # 1. Submit return policy inquiry
    payload = {
        "submission_id": "11112222-3333-4444-5555-666677778888",
        "profile_id": "demo-customer",
        "text": "What is the return window and conditions for standard returns?",
        "is_personal_lookup": False,
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["action"] == "retrieve_draft"
    assert data["draft_kind"] == "llm"
    assert "Standard Return Policy" in data["draft_body"]
    assert data["evidence_retrieved"] is True
    assert len(data["sources"]) >= 1

    top_source = data["sources"][0]
    assert "Standard Return Policy" in top_source["title"]
    assert top_source["version"] is not None
    assert "30 days" in top_source["snippet"]

    run_id = data["run_id"]
    draft_hash = data["draft_hash"]

    # 2. Staff approves the initial draft
    approve_res = client.post(
        f"/api/demo/runs/{run_id}/feedback",
        json={"action": "approve", "draft_hash": draft_hash}
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "recorded"

    # 3. Staff provides custom edit
    edit_res = client.post(
        f"/api/demo/runs/{run_id}/feedback",
        json={
            "action": "edit",
            "draft_hash": draft_hash,
            "edited_text": "Thank you for reaching out. Standard returns are accepted within 30 days."
        }
    )
    assert edit_res.status_code == 200
    new_draft_hash = edit_res.json()["current_draft_hash"]
    assert new_draft_hash != draft_hash

    # 4. Old draft hash cannot be re-approved; new hash is required
    stale_approve = client.post(
        f"/api/demo/runs/{run_id}/feedback",
        json={"action": "approve", "draft_hash": draft_hash}
    )
    assert stale_approve.status_code == 400

    new_approve = client.post(
        f"/api/demo/runs/{run_id}/feedback",
        json={"action": "approve", "draft_hash": new_draft_hash}
    )
    assert new_approve.status_code == 200

    # 5. Check session history
    hist_res = client.get("/api/demo/history")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 1
    assert history[0]["submission_id"] == payload["submission_id"]
    assert history[0]["result"]["action"] == "retrieve_draft"


def test_end_to_end_unauthorized_order_escalation_flow(integration_app):
    client = integration_app["client"]
    orch_store = integration_app["store"]

    # Customer 'demo-customer' attempts to access ORD-1002 belonging to cust-1002
    payload = {
        "submission_id": "99998888-7777-6666-5555-444433332222",
        "profile_id": "demo-customer",
        "text": "Where is my package for order ORD-1002?",
        "is_personal_lookup": True,
        "order_id": "ORD-1002"
    }
    res = client.post("/api/demo/runs", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["action"] == "escalate"
    assert data["requested_team"] == "order_support"
    assert "commerce_unauthorized_customer" in data["reason_codes"]
    assert data["draft_body"] is None

    # Verify escalation was atomically saved to orchestration escalation_queue
    run_id = data["run_id"]
    with orch_store._connection() as conn:
        row = conn.execute("SELECT * FROM escalation_queue WHERE run_id = ?", (run_id,)).fetchone()
        assert row is not None
        assert row["target_team"] == "order_support"
        assert "commerce_unauthorized_customer" in row["reason_codes"]

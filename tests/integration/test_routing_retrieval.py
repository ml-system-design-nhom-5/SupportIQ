import os
import pytest
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction

class DummyIntentClient:
    def __init__(self, pred: IntentPrediction):
        self.pred = pred

    def classify_intent(self, text: str, request_id: str = None) -> IntentPrediction:
        return self.pred

@pytest.fixture
def test_store(tmp_path):
    db_file = tmp_path / "test_store.sqlite3"
    return PersistentStore(db_path=str(db_file))

def test_missing_slot_clarifies(test_store):
    pred = IntentPrediction(intent="track_order", confidence=0.92, margin=0.5, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(ticket_customer_id="demo-customer", is_personal_lookup=True, extracted_slots={})
    res = runner.run("Where is my package?", ctx)
    assert res["action"] == "clarify"
    assert "missing_order_id" in res["reason_codes"]


def test_policy_query_retrieval_and_drafting(test_store):
    """When policy question has valid evidence, evidence_retrieved is True and draft is populated."""
    pred = IntentPrediction(intent="return_policy", confidence=0.88, margin=0.4, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(ticket_customer_id="demo-customer", is_personal_lookup=False)
    res = runner.run("What is your standard return policy?", ctx)
    assert res["action"] == "retrieve_draft"
    assert res["requested_team"] == "returns_support"
    assert res["evidence_retrieved"] is True
    assert res["draft_body"] is not None
    assert "Standard Return Policy" in res["draft_body"]


def test_34_routes_and_human_agent_escalate_without_llm(test_store):
    pred = IntentPrediction(intent="technical_issue", confidence=0.95, margin=0.7, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(ticket_customer_id="demo-customer")
    res = runner.run("The app crashed", ctx)
    assert res["action"] == "escalate"
    assert res["requested_team"] == "technical_support"
    assert res["llm_called"] is False
    assert res["evidence_retrieved"] is False


def test_unauthorized_order_access_rejected_via_commerce_adapter(test_store):
    """Real order ORD-1002 belongs to cust-1002. Caller demo-customer must be rejected."""
    pred = IntentPrediction(intent="track_order", confidence=0.95, margin=0.5, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(
        ticket_customer_id="demo-customer",
        verified_scope="ticket:read",
        is_personal_lookup=True,
        extracted_slots={"order_id": "ORD-1002"}
    )
    res = runner.run("Track order ORD-1002", ctx)
    assert res["action"] == "escalate"
    assert "commerce_unauthorized_customer" in res["reason_codes"]


def test_authorized_real_order_passes_scope(test_store):
    """Real order ORD-1001 belongs to demo-customer."""
    pred = IntentPrediction(intent="track_order", confidence=0.95, margin=0.5, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(
        ticket_customer_id="demo-customer",
        verified_scope="ticket:read order:read",
        is_personal_lookup=True,
        extracted_slots={"order_id": "ORD-1001"}
    )
    res = runner.run("Track order ORD-1001", ctx)
    assert res["action"] == "retrieve_draft"


def test_escalation_idempotency_persisted_in_store(test_store, tmp_path):
    pred = IntentPrediction(intent="customer_service", confidence=0.95, margin=0.6, model_version="v2.0.0")
    runner1 = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    ctx = RoutingContext(ticket_customer_id="demo-customer")

    res1 = runner1.run("I need help", ctx, run_id="run-101")
    assert res1["action"] == "escalate"
    assert res1["is_duplicate_run"] is False

    # Simulate new runner / process restart pointing to same store
    runner2 = PipelineRunner(intent_client=DummyIntentClient(pred), store=test_store)
    res2 = runner2.run("I need help", ctx, run_id="run-101")
    assert res2["action"] == "escalate"
    assert res2["is_duplicate_run"] is True
    assert res2["decision_id"] == res1["decision_id"]

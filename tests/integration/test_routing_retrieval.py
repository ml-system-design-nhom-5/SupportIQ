import pytest
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction

class DummyIntentClient:
    def __init__(self, pred: IntentPrediction):
        self.pred = pred

    def classify_intent(self, text: str, request_id: str = None) -> IntentPrediction:
        return self.pred

def test_missing_slot_clarifies():
    pred = IntentPrediction(intent="track_order", confidence=0.92, margin=0.5, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    ctx = RoutingContext(ticket_customer_id="cust_1", extracted_slots={})
    res = runner.run("Where is my package?", ctx)
    assert res["action"] == "clarify"
    assert "missing_order_id" in res["reason_codes"]


def test_policy_query_no_order_needed():
    pred = IntentPrediction(intent="return_policy", confidence=0.88, margin=0.4, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    ctx = RoutingContext(ticket_customer_id="cust_1")
    res = runner.run("What is your return policy?", ctx)
    assert res["action"] == "retrieve_draft"
    assert res["requested_team"] == "returns_support"


def test_34_routes_and_human_agent_escalate_without_llm():
    pred = IntentPrediction(intent="technical_issue", confidence=0.95, margin=0.7, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    ctx = RoutingContext(ticket_customer_id="cust_1")
    res = runner.run("The app crashed", ctx)
    assert res["action"] == "escalate"
    assert res["requested_team"] == "technical_support"
    assert res.get("llm_called") is not True


def test_ml_failure_manual_fallback():
    pred = IntentPrediction(intent="unknown", confidence=0.0, model_version="v2.0.0", error="Timeout")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    ctx = RoutingContext(ticket_customer_id="cust_1")
    res = runner.run("Anything", ctx)
    assert res["action"] == "manual_fallback"
    assert "ml_unavailable" in res["reason_codes"]


def test_unauthorized_order_access_rejected():
    pred = IntentPrediction(intent="track_order", confidence=0.95, margin=0.5, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    # Customer cust_1 tries to access order belonging to cust_999
    ctx = RoutingContext(ticket_customer_id="cust_1", extracted_slots={"order_id": "ORD_OTHER"})
    res = runner.run("Track my order", ctx)
    assert res["action"] == "escalate"
    assert "unauthorized_order_scope" in res["reason_codes"]


def test_escalation_idempotency():
    pred = IntentPrediction(intent="customer_service", confidence=0.95, margin=0.6, model_version="v2.0.0")
    runner = PipelineRunner(intent_client=DummyIntentClient(pred))
    ctx = RoutingContext(ticket_customer_id="cust_1")
    res1 = runner.run("I need help", ctx, run_id="run-101")
    res2 = runner.run("I need help", ctx, run_id="run-101") # Retry
    assert res1["action"] == "escalate"
    assert res2["action"] == "escalate"
    assert res2["is_duplicate_run"] is True

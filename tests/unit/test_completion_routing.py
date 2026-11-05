"""Unit tests for routing safety gates, human requests, outside-scope escalation, and fault handling (Task 2)."""

import pytest
from apps.core_backend.intent.routing import decide_route, load_policy_v2
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction, RouteDecision


@pytest.fixture
def policy():
    return load_policy_v2()


class TestRoutingCompletionGates:
    def test_human_agent_intent_always_escalates_even_with_low_confidence(self, policy):
        """When human_agent is predicted, low confidence must NOT convert it to clarify."""
        pred = IntentPrediction(
            intent="human_agent",
            confidence=0.35,  # Well below default threshold 0.75
            margin=0.05,
            model_version="v1.0",
            score_kind="mock",
            error=None,
        )
        ctx = RoutingContext(ticket_customer_id="cust-1", clarify_count=0)
        dec = decide_route(pred, ctx, policy)

        assert dec.action == "escalate"
        assert "human_agent_requested" in dec.reason_codes
        assert dec.requested_team == "general_support"

    def test_explicit_human_request_in_context_always_escalates(self, policy):
        """When context indicates explicit human request, low confidence must still escalate."""
        pred = IntentPrediction(
            intent="return_policy",
            confidence=0.20,
            margin=0.02,
            model_version="v1.0",
            score_kind="mock",
            error=None,
        )
        ctx = RoutingContext(
            ticket_customer_id="cust-2",
            is_human_agent_requested=True,
            clarify_count=0,
        )
        dec = decide_route(pred, ctx, policy)

        assert dec.action == "escalate"
        assert dec.requested_team == "general_support"
        assert "explicit_human_request" in dec.reason_codes

    def test_outside_scope_34_intents_escalate_and_never_clarify_or_draft(self, policy):
        """Recognized outside-scope intents (e.g. request_invoice, availability_online) must escalate."""
        outside_scope_intents = ["request_invoice", "availability_online", "submit_feedback", "technical_issue"]
        for intent in outside_scope_intents:
            pred = IntentPrediction(
                intent=intent,
                confidence=0.40,  # Low confidence
                margin=0.05,
                model_version="v1.0",
                score_kind="mock",
                error=None,
            )
            ctx = RoutingContext(ticket_customer_id="cust-3", clarify_count=0)
            dec = decide_route(pred, ctx, policy)

            assert dec.action == "escalate", f"Intent {intent} did not escalate under low confidence"
            assert "recognized_outside_product_scope" in dec.reason_codes

    def test_supported_intent_uncertainty_clarifies_on_first_try(self, policy):
        """Supported 11 intents with low confidence clarify on first attempt and escalate on second."""
        pred = IntentPrediction(
            intent="return_policy",
            confidence=0.40,
            margin=0.05,
            model_version="v1.0",
            score_kind="mock",
            error=None,
        )
        # First attempt: clarify
        ctx1 = RoutingContext(ticket_customer_id="cust-4", clarify_count=0)
        dec1 = decide_route(pred, ctx1, policy)
        assert dec1.action == "clarify"
        assert "low_confidence" in dec1.reason_codes

        # Second attempt: escalate
        ctx2 = RoutingContext(ticket_customer_id="cust-4", clarify_count=1)
        dec2 = decide_route(pred, ctx2, policy)
        assert dec2.action == "escalate"
        assert "max_clarify_reached" in dec2.reason_codes

    def test_general_policy_questions_do_not_require_order_id(self, policy):
        """General inquiry for return policy must not ask for order_id unless personal lookup is indicated."""
        pred = IntentPrediction(
            intent="return_policy",
            confidence=0.95,
            margin=0.40,
            model_version="v1.0",
            score_kind="mock",
            error=None,
        )
        ctx = RoutingContext(
            ticket_customer_id="cust-5",
            is_personal_lookup=False,
            extracted_slots={},
        )
        dec = decide_route(pred, ctx, policy)
        assert dec.action == "retrieve_draft"
        assert dec.missing_slots == []

    def test_explicit_human_request_overrides_ml_error(self, policy):
        """When ML service fails or times out, an explicit human request must still escalate to general_support."""
        pred = IntentPrediction(
            intent="unknown",
            confidence=0.0,
            margin=0.0,
            model_version="v1.0",
            score_kind="error",
            error="ml_service_timeout",
        )
        ctx = RoutingContext(
            ticket_customer_id="cust-6",
            is_human_agent_requested=True,
            clarify_count=0,
        )
        dec = decide_route(pred, ctx, policy)
        assert dec.action == "escalate"
        assert dec.requested_team == "general_support"
        assert "explicit_human_request" in dec.reason_codes

    def test_ml_error_without_human_request_falls_back_safely(self, policy):
        """When ML service fails without explicit human request, system must safely route to general_support via manual_fallback."""
        pred = IntentPrediction(
            intent="unknown",
            confidence=0.0,
            margin=0.0,
            model_version="v1.0",
            score_kind="error",
            error="ml_service_unavailable",
        )
        ctx = RoutingContext(
            ticket_customer_id="cust-7",
            is_human_agent_requested=False,
            clarify_count=0,
        )
        dec = decide_route(pred, ctx, policy)
        assert dec.action == "manual_fallback"
        assert dec.requested_team == "general_support"
        assert "ml_unavailable" in dec.reason_codes


class TestOrchestrationFaultHandling:
    def test_pipeline_runner_handles_ml_failure_safely(self, tmp_path):
        """PipelineRunner must safely handle ML failure and store run without crashing."""
        from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
        from apps.core_backend.orchestration.store import PersistentStore
        from unittest.mock import MagicMock

        mock_intent = MagicMock()
        mock_intent.classify_intent.return_value = IntentPrediction(
            intent="unknown",
            confidence=0.0,
            margin=0.0,
            model_version="v1.0",
            score_kind="error",
            error="ml_service_unavailable",
        )
        store = PersistentStore(db_path=str(tmp_path / "orch_fault_ml.sqlite3"))
        runner = PipelineRunner(intent_client=mock_intent, store=store)

        ctx = RoutingContext(ticket_customer_id="cust-fault-1")
        res = runner.run(text="Help me", context=ctx, run_id="run-fault-ml-1")

        assert res["action"] == "manual_fallback"
        assert res["requested_team"] == "general_support"
        assert "ml_unavailable" in res["reason_codes"]
        assert res["draft_body"] is None

    def test_pipeline_runner_handles_encoder_failure_safely(self, tmp_path):
        """PipelineRunner must handle retrieval encoder failure and safely fallback without crashing."""
        from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
        from apps.core_backend.orchestration.store import PersistentStore
        from unittest.mock import MagicMock

        mock_intent = MagicMock()
        mock_intent.classify_intent.return_value = IntentPrediction(
            intent="return_policy",
            confidence=0.95,
            margin=0.40,
            model_version="v1.0",
            score_kind="mock",
            error=None,
        )
        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = {
            "status": "encoder_unavailable",
            "evidence": [],
            "error": "Checkpoint not loaded",
        }
        store = PersistentStore(db_path=str(tmp_path / "orch_fault_enc.sqlite3"))
        runner = PipelineRunner(intent_client=mock_intent, retrieval_adapter=mock_retrieval, store=store)

        ctx = RoutingContext(ticket_customer_id="cust-fault-2")
        res = runner.run(text="What is the return window?", context=ctx, run_id="run-fault-enc-1")

        assert res["action"] in ("manual_fallback", "escalate")
        assert "encoder_unavailable" in res["reason_codes"]
        assert res["draft_body"] is None

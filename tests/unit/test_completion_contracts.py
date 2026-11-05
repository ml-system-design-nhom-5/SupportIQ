"""Unit tests for completion contracts and benchmark validation (Task 1)."""

from datetime import datetime, timezone
import json
import pytest

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    validate_expected_outcomes,
    load_system_inputs,
)


@pytest.fixture
def sample_kb():
    return [
        {
            "doc_id": "KB-01",
            "document_id": "KB-01",
            "version": "1.0",
            "status": "approved",
            "title": "Return Policy",
            "content": "Items can be returned within 30 days.",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window", "return_conditions"],
        },
        {
            "doc_id": "KB-02",
            "document_id": "KB-02",
            "version": "1.0",
            "status": "draft",
            "title": "Unapproved Policy",
            "content": "Not approved yet.",
            "allowed_roles": ["agent"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
        },
        {
            "doc_id": "KB-03",
            "document_id": "KB-03",
            "version": "1.0",
            "status": "approved",
            "title": "Expired Policy",
            "content": "Expired last year.",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2025-01-01T00:00:00Z",
            "valid_to": "2025-12-31T23:59:59Z",
        },
    ]


class TestValidateExpectedOutcomes:
    def test_contradiction_must_escalate_with_draft_expected(self, sample_kb):
        """must_escalate=True cannot have draft_expected=True."""
        case = SystemCase(
            id="case-contra-01",
            primary_slice="contradiction",
            text="I want human agent",
            true_intent="human_agent",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                must_escalate=True,
                draft_expected=True,  # Contradiction!
            ),
        )
        with pytest.raises(EvaluationError, match="must_escalate.*cannot expect draft|contradiction"):
            validate_expected_outcomes([case], sample_kb)

    def test_contradiction_must_not_draft_with_retrieve_draft_action(self, sample_kb):
        """must_not_draft=True cannot have retrieve_draft in actions."""
        case = SystemCase(
            id="case-contra-02",
            primary_slice="contradiction",
            text="Close account immediately",
            true_intent="close_account",
            context=SystemCaseContext(ticket_customer_id="cust-2"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],  # Contradiction with must_not_draft!
                must_not_draft=True,
                draft_expected=False,
            ),
        )
        with pytest.raises(EvaluationError, match="must_not_draft.*cannot contain retrieve_draft|contradiction"):
            validate_expected_outcomes([case], sample_kb)

    def test_missing_gold_document_raises_evaluation_error(self, sample_kb):
        """Answerable case referencing missing doc in KB must raise EvaluationError."""
        case = SystemCase(
            id="case-missing-gold",
            primary_slice="missing_gold",
            text="What is the shipping cost?",
            true_intent="shipping_costs",
            context=SystemCaseContext(ticket_customer_id="cust-3"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-NONEXISTENT", "version": "1.0"}],
                draft_expected=True,
            ),
        )
        with pytest.raises(EvaluationError, match="not found in KB"):
            validate_expected_outcomes([case], sample_kb)

    def test_unapproved_or_expired_gold_document_raises_evaluation_error(self, sample_kb):
        """Answerable case referencing unapproved or expired doc must raise EvaluationError."""
        # Unapproved
        c_unapproved = SystemCase(
            id="case-unapproved-gold",
            primary_slice="unapproved",
            text="Test query",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-4"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-02", "version": "1.0"}],
                draft_expected=True,
            ),
        )
        with pytest.raises(EvaluationError, match="unapproved|not approved"):
            validate_expected_outcomes([c_unapproved], sample_kb)

        # Expired
        c_expired = SystemCase(
            id="case-expired-gold",
            primary_slice="expired",
            text="Test query expired",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-5"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-03", "version": "1.0"}],
                draft_expected=True,
            ),
        )
        with pytest.raises(EvaluationError, match="expired|ineligible"):
            validate_expected_outcomes([c_expired], sample_kb, as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))

    def test_valid_cases_return_coverage_and_intent_breakdown(self, sample_kb):
        """Valid cases pass validation and return comprehensive outcome analytics."""
        c1 = SystemCase(
            id="case-valid-01",
            primary_slice="supported",
            text="What is the return window?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-6"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-01", "version": "1.0"}],
                draft_expected=True,
            ),
        )
        c2 = SystemCase(
            id="case-valid-02",
            primary_slice="escalation",
            text="Close my account please",
            true_intent="close_account",
            context=SystemCaseContext(ticket_customer_id="cust-7"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                must_escalate=True,
                must_not_draft=True,
                team="account_ops",
            ),
        )

        res = validate_expected_outcomes([c1, c2], sample_kb, as_of=datetime(2026, 6, 1, tzinfo=timezone.utc))
        assert isinstance(res, dict)
        assert res["total_cases"] == 2
        assert "coverage_by_intent" in res
        assert res["coverage_by_intent"]["return_policy"]["answerable_count"] == 1
        assert res["coverage_by_intent"]["close_account"]["escalate_count"] == 1
        assert res["contradictions"] == []
        assert res["missing_evidence"] == []

    def test_v2_dev_and_acceptance_suites_load_and_validate(self):
        """Dev and acceptance suites v2 must load cleanly and pass contract validation."""
        # 1. Dev suite
        dev_inputs = load_system_inputs(
            repo_root=".",
            suite_path="data/benchmarks/system/v2/dev/suite_manifest.json",
            config_path="pipeline/configs/system_evaluation.json",
            profile="mock",
        )
        assert len(dev_inputs.cases) == 50
        assert dev_inputs.manifest["split"] == "dev"

        # 2. Acceptance suite
        acc_inputs = load_system_inputs(
            repo_root=".",
            suite_path="data/benchmarks/system/v2/acceptance/suite_manifest.json",
            config_path="pipeline/configs/system_evaluation.json",
            profile="mock",
        )
        assert len(acc_inputs.cases) == 156
        assert acc_inputs.manifest["split"] == "acceptance"
        assert acc_inputs.manifest["status"] == "draft"

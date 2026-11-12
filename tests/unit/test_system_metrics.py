"""Unit tests for System Metrics calculation, gating, and Wilson score intervals."""

import pytest
from pydantic import ValidationError

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    CaseResult,
    SystemConfig,
)
from pipeline.evaluation.system_metrics import (
    aggregate_system_metrics,
    evaluate_system_gates,
    compute_wilson_ci,
)


def _make_case(
    case_id: str,
    must_escalate: bool = False,
    answerable: bool = False,
    gold_sources: list = None,
    draft_expected: bool = False,
    primary_slice: str = "supported",
    true_intent: str = "track_order",
) -> SystemCase:
    return SystemCase(
        id=case_id,
        primary_slice=primary_slice,
        tags=[],
        text="Test query",
        true_intent=true_intent,
        context=SystemCaseContext(ticket_customer_id="cust-1"),
        expected=SystemCaseExpected(
            actions=["escalate"] if must_escalate else ["retrieve_draft"],
            must_escalate=must_escalate,
            answerable=answerable,
            gold_sources=gold_sources or [],
            draft_expected=draft_expected,
        ),
    )


def _make_result(
    case_id: str,
    routing_action: str = "retrieve_draft",
    final_action: str = "retrieve_draft",
    predicted_intent: str = "track_order",
    sources: list = None,
    draft_body: str = None,
    status: str = "ok",
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        repetition=1,
        profile="mock",
        scope="e2e",
        execution_status=status,
        routing_action=routing_action,
        final_action=final_action,
        predicted_intent=predicted_intent,
        sources=sources or [],
        draft_body=draft_body,
    )


class TestAggregateSystemMetrics:
    def test_missing_decision_still_in_escalation_denominator(self):
        """Case with must_escalate=True missing from results still counts in must_escalate_total."""
        cases = [
            _make_case("c1", must_escalate=True),
            _make_case("c2", must_escalate=True),
        ]
        # Only c1 has a result; c2 is missing entirely
        results = [
            _make_result("c1", routing_action="escalate", final_action="escalate"),
        ]
        metrics = aggregate_system_metrics(cases, results)
        routing = metrics["routing"]
        assert routing["must_escalate_total"] == 2
        assert routing["must_escalate_correct"] == 1
        assert routing["guardrail_passed"] is False
        assert routing["must_escalate_success_rate"] == 0.5
        assert metrics["summary"]["missing"] == 1

    def test_duplicate_result_raises_evaluation_error(self):
        """Duplicate results for the same case_id must raise EvaluationError."""
        cases = [_make_case("c1")]
        results = [
            _make_result("c1"),
            _make_result("c1"),
        ]
        with pytest.raises(EvaluationError, match="Duplicate result"):
            aggregate_system_metrics(cases, results)

    def test_extra_result_raises_evaluation_error(self):
        """Result with case_id not declared in benchmark cases must raise EvaluationError."""
        cases = [_make_case("c1")]
        results = [
            _make_result("c1"),
            _make_result("c_unknown"),
        ]
        with pytest.raises(EvaluationError, match="Extra result ID"):
            aggregate_system_metrics(cases, results)

    def test_guardrail_exact_count_20000_of_20001_fails(self):
        """20000 correct out of 20001 must NOT pass guardrail (no float rounding leak)."""
        cases = [_make_case(f"c_{i}", must_escalate=True) for i in range(20001)]
        results = [
            _make_result(f"c_{i}", routing_action="escalate", final_action="escalate")
            for i in range(20000)
        ]
        # The 20001st case was drafted instead of escalated
        results.append(_make_result("c_20000", routing_action="retrieve_draft", final_action="retrieve_draft"))

        metrics = aggregate_system_metrics(cases, results)
        routing = metrics["routing"]
        assert routing["must_escalate_total"] == 20001
        assert routing["must_escalate_correct"] == 20000
        assert routing["guardrail_passed"] is False

    def test_retrieval_wrong_source_version_not_counted(self):
        """Returning a document with wrong version yields zero recall and zero hit."""
        cases = [
            _make_case(
                "c1",
                answerable=True,
                gold_sources=[{"doc_id": "KB-1", "version": "2.0"}],
            )
        ]
        results = [
            _make_result(
                "c1",
                sources=[{"doc_id": "KB-1", "version": "1.0"}],  # Wrong version!
            )
        ]
        metrics = aggregate_system_metrics(cases, results)
        retrieval = metrics["retrieval"]
        assert retrieval["recall_at_3"] == 0.0
        assert retrieval["hit_at_3"] == 0.0

    def test_retrieval_dedupes_top_3_sources(self):
        """Retrieved sources are deduplicated by (doc_id, version) within top 3."""
        cases = [
            _make_case(
                "c1",
                answerable=True,
                gold_sources=[{"doc_id": "KB-1", "version": "1.0"}, {"doc_id": "KB-2", "version": "1.0"}],
            )
        ]
        results = [
            _make_result(
                "c1",
                sources=[
                    {"doc_id": "KB-1", "version": "1.0"},
                    {"doc_id": "KB-1", "version": "1.0"},  # duplicate in top 3
                    {"doc_id": "KB-2", "version": "1.0"},
                ],
            )
        ]
        metrics = aggregate_system_metrics(cases, results)
        retrieval = metrics["retrieval"]
        assert retrieval["recall_at_3"] == 1.0
        assert retrieval["hit_at_3"] == 1.0

    def test_retrieval_false_evidence_on_unanswerable(self):
        """Unanswerable query that returns sources counts toward false_evidence_rate."""
        cases = [
            _make_case("c1", answerable=False),
            _make_case("c2", answerable=False),
        ]
        results = [
            _make_result("c1", sources=[{"doc_id": "KB-1", "version": "1.0"}]),
            _make_result("c2", sources=[]),
        ]
        metrics = aggregate_system_metrics(cases, results)
        retrieval = metrics["retrieval"]
        assert retrieval["unanswerable_count"] == 2
        assert retrieval["false_evidence_count"] == 1
        assert retrieval["false_evidence_rate"] == 0.5

    def test_zero_samples_safely_returns_na(self):
        """Empty benchmark cases return N/A for rate metrics."""
        metrics = aggregate_system_metrics([], [])
        assert metrics["summary"]["total_cases"] == 0
        assert metrics["routing"]["guardrail_passed"] == "N/A"
        assert metrics["routing"]["coverage"] == "N/A"
        assert metrics["retrieval"]["recall_at_3"] == "N/A"

    def test_initial_routing_vs_final_draft_yield(self):
        """Routing coverage counts initial routing acceptances, while draft_yield counts actual drafts."""
        cases = [
            _make_case("c1", draft_expected=True),
            _make_case("c2", draft_expected=True),
        ]
        results = [
            # c1: routing accepted retrieve_draft, LLM succeeded
            _make_result("c1", routing_action="retrieve_draft", final_action="retrieve_draft", draft_body="Here is your draft."),
            # c2: routing accepted retrieve_draft, but LLM failed / escalated
            _make_result("c2", routing_action="retrieve_draft", final_action="escalate", draft_body=None),
        ]
        metrics = aggregate_system_metrics(cases, results)
        routing = metrics["routing"]
        # Both c1 and c2 accepted by initial routing
        assert routing["coverage"] == 1.0
        # Only c1 actually yielded a draft
        assert routing["draft_yield"] == 0.5


class TestWilsonCI:
    def test_binomial_proportion_interval(self):
        ci = compute_wilson_ci(k=90, n=100, confidence=0.95)
        assert ci is not None
        low, high = ci
        assert 0.80 < low < 0.90
        assert 0.90 < high < 0.96

    def test_zero_or_negative_denominator(self):
        assert compute_wilson_ci(k=0, n=0) is None
        assert compute_wilson_ci(k=-1, n=10) is None


class TestEvaluateSystemGates:
    @pytest.fixture
    def system_config(self):
        return SystemConfig(
            mandatory_gates=["routing_guardrails", "retrieval_safety", "retrieval_recall"],
            thresholds={"recall_at_3": 0.80, "grounded_claims": 0.90},
        )

    def test_mock_profile_cannot_pass_live_acceptance_gates(self, system_config):
        """Simulated evidence kind MUST NOT pass live acceptance gates."""
        metrics = {
            "routing": {"guardrail_passed": True, "must_escalate_total": 5, "must_escalate_correct": 5},
            "retrieval": {"safety_violations": 0, "recall_at_3": 0.95, "answerable_count": 10},
        }
        gate_results = evaluate_system_gates(metrics, system_config, evidence_kind="simulated")
        assert gate_results["all_mandatory_passed"] is False
        assert "Simulated mock runs cannot satisfy live acceptance" in gate_results["summary_reason"]

    def test_live_profile_gate_evaluation(self, system_config):
        """Live evaluation checks exact thresholds and integer guardrails."""
        # Case 1: recall below threshold
        metrics_fail = {
            "routing": {"guardrail_passed": True, "must_escalate_total": 5, "must_escalate_correct": 5},
            "retrieval": {"safety_violations": 0, "recall_at_3": 0.75, "answerable_count": 10},
        }
        res_fail = evaluate_system_gates(metrics_fail, system_config, evidence_kind="live")
        assert res_fail["all_mandatory_passed"] is False
        assert res_fail["gates"]["retrieval_recall"]["status"] == "fail"

        # Case 2: all pass
        metrics_pass = {
            "routing": {"guardrail_passed": True, "must_escalate_total": 5, "must_escalate_correct": 5},
            "retrieval": {"safety_violations": 0, "recall_at_3": 0.85, "answerable_count": 10},
        }
        res_pass = evaluate_system_gates(metrics_pass, system_config, evidence_kind="live")
        assert res_pass["all_mandatory_passed"] is True
        assert res_pass["gates"]["retrieval_recall"]["status"] == "pass"

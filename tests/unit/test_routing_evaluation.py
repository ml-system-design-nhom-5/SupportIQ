import pytest
from pipeline.evaluation.evaluate_routing import evaluate_routes

def test_must_escalate_guardrail_failure():
    cases = [
        {"id": "c1", "true_intent": "close_account", "must_escalate": True},
        {"id": "c2", "true_intent": "track_order", "must_escalate": False},
    ]
    # c1 is incorrectly drafted instead of escalated
    decisions = [
        {"id": "c1", "action": "retrieve_draft", "predicted_intent": "close_account"},
        {"id": "c2", "action": "retrieve_draft", "predicted_intent": "track_order"},
    ]
    metrics = evaluate_routes(cases, decisions)
    assert metrics["guardrail_passed"] is False
    assert metrics["must_escalate_success_rate"] == 0.0


def test_guardrail_exact_count_no_float_rounding_leak():
    """20000 correct out of 20001 must NOT pass guardrail despite rounding."""
    cases = [{"id": f"c_{i}", "true_intent": "close_account", "must_escalate": True} for i in range(20001)]
    decisions = [{"id": f"c_{i}", "action": "escalate", "predicted_intent": "close_account"} for i in range(20000)]
    decisions.append({"id": "c_20000", "action": "retrieve_draft", "predicted_intent": "close_account"})

    metrics = evaluate_routes(cases, decisions)
    assert metrics["guardrail_passed"] is False
    assert metrics["must_escalate_correct"] == 20000
    assert metrics["must_escalate_total"] == 20001


def test_zero_denominator_safe():
    cases = []
    decisions = []
    metrics = evaluate_routes(cases, decisions)
    assert metrics["guardrail_passed"] == "N/A"
    assert metrics["coverage"] == "N/A"
    assert metrics["selective_accuracy"] == "N/A"


def test_coverage_and_selective_accuracy():
    cases = [
        {"id": "c1", "true_intent": "track_order", "must_escalate": False},
        {"id": "c2", "true_intent": "technical_issue", "must_escalate": True},
    ]
    decisions = [
        {"id": "c1", "action": "retrieve_draft", "predicted_intent": "track_order"},
        {"id": "c2", "action": "escalate", "predicted_intent": "technical_issue"},
    ]
    metrics = evaluate_routes(cases, decisions)
    assert metrics["guardrail_passed"] is True
    assert metrics["must_escalate_success_rate"] == 1.0
    assert metrics["selective_accuracy"] == 1.0
    # 1 out of 2 cases accepted for drafting -> coverage is 0.5
    assert metrics["coverage"] == 0.5

"""Selection rules of pipeline/evaluation/tune_routing.py (DATA-58: tuned on dev data only)."""
import pytest

pytest.importorskip("pandas")
from pipeline.evaluation import tune_routing as T  # noqa: E402
from apps.core_backend.intent.routing import load_policy_v2  # noqa: E402


def _r(mc, correct, multi=0.95, false=0.05, clarify=0.1, oos=0.95, esc=0, ts=0.0):
    m = {"multi_flag_rate": multi, "single_false_flag_rate": false, "dev_clarify_rate": clarify, "oos_flag_rate": oos,
         "dev_correct_draft_rate": correct, "dev_wrong_intent_drafts": 0, "dev_must_escalate_drafted": esc}
    return {"settings": {"min_clause_confidence": mc, "min_words": 3, "tau_shift": ts, "delta": 0.1},
            "metrics": m, "violation": T.violation(m)}


def test_feasible_setting_with_most_correct_drafts_wins():
    best = T.select([_r(0.6, 0.80), _r(0.7, 0.85), _r(0.8, 0.90, false=0.2), _r(0.9, 0.95, esc=1)])
    assert best["feasible"] and best["settings"]["min_clause_confidence"] == 0.7


def test_without_feasible_setting_smallest_violation_wins_and_is_reported():
    best = T.select([_r(0.6, 0.9, false=0.125), _r(0.7, 0.9, false=0.2)])
    assert not best["feasible"] and best["violation"] == 0.025


def test_sensitive_thresholds_and_margins_are_never_lowered():
    base = load_policy_v2()
    p = T._policy(base, tau_shift=-0.10, delta=0.05, min_conf=0.6, min_words=3)
    for intent in base.sensitive_action_intents:
        assert p.confidence_thresholds[intent] >= base.confidence_thresholds[intent]
    for intent, value in base.margin_thresholds.items():
        assert p.margin_thresholds[intent] >= value
    assert p.multi_request.min_clause_confidence == 0.6

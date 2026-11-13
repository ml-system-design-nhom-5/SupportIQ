"""Regression tests for Task C independent baseline, provider resilience, and classifier gate."""
from __future__ import annotations

import json
from pathlib import Path

from apps.core_backend.intent.routing import STANDARD_INTENTS_46
from pipeline.evaluation.classifier_acceptance_gate import (
    audit_candidate_provenance,
    check_split_isolation_and_gold_contamination,
)
from pipeline.evaluation.independent_baseline import build_independent_baseline_report
from pipeline.evaluation.provider_resilience_eval import (
    DEFAULT_SCHEDULES,
    ScheduleStep,
    ResilienceSchedule,
    compare_resilience_runs,
    run_resilience_suite,
    run_schedule,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_independent_baseline_correct_intent_vs_raw_and_strict_mandatory():
    report = build_independent_baseline_report(REPO_ROOT)
    srv = report["recomputed_metrics"]["serving_distilbert_supportiq"]
    rej = report["recomputed_metrics"]["rejected_supportpilot_distilbert"]
    live = report["recomputed_metrics"]["live_r3_run"]

    # Correct-intent draft eligibility strictly distinguishes wrong-intent drafts
    assert srv["final_acceptance_answerable_12"]["raw_draft_eligible_count"] == 5
    assert srv["final_acceptance_answerable_12"]["correct_intent_draft_eligible_count"] == 4
    assert srv["final_acceptance_answerable_12"]["wrong_intent_draft_eligible_count"] == 1
    assert srv["final_acceptance_answerable_12"]["wrong_intent_draft_case_ids"][0]["case_id"] == "final-case-02"

    assert rej["final_acceptance_answerable_12"]["raw_draft_eligible_count"] == 8
    assert rej["final_acceptance_answerable_12"]["correct_intent_draft_eligible_count"] == 6
    assert rej["final_acceptance_answerable_12"]["wrong_intent_draft_eligible_count"] == 2

    # Known acceptance regression suite (34 draft_expected & 63 mandatory escalation)
    assert srv["system_acceptance_156"]["draft_expected_34"]["raw_draft_eligible_count"] == 21
    assert srv["system_acceptance_156"]["draft_expected_34"]["correct_intent_draft_eligible_count"] == 17
    assert srv["system_acceptance_156"]["mandatory_escalation_63"]["n"] == 63
    assert srv["system_acceptance_156"]["mandatory_escalation_63"]["strict_expected_actions_match_count"] == 21
    assert srv["system_acceptance_156"]["mandatory_escalation_63"]["abstain_manual_fallback_count"] == 46
    assert srv["system_acceptance_156"]["mandatory_escalation_63"]["real_unsafe_draft_leak_count"] == 0

    assert rej["ml_oos_80"]["false_draft_case_ids"] == ["oos-multi_intent-07"]
    assert rej["system_acceptance_156"]["mandatory_escalation_63"]["real_unsafe_draft_leak_count"] == 2

    # Live r3: final-case-02 is the only draft_ready case and has wrong intent -> 0/12 both correct & drafted
    assert live["answerable_12"]["terminal_draft_ready_count"] == 1
    assert live["answerable_12"]["terminal_draft_ready_case_ids"] == ["final-case-02"]
    assert live["answerable_12"]["correct_intent_and_terminal_draft_ready_count"] == 0
    assert live["customer_no_auto_send_observed_http"] == 20


def test_provider_resilience_attempt_usage_budget_and_no_auto_send():
    report = run_resilience_suite(REPO_ROOT, label="unit_test_baseline", source_commit="test-sha")
    assert report["external_provider_calls"] == 0
    assert report["summary"]["total_schedules"] == len(DEFAULT_SCHEDULES)
    assert report["summary"]["budget_respected_all"] is True
    assert report["summary"]["attempt_cap_respected_all"] is True
    assert report["summary"]["no_auto_send_all"] is True
    assert report["summary"]["zero_fabricated_totals"] is True
    assert report["summary"]["all_attempts_persisted"] is True

    by_id = {r["schedule_id"]: r for r in report["schedules"]}
    # S07 timeout then success must record incomplete usage and total latency <= 10s
    s07 = by_id["S07_timeout_then_success"]
    assert s07["terminal_status"] == "draft_ready"
    assert s07["attempt_count"] == 2
    assert s07["usage_status"] == "incomplete_mixed_attempts"
    assert s07["total_tokens_fabricated"] is False
    assert s07["no_auto_send_verified"] is True

    # S08 repeated timeouts must keep usage unknown and fall back cleanly
    s08 = by_id["S08_repeated_timeouts_exhaust_budget"]
    assert s08["terminal_status"] == "llm_unavailable"
    assert s08["failure_code"] == "llm_timeout"
    assert s08["usage_status"] == "unknown_no_response"
    assert s08["llm_usage_mapped"] == {}

    # S13 sub-5s remaining budget clamp verifies request timeout never exceeds remaining budget
    s13 = by_id["S13_remaining_budget_clamped_timeout"]
    assert s13["simulated_elapsed_seconds"] <= 10.0 + 1e-3
    assert s13["attempt_cap_respected_5s"] is True

    # S14 malformed Retry-After and S15 invalid RetryInfo never crash
    assert by_id["S14_503_malformed_retry_after_header"]["attempt_count"] >= 1
    assert by_id["S15_429_invalid_retry_info_typing"]["attempt_count"] >= 1
    assert by_id["S17_429_daily_quota_exhausted_non_retryable"]["attempt_count"] == 1
    assert by_id["S18_fast_503_storm_max_attempts_bound"]["attempt_count"] <= 2

    comp = compare_resilience_runs(report, report)
    assert len(comp["schedule_comparison"]) == len(DEFAULT_SCHEDULES)
    assert "trust_env_audit" in report


def test_provider_resilience_single_custom_400_fast_fail():
    sched = ResilienceSchedule(
        schedule_id="custom_400",
        description="400 fails immediately without retry",
        category="non_retryable",
        steps=[ScheduleStep(outcome="http_error", duration_seconds=0.2, status_code=400)],
        expected_if_recovered="fallback",
    )
    row = run_schedule(sched, REPO_ROOT)
    assert row["attempt_count"] == 1
    assert row["failure_code"] == "llm_request_rejected"
    assert row["no_auto_send_verified"] is True


def test_classifier_gate_rejects_missing_lineage_overlap_and_gold_contamination(tmp_path: Path):
    # 1. Missing provenance manifest -> rejected
    cand_dir = tmp_path / "cand_model"
    cand_dir.mkdir()
    (cand_dir / "model.safetensors").write_bytes(b"fake-weights")
    (cand_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (cand_dir / "config.json").write_text(
        json.dumps({"id2label": {str(i): lbl for i, lbl in enumerate(STANDARD_INTENTS_46)}}),
        encoding="utf-8",
    )
    prov_missing = audit_candidate_provenance(cand_dir, manifest_path=None)
    assert prov_missing["provenance_passed"] is False
    assert "missing_or_unverified_provenance" in prov_missing["failure_reasons"]

    # Valid manifest with matching hash passes provenance audit
    from pipeline.evaluation.classifier_acceptance_gate import compute_file_sha256

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "provenance_status": "verified",
                "training_lineage": "synthetic_domain_plus_bitext_replay_v1",
                "dataset_hashes": {"train": "abc"},
                "base_model": "distilbert-base-uncased",
                "git_commit": "deadbeef",
                "artifact_hashes": {
                    "model.safetensors": compute_file_sha256(cand_dir / "model.safetensors"),
                    "tokenizer.json": compute_file_sha256(cand_dir / "tokenizer.json"),
                    "config.json": compute_file_sha256(cand_dir / "config.json"),
                },
            }
        ),
        encoding="utf-8",
    )
    prov_ok = audit_candidate_provenance(cand_dir, manifest_path=manifest_path)
    assert prov_ok["provenance_passed"] is True
    assert prov_ok["valid_46_label_bijection"] is True

    # 2. Split isolation rejects template group overlap and gold contamination
    gold = [("final_acceptance", "final-case-01", "What is the return window for products directly distributed by Tiki Trading?")]
    bad_overlap = check_split_isolation_and_gold_contamination(
        train_rows=[{"text": "How do I track order status?", "true_intent": "track_order", "group_id": "g1"}],
        calibration_rows=[{"text": "Where is my order tracking page?", "true_intent": "track_order", "group_id": "g1"}],
        eval_rows=[{"text": "What is the return window for products directly distributed by Tiki Trading?", "true_intent": "return_policy", "group_id": "g2"}],
        gold_texts=gold,
    )
    assert bad_overlap["passed"] is False
    assert "template_group_overlap:train_vs_calibration" in bad_overlap["failure_reasons"]
    assert "gold_benchmark_contamination_exact" in bad_overlap["failure_reasons"]

    # 3. Clean disjoint groups and zero gold overlap pass isolation check
    clean_iso = check_split_isolation_and_gold_contamination(
        train_rows=[{"text": "Explain Tiki Trading standard return days.", "true_intent": "return_policy", "group_id": "g_train"}],
        calibration_rows=[{"text": "Where can I view parcel tracking history?", "true_intent": "track_order", "group_id": "g_cal"}],
        eval_rows=[{"text": "How do I submit a refund request via wallet?", "true_intent": "request_refund", "group_id": "g_eval"}],
        gold_texts=gold,
    )
    assert clean_iso["passed"] is True
    assert clean_iso["failure_reasons"] == []


def test_ff0e147_evaluation_artifacts_hashes_and_9160_history_preserved():
    import hashlib
    import json

    ff_dir = REPO_ROOT / "artifacts/evaluation/provider_resilience_ff0e147_20261113"
    hashes = json.loads((ff_dir / "report_hashes.json").read_text(encoding="utf-8"))
    for name, expected_sha in hashes.items():
        actual_sha = hashlib.sha256((ff_dir / name).read_bytes()).hexdigest()
        assert actual_sha == expected_sha, f"Hash mismatch for {name}"

    comp = json.loads((ff_dir / "before_after_comparison.json").read_text(encoding="utf-8"))
    assert comp["before_commit"].startswith("54fda75")
    assert comp["after_commit"].startswith("ff0e147")
    assert comp["before_summary"]["transient_recovered_count"] == 4
    assert comp["after_summary"]["transient_recovered_count"] == 6
    assert comp["after_summary"]["latency_includes_retry_waits_all"] is True
    assert comp["after_summary"]["quota_429_non_retryable_fail_fast"] is True
    assert comp["after_summary"]["no_auto_send_all"] is True
    assert comp["after_summary"]["zero_fabricated_totals"] is True

    edge = json.loads((ff_dir / "candidate_edge_contracts.json").read_text(encoding="utf-8"))
    assert edge["source_commit"].startswith("ff0e147")
    assert edge["all_passed"] is True
    assert edge["checks"]["hard_quota_429_with_valid_header"]["passed"] is True
    assert edge["checks"]["malformed_injected_retry_after"]["passed"] is True

    # Historical 9160ffb artifacts must remain preserved with Wait Incl = False
    hist_comp = json.loads(
        (REPO_ROOT / "artifacts/evaluation/provider_resilience_9160ffb_20261113/before_after_comparison.json").read_text(
            encoding="utf-8"
        )
    )
    assert hist_comp["after_commit"].startswith("9160ffb")
    assert hist_comp["after_summary"]["latency_includes_retry_waits_all"] is False


def test_live_ff0e147_accounting_recomputation_and_followup_gate_artifacts():
    import hashlib
    import pytest
    from pipeline.evaluation.live_provider_verification import recompute_live_accounting_and_latency

    live_dir = REPO_ROOT / "artifacts/evaluation/live_ff0e147_oracle_20261113"
    live_json = live_dir / "live_verification.json"
    pricing_json = REPO_ROOT / "artifacts/evaluation/pricing/gemini-3.1-flash-lite-20261112.json"

    # Frozen live_verification.json must remain byte-identical
    live_sha = hashlib.sha256(live_json.read_bytes()).hexdigest()
    assert live_sha == "548a96fd2466fcefb1c2cb74e876818bc0ec1c9967b56765761cb662121f8dad"

    acct = json.loads((live_dir / "accounting_recomputed.json").read_text(encoding="utf-8"))
    fresh = recompute_live_accounting_and_latency(live_json, pricing_json)

    assert acct["new_live_calls_made"] == 0
    assert acct["source_live_verification_sha256"] == live_sha
    assert acct["previous_unverified_estimate"]["conditional_observed_list_price_usd"] == pytest.approx(0.00033345)
    assert acct["verified_primary_pricing"]["input_cost_per_million"] == pytest.approx(0.25)
    assert acct["verified_primary_pricing"]["output_cost_per_million"] == pytest.approx(1.50)

    tc = acct["token_and_cost_recomputation"]
    assert tc["attempts_missing_usage"] == 6
    assert tc["total_attempts_counted"] == 8
    assert tc["missing_thought_field_not_proof_of_zero"] is True
    assert tc["observed_total_minus_prompt_billable_output_tokens"] == 250
    assert tc["conditional_observed_list_price_usd"] == pytest.approx(0.0012365)
    assert tc["complete_cost_known"] is False
    assert tc["complete_cost_usd"] is None
    assert fresh["token_and_cost_recomputation"]["conditional_observed_list_price_usd"] == pytest.approx(0.0012365)

    lat = acct["latency_recomputation"]
    assert lat["http_calls_observed"] == 8
    assert lat["cases_executed"] == 4
    assert lat["standard_interpolated_median_p50_seconds"] == pytest.approx(8.26355)
    assert lat["prior_nearest_rank_index_p50_seconds"] == pytest.approx(9.9265)
    assert lat["nearest_rank_p95_seconds"] == pytest.approx(10.1452)

    # First Task A gate directory must remain untouched and preserved alongside followup gate
    first_gate = json.loads(
        (REPO_ROOT / "artifacts/evaluation/classifier_gate_task_a_first_20261113/gate_report.json").read_text(encoding="utf-8")
    )
    assert first_gate["gate_decision"] == "REJECT"
    assert first_gate["candidate_evaluation"]["ml_oos_80"]["false_draft_eligible_count"] == 2

    followup_dir = REPO_ROOT / "artifacts/evaluation/classifier_gate_task_a_followup_20261113"
    followup_gate = json.loads((followup_dir / "gate_report.json").read_text(encoding="utf-8"))
    followup_supp = json.loads((followup_dir / "followup_supplement.json").read_text(encoding="utf-8"))
    assert followup_gate["gate_decision"] == "REJECT"
    assert "oos_draft_leak" in followup_gate["failure_reasons"]
    assert followup_gate["candidate_evaluation"]["ml_oos_80"]["false_draft_eligible_count"] == 1
    assert followup_supp["domain_negatives_isolation_and_gold_contamination"]["passed"] is True
    assert followup_supp["independent_held_out_domain_negatives_27_eval"]["followup_candidate_32e9781"]["false_draft_count"] == 0
    assert followup_supp["candidate_provenance_sha256_verification"]["worker_a_promotion_approved"] is False


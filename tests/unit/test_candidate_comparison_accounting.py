"""Regression and accounting verification for candidate comparison results.

Verifies:
1. Exact denominator accounting across all benchmark suites from raw rows and summary.
2. Actual recomputation from raw predictions + frozen gold for system acceptance
   action matches and the 63 mandatory escalation cases.
3. Actual recomputation from raw predictions + frozen gold for final acceptance
   (24 total and 12 answerable) action matches and routing breakdown.
4. Actual recomputation from raw confidence and correctness against frozen gold for
   average confidence, 10-bin ECE, and binary top-label Brier score (top-1 only).
5. Traditional baseline audit logic using temporary missing/present fixtures plus
   verification of the archived historical inventory snapshot in summary.json
   (never asserting actual ignored repository model assets remain absent).
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.evaluation.autoeval import metrics as M
from scripts.compare_trained_candidates import audit_traditional_baselines

SUMMARY_PATH = REPO_ROOT / "artifacts/evaluation/candidate_comparison_20261113/summary.json"
RAW_PREDICTIONS_PATH = REPO_ROOT / "artifacts/evaluation/candidate_comparison_20261113/raw_predictions.jsonl"
ML_NOISE_PATH = REPO_ROOT / "data/benchmarks/autoeval/v1/ml_noise.jsonl"
ML_OOS_PATH = REPO_ROOT / "data/benchmarks/autoeval/v1/ml_oos.jsonl"
ACCEPTANCE_PATH = REPO_ROOT / "data/benchmarks/system/v2/acceptance/cases.jsonl"
FINAL_ACCEPTANCE_PATH = REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl"

CANDIDATES = ("distilbert-supportiq", "supportpilot-distilbert")


def _load_jsonl_by_id(path: Path) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return {c["id"]: c for c in (json.loads(line) for line in f if line.strip())}


def _rows_for(raw_predictions: List[Dict[str, Any]], candidate: str, suite: str) -> List[Dict[str, Any]]:
    return [r for r in raw_predictions if r["candidate"] == candidate and r["suite"] == suite]


def _compute_binary_top_label_brier(confidences: List[float], correctness: List[bool]) -> float:
    """Compute binary top-label Brier score: MSE(top1_conf, 1[pred == gold])."""
    return sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(confidences, correctness)) / len(confidences)


@pytest.fixture(scope="module")
def summary_data() -> Dict[str, Any]:
    assert SUMMARY_PATH.exists(), f"Missing summary file: {SUMMARY_PATH}"
    with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def raw_predictions() -> List[Dict[str, Any]]:
    assert RAW_PREDICTIONS_PATH.exists(), f"Missing raw predictions: {RAW_PREDICTIONS_PATH}"
    with open(RAW_PREDICTIONS_PATH, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(scope="module")
def noise_cases() -> Dict[str, Dict[str, Any]]:
    return _load_jsonl_by_id(ML_NOISE_PATH)


@pytest.fixture(scope="module")
def oos_cases() -> Dict[str, Dict[str, Any]]:
    return _load_jsonl_by_id(ML_OOS_PATH)


@pytest.fixture(scope="module")
def acceptance_cases() -> Dict[str, Dict[str, Any]]:
    return _load_jsonl_by_id(ACCEPTANCE_PATH)


@pytest.fixture(scope="module")
def final_acceptance_cases() -> Dict[str, Dict[str, Any]]:
    return _load_jsonl_by_id(FINAL_ACCEPTANCE_PATH)


def test_suite_denominators(summary_data, raw_predictions, noise_cases, oos_cases, acceptance_cases, final_acceptance_cases):
    """Verify exact denominators across summary and raw prediction rows against frozen gold."""
    assert len(noise_cases) == 420
    assert len(oos_cases) == 80
    assert len(acceptance_cases) == 156
    assert len(final_acceptance_cases) == 24

    for cand in CANDIDATES:
        suite_summary = summary_data["suites"][cand]
        noise_rows = _rows_for(raw_predictions, cand, "ml_noise")
        oos_rows = _rows_for(raw_predictions, cand, "ml_oos")
        acc_rows = _rows_for(raw_predictions, cand, "system_acceptance_156")
        fa_rows = _rows_for(raw_predictions, cand, "final_acceptance_24")

        assert len(noise_rows) == 420
        assert len(oos_rows) == 80
        assert len(acc_rows) == 156
        assert len(fa_rows) == 24

        assert suite_summary["ml_noise"]["n_total"] == 420
        assert suite_summary["ml_noise"]["clean"]["n"] == 84
        assert suite_summary["ml_noise"]["casual"]["n"] == 84
        assert suite_summary["ml_noise"]["typo"]["n"] == 252
        assert suite_summary["ml_oos"]["n_total"] == 80
        assert suite_summary["system_acceptance"]["n_total"] == 156
        assert suite_summary["final_acceptance"]["n_total"] == 24


def test_mandatory_escalation_and_action_match_recomputation(summary_data, raw_predictions, acceptance_cases):
    """Recompute system acceptance action matches and mandatory escalation accounting from raw rows + frozen gold."""
    expected_mandatory = {
        "distilbert-supportiq": {
            "overall_action_match": 74,
            "escalate": 16,
            "abstain": 46,
            "draft": 1,
            "action_match": 21,
            "non_drafting": 62,
            "draft_ids": {"unc-return_policy-04"},
        },
        "supportpilot-distilbert": {
            "overall_action_match": 85,
            "escalate": 15,
            "abstain": 45,
            "draft": 3,
            "action_match": 20,
            "non_drafting": 60,
            "draft_ids": {
                "uns-return_product_in_store-01",
                "uns-track_delivery-01",
                "unc-return_policy-04",
            },
        },
    }

    for cand, exp in expected_mandatory.items():
        sys_rows = _rows_for(raw_predictions, cand, "system_acceptance_156")
        assert {r["case_id"] for r in sys_rows} == set(acceptance_cases.keys())

        overall_action_matches = sum(
            1
            for r in sys_rows
            if r["adapted_routing_action"] in acceptance_cases[r["case_id"]]["expected"]["actions"]
        )
        assert overall_action_matches == exp["overall_action_match"]
        assert overall_action_matches == summary_data["suites"][cand]["system_acceptance"]["action_match_count"]

        mandatory_rows = [
            r for r in sys_rows if acceptance_cases[r["case_id"]].get("expected", {}).get("must_escalate", False)
        ]
        assert len(mandatory_rows) == 63

        esc_count = sum(1 for r in mandatory_rows if r["engine_recommendation"] == "escalate")
        abs_count = sum(1 for r in mandatory_rows if r["engine_recommendation"] == "abstain")
        draft_rows = [r for r in mandatory_rows if r["engine_recommendation"] == "draft"]
        mand_action_matches = sum(
            1
            for r in mandatory_rows
            if r["adapted_routing_action"] in acceptance_cases[r["case_id"]]["expected"]["actions"]
        )
        non_drafting_count = esc_count + abs_count

        assert esc_count == exp["escalate"]
        assert abs_count == exp["abstain"]
        assert len(draft_rows) == exp["draft"]
        assert {r["case_id"] for r in draft_rows} == exp["draft_ids"]
        assert mand_action_matches == exp["action_match"]
        assert non_drafting_count == exp["non_drafting"]

        acc = summary_data["suites"][cand]["system_acceptance"]["mandatory_escalations_accounting"]
        assert acc["n_total"] == len(mandatory_rows)
        assert acc["escalate_recommendation_count"] == esc_count
        assert acc["abstain_recommendation_count"] == abs_count
        assert acc["draft_recommendation_count"] == len(draft_rows)
        assert acc["action_match_count"] == mand_action_matches
        assert acc["non_drafting_count"] == non_drafting_count
        assert {d["case_id"] for d in acc["draft_cases"]} == exp["draft_ids"]

    serving_acc = summary_data["suites"]["distilbert-supportiq"]["system_acceptance"]["mandatory_escalations_accounting"]
    assert serving_acc["draft_cases"][0]["status"] == "NOT_EXECUTED"


def test_final_acceptance_recomputation(summary_data, raw_predictions, final_acceptance_cases):
    """Recompute final acceptance (24 total and 12 answerable) accounting from raw rows + frozen gold."""
    action_map = {"draft": "retrieve_draft", "abstain": "manual_fallback"}

    for cand in CANDIDATES:
        fa_rows = _rows_for(raw_predictions, cand, "final_acceptance_24")
        assert {r["case_id"] for r in fa_rows} == set(final_acceptance_cases.keys())

        fa_action_match = sum(
            1
            for r in fa_rows
            if r["adapted_action"] == action_map.get(
                final_acceptance_cases[r["case_id"]]["expected_action"],
                final_acceptance_cases[r["case_id"]]["expected_action"],
            )
        )
        fa_summary = summary_data["suites"][cand]["final_acceptance"]
        assert fa_action_match == fa_summary["action_match_count"]
        assert sum(1 for r in fa_rows if r["engine_recommendation"] == "draft") == fa_summary["draft_count"]
        assert sum(1 for r in fa_rows if r["engine_recommendation"] == "abstain") == fa_summary["abstain_count"]
        assert sum(1 for r in fa_rows if r["engine_recommendation"] == "escalate") == fa_summary["escalate_count"]

        ans_rows = _rows_for(raw_predictions, cand, "final_acceptance_answerable_12")
        gold_ans_ids = {cid for cid, c in final_acceptance_cases.items() if c.get("is_answerable")}
        assert {r["case_id"] for r in ans_rows} == gold_ans_ids
        assert len(ans_rows) == 12

        diag = summary_data["final_acceptance_12_answerable"][cand]
        assert sum(1 for r in ans_rows if r["routing_action"] == "retrieve_draft") == diag["drafted_count"]
        assert sum(1 for r in ans_rows if r["routing_action"] == "clarify") == diag["clarify_count"]
        assert sum(1 for r in ans_rows if r["routing_action"] == "escalate") == diag["escalate_count"]
        assert (
            sum(1 for r in ans_rows if r["predicted_intent"] == final_acceptance_cases[r["case_id"]]["intent"])
            == diag["correct_intent_count"]
        )

    serving_diag = summary_data["final_acceptance_12_answerable"]["distilbert-supportiq"]
    cand_diag = summary_data["final_acceptance_12_answerable"]["supportpilot-distilbert"]
    assert (serving_diag["drafted_count"], serving_diag["clarify_count"], serving_diag["escalate_count"]) == (5, 6, 1)
    assert (cand_diag["drafted_count"], cand_diag["clarify_count"], cand_diag["escalate_count"]) == (8, 2, 2)

    serving_case12 = next(c for c in serving_diag["cases"] if c["case_id"] == "final-case-12")
    cand_case12 = next(c for c in cand_diag["cases"] if c["case_id"] == "final-case-12")
    assert serving_case12["routing_action"] == "clarify"
    assert "low_confidence" in serving_case12["reason_codes"]
    assert serving_case12["is_automated_draft"] is False
    assert cand_case12["routing_action"] == "retrieve_draft"
    assert cand_case12["predicted_intent"] == "track_order"
    assert cand_case12["expected_intent"] == "payment_issue"
    assert cand_case12["confidence"] >= 0.80


def test_calibration_recomputed_from_raw_and_binary_brier_named(
    summary_data, raw_predictions, noise_cases, acceptance_cases
):
    """Recompute avg confidence, 10-bin ECE, and binary top-label Brier score from raw rows + frozen gold."""
    for cand in CANDIDATES:
        # Suite 1: ml_noise (N=420)
        noise_rows = _rows_for(raw_predictions, cand, "ml_noise")
        n_confs = [r["confidence"] for r in noise_rows]
        n_corrs = [r["predicted_intent"] == noise_cases[r["case_id"]]["true_intent"] for r in noise_rows]
        n_ece, _ = M.expected_calibration_error(n_confs, n_corrs, n_bins=10)
        n_brier = _compute_binary_top_label_brier(n_confs, n_corrs)
        n_avg_c = sum(n_confs) / len(noise_rows)

        noise_cal = summary_data["suites"][cand]["ml_noise"]["calibration"]
        assert noise_cal["n_evaluated"] == 420
        assert noise_cal["brier_score_kind"] == "binary_top_label_top1_only"
        assert noise_cal["avg_confidence"] == pytest.approx(n_avg_c, abs=1e-4)
        assert noise_cal["expected_calibration_error"] == pytest.approx(n_ece, abs=1e-4)
        assert noise_cal["binary_top_label_brier_score"] == pytest.approx(n_brier, abs=1e-4)

        # Suite 3: system_acceptance (153 labeled cases with true_intent; 3 OOD cases excluded)
        acc_rows = [
            r for r in _rows_for(raw_predictions, cand, "system_acceptance_156")
            if acceptance_cases[r["case_id"]].get("true_intent")
        ]
        assert len(acc_rows) == 153
        s_confs = [r["confidence"] for r in acc_rows]
        s_corrs = [r["predicted_intent"] == acceptance_cases[r["case_id"]]["true_intent"] for r in acc_rows]
        s_ece, _ = M.expected_calibration_error(s_confs, s_corrs, n_bins=10)
        s_brier = _compute_binary_top_label_brier(s_confs, s_corrs)
        s_avg_c = sum(s_confs) / len(acc_rows)

        acc_cal = summary_data["suites"][cand]["system_acceptance"]["calibration"]
        assert acc_cal["n_evaluated"] == 153
        assert acc_cal["brier_score_kind"] == "binary_top_label_top1_only"
        assert acc_cal["avg_confidence"] == pytest.approx(s_avg_c, abs=1e-4)
        assert acc_cal["expected_calibration_error"] == pytest.approx(s_ece, abs=1e-4)
        assert acc_cal["binary_top_label_brier_score"] == pytest.approx(s_brier, abs=1e-4)

    assert (
        summary_data["suites"]["supportpilot-distilbert"]["ml_noise"]["calibration"]["expected_calibration_error"]
        > summary_data["suites"]["distilbert-supportiq"]["ml_noise"]["calibration"]["expected_calibration_error"]
    )
    assert (
        summary_data["suites"]["supportpilot-distilbert"]["system_acceptance"]["calibration"]["expected_calibration_error"]
        > summary_data["suites"]["distilbert-supportiq"]["system_acceptance"]["calibration"]["expected_calibration_error"]
    )


def test_traditional_baseline_audit_with_missing_and_present_fixtures(tmp_path):
    """Test audit_traditional_baselines using temporary missing and present bundle fixtures."""
    bundle_payloads = {
        "linear_svm": b"fake-svm-bundle-bytes",
        "logistic_regression": b"fake-logreg-bundle-bytes",
        "multinomial_nb": b"fake-nb-bundle-bytes",
    }
    expected_hashes = {
        f"models/{mid}/bundle.joblib": hashlib.sha256(payload).hexdigest().upper()
        for mid, payload in bundle_payloads.items()
    }
    manifest = {
        "outputs": expected_hashes,
        "selection": {
            "best_per_model": {
                mid: {"macro_f1_mean": 0.99, "macro_f1_std": 0.001, "accuracy_mean": 0.99, "params": {}}
                for mid in bundle_payloads
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # 1. All bundles missing
    missing_audit = audit_traditional_baselines(run_dir=tmp_path)
    assert missing_audit["status"] == "weights_missing"
    for mid in bundle_payloads:
        assert missing_audit["models"][mid]["file_present_on_disk"] is False
        assert missing_audit["models"][mid]["runnable_for_live_inference"] is False

    # 2. One bundle restored with matching checksum -> partially present
    svm_dir = tmp_path / "models" / "linear_svm"
    svm_dir.mkdir(parents=True)
    (svm_dir / "bundle.joblib").write_bytes(bundle_payloads["linear_svm"])
    partial_audit = audit_traditional_baselines(run_dir=tmp_path)
    assert partial_audit["status"] == "weights_partially_present"
    assert partial_audit["models"]["linear_svm"]["file_present_on_disk"] is True
    assert partial_audit["models"]["linear_svm"]["sha256_match"] is True
    assert partial_audit["models"]["linear_svm"]["runnable_for_live_inference"] is True
    assert partial_audit["models"]["logistic_regression"]["file_present_on_disk"] is False

    # 3. Remaining bundles restored (one valid, one corrupted checksum) -> all present on disk, checksum enforced
    lr_dir = tmp_path / "models" / "logistic_regression"
    lr_dir.mkdir(parents=True)
    (lr_dir / "bundle.joblib").write_bytes(bundle_payloads["logistic_regression"])
    nb_dir = tmp_path / "models" / "multinomial_nb"
    nb_dir.mkdir(parents=True)
    (nb_dir / "bundle.joblib").write_bytes(b"corrupted-bytes")

    full_audit = audit_traditional_baselines(run_dir=tmp_path)
    assert full_audit["status"] == "weights_present"
    assert full_audit["models"]["logistic_regression"]["runnable_for_live_inference"] is True
    assert full_audit["models"]["multinomial_nb"]["file_present_on_disk"] is True
    assert full_audit["models"]["multinomial_nb"]["sha256_match"] is False
    assert full_audit["models"]["multinomial_nb"]["runnable_for_live_inference"] is False


def test_historical_baseline_inventory_record(summary_data):
    """Verify archived baseline inventory records historical evaluation-time absence without checking today's disk."""
    tb = summary_data["traditional_baselines"]
    assert tb["run_id"] == "03-11-2026-00"
    assert tb["inventory_snapshot_at"] == summary_data["metadata"]["created_at"]
    assert tb["status"] == "weights_missing_at_evaluation_snapshot"
    for mid in ("linear_svm", "logistic_regression", "multinomial_nb"):
        assert tb["models"][mid]["file_present_on_disk"] is False
        assert tb["models"][mid]["runnable_for_live_inference"] is False

    prov = summary_data["lineage_and_provenance"]["traditional_baselines"]
    assert prov["inventory_snapshot_at"] == summary_data["metadata"]["created_at"]
    assert prov["weights_status"] == "MISSING_ON_DISK_AT_EVALUATION_SNAPSHOT"

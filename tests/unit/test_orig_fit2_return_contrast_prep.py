from __future__ import annotations

from pathlib import Path

import pytest
import torch

from pipeline.evaluation.classifier_acceptance_gate import STANDARD_INTENTS_46
from pipeline.training.orig_fit2_return_contrast_data import (
    ORIG_FIT2_STAGE2_REL,
    build_orig_fit2_return_contrast_rows,
)
from pipeline.training.train_boundary_candidate import classify_row_kb_semantics
from scripts.run_boundary_contrast_fit import (
    EXPECTED_FIT2_SHA256,
    EXPECTED_SERVING_SHA256,
    validate_zero_fit_prep_namespace,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    EXPECTED_FIT1_SHA256,
    UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
    _build_hyperparameter_reconciliation,
    run_orig_fit2_preflight,
)


def test_extension_balance_taxonomy_and_kb_semantics():
    rows = build_orig_fit2_return_contrast_rows()
    assert len(rows) == 18

    by_intent = {}
    for row in rows:
        assert row["intent"] in STANDARD_INTENTS_46
        assert row["split"] == "train"
        assert row["kb_version"] == "approved_kb.v2.json"
        assert row["selective_label"] == 1
        assert row["is_negative"] == 0
        sem = classify_row_kb_semantics(row)
        assert sem["status"] == "valid", f"{row['sample_id']} failed KB check: {sem}"
        by_intent[row["intent"]] = by_intent.get(row["intent"], 0) + 1

    assert by_intent == {"return_policy": 10, "return_product_in_store": 8}
    # Effective exposure under unchanged Fit2 repeats: 10*4 = 40 vs 8*5 = 40.
    assert by_intent["return_policy"] * 4 == 40
    assert by_intent["return_product_in_store"] * 5 == 40


def test_zero_fit_preflight_reproduces_orig_baseline_and_blocks_optimizer_calibrator(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    stage2_ref = repo_root / ORIG_FIT2_STAGE2_REL
    if not stage2_ref.is_dir():
        pytest.skip("Archived faithful Fit2 stage2_inputs not present")

    def _forbid(*args, **kwargs):
        raise AssertionError("Zero-fit prep must never invoke optimizer or calibrator")

    class _StubTok:
        def encode(self, text, truncation=False, add_special_tokens=True):
            return [1] * len(text.split())

        def __call__(self, texts, truncation=False, max_length=64):
            return {"input_ids": [[1] * min(len(t.split()), max_length) for t in texts]}

    monkeypatch.setattr(torch.optim, "AdamW", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.fit_temperature_on_calibration_logits", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.run_fit_and_lock_candidate", _forbid)
    monkeypatch.setattr("pipeline.training.train_boundary_candidate.AutoTokenizer.from_pretrained", lambda *a, **kw: _StubTok())

    preflight = run_orig_fit2_preflight(repo_root, tmp_path / "dryrun")
    assert preflight["dry_run"] is True
    assert preflight["fits_executed"] == 0
    assert preflight["optimizer_invoked"] is False
    assert preflight["calibrator_invoked"] is False
    assert preflight["serving_weights_sha256"] == EXPECTED_SERVING_SHA256
    assert preflight["fit1_reference_weights_sha256"] == EXPECTED_FIT1_SHA256
    assert preflight["starting_checkpoint"]["weights_sha256"] == EXPECTED_FIT2_SHA256
    assert preflight["starting_checkpoint"]["temperature"] == 1.0
    assert preflight["starting_checkpoint"]["rejector_enabled"] is False
    assert preflight["starting_checkpoint"]["num_labels"] == 46

    diff = preflight["baseline_vs_new_diff"]
    assert set(diff["changed_files"].keys()) == {"boundary_pos_train.jsonl", "full_train_split.jsonl"}
    assert len(diff["unchanged_bit_identical_files"]) == 11
    assert diff["exposure_delta"] == {
        "raw_domain_return_policy_delta": 10,
        "raw_domain_return_product_in_store_delta": 8,
        "effective_domain_return_policy_delta": 40,
        "effective_domain_return_product_in_store_delta": 40,
        "effective_train_total_delta": 80,
    }
    assert preflight["counts"]["domain_pos_train"] == 199
    assert preflight["counts"]["domain_pos_cal"] == 86
    assert preflight["counts"]["domain_pos_eval"] == 122
    assert preflight["isolation_audit"]["isolation_passed"] is True
    assert preflight["isolation_audit"]["max_jaccard_across_all_frozen_suites"] < 0.55
    assert preflight["isolation_audit"]["max_token_f1_across_all_frozen_suites"] < 0.65
    assert (
        preflight["historical_baseline_noisy_overlap_disclosure"]["historical_bitext_train_noisy_vs_eval_norm_overlap_count"]
        == 3
    )


def test_prep_namespace_collision_and_no_overwrite(tmp_path):
    candidates_dir = tmp_path / "candidates"
    local_root = tmp_path / "local"
    candidates_dir.mkdir(parents=True)
    local_root.mkdir(parents=True)

    ns = validate_zero_fit_prep_namespace(
        prep_run_id="fit2-orig-ret-channel-v1",
        fit_run_id="fit2-orig-ret-channel-fit-v1",
        main_candidates_dir=candidates_dir,
        local_contrast_root=local_root,
    )
    assert ns["prep_records_dir"].name == "run-records-fit2-orig-ret-channel-v1-prep"

    ns["prep_records_dir"].mkdir()
    with pytest.raises(FileExistsError):
        validate_zero_fit_prep_namespace(
            prep_run_id="fit2-orig-ret-channel-v1",
            fit_run_id="fit2-orig-ret-channel-fit-v1",
            main_candidates_dir=candidates_dir,
            local_contrast_root=local_root,
        )


def test_reconciliation_leaves_fit_hyperparams_unselected_and_rejector_off(tmp_path):
    assert UNCHANGED_ORIGINAL_RECIPE_PARAMETERS["fit_mode"] == "fit2_supcon_energy"
    assert UNCHANGED_ORIGINAL_RECIPE_PARAMETERS["min_temperature"] == 1.0
    assert UNCHANGED_ORIGINAL_RECIPE_PARAMETERS["selective_rejector_enabled"] is False
    assert UNCHANGED_ORIGINAL_RECIPE_PARAMETERS["apply_active_kb_audit"] is False
    assert UNCHANGED_ORIGINAL_RECIPE_PARAMETERS["exclude_noisy_test_overlap"] is False

    rec = _build_hyperparameter_reconciliation(
        prep_records_dir=tmp_path / "run-records-fit2-orig-ret-channel-v1-prep",
        planned_fit_run_id="fit2-orig-ret-channel-fit-v1",
        planned_future_paths={
            "archive_dir": str(tmp_path / "fit_archive"),
            "records_dir": str(tmp_path / "fit_records"),
            "local_dir": str(tmp_path / "fit_local"),
        },
    )
    assert rec["selected_by_worker_a"] is None
    assert rec["signoff_required_before_fit"] is True
    assert rec["authorized_to_train_now"] is False
    opt_a = rec["options"]["option_a_original_fit2_hyperparams"]
    opt_b = rec["options"]["option_b_historical_continuation_helper_hyperparams"]
    assert (opt_a["epochs"], opt_a["lr"]) == (3, 2e-5)
    assert (opt_b["epochs"], opt_b["lr"]) == (2, 1e-5)
    assert "enable_selective_rejector=False" in " ".join(opt_a["planned_cli"])
    assert "fit2_supcon_energy" in " ".join(opt_b["planned_cli"])

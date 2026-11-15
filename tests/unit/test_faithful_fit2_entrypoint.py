"""Focused unit tests for fail-closed preflight, Stage 1 data assembly, rejector archival, and Stage 2 handoff."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import scripts.run_faithful_fit2_restore as restore_mod
from apps.core_backend.intent.routing import STANDARD_INTENTS_46
from pipeline.training.train_domain_candidate import (
    MissingLineageBlockerError,
    verify_original_46_label_lineage,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _has_local_bitext_46_data() -> bool:
    return (
        (
            (REPO_ROOT / "data/datasets/processed/03-11-2026-02/cleaned.csv").is_file()
            and (REPO_ROOT / "data/datasets/splits/03-11-2026-02/split_assignments.csv").is_file()
        )
        or (
            (REPO_ROOT / "data/datasets/restored/bitext-12dd624/prep/data/datasets/processed/13-11-2026-00/cleaned.csv").is_file()
            and (REPO_ROOT / "data/datasets/restored/bitext-12dd624/prep/data/datasets/splits/13-11-2026-00/split_assignments.csv").is_file()
        )
    )


def _build_synthetic_46_label_lineage(fixture_root: Path):
    """Build deterministic 46-label CSVs + SHA-locked prep manifests in tmp_path and verify via real parser."""
    fixture_root.mkdir(parents=True, exist_ok=True)
    cleaned_rows = []
    split_rows = []
    idx = 0
    for intent in STANDARD_INTENTS_46:
        for i in range(86):
            idx += 1
            sid = f"syn_sample_{idx:05d}"
            cleaned_rows.append(
                {
                    "sample_id": sid,
                    "instruction": f"Synthetic customer inquiry {idx} regarding {intent.replace('_', ' ')}",
                    "intent": intent,
                }
            )
            split_rows.append({"sample_id": sid, "partition": "train" if i < 85 else "test"})

    cleaned_path = fixture_root / "cleaned.csv"
    splits_path = fixture_root / "split_assignments.csv"
    pd.DataFrame(cleaned_rows).to_csv(cleaned_path, index=False)
    pd.DataFrame(split_rows).to_csv(splits_path, index=False)

    cleaned_sha = hashlib.sha256(cleaned_path.read_bytes()).hexdigest().upper()
    splits_sha = hashlib.sha256(splits_path.read_bytes()).hexdigest().upper()

    manifest_path = fixture_root / "manifest.json"
    split_report_path = fixture_root / "split_report.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "synthetic-46",
                "input_files": {"raw_sha256": ""},
                "output_artifacts": {
                    "cleaned_csv": str(cleaned_path),
                    "split_assignments": str(splits_path),
                },
            }
        ),
        encoding="utf-8",
    )
    split_report_path.write_text(
        json.dumps({"cleaned_sha256": cleaned_sha, "splits_sha256": splits_sha}),
        encoding="utf-8",
    )
    return verify_original_46_label_lineage(
        preparation_manifest_path=manifest_path,
        split_report_path=split_report_path,
        cleaned_csv_override=cleaned_path,
        splits_csv_override=splits_path,
        repo_root=REPO_ROOT,
    )


def test_stage1_real_data_assembly_and_rejector_invocation(tmp_path: Path) -> None:
    """Deterministic assemble_stage1_closure_data produces all 46 replay labels, 0 OOD in CE, disjoint cal, and invokes rejector."""
    syn_lineage = _build_synthetic_46_label_lineage(tmp_path / "syn_46")
    with patch.object(restore_mod, "verify_original_46_label_lineage", return_value=syn_lineage):
        s1_data = restore_mod.assemble_stage1_closure_data(REPO_ROOT, tmp_path / "ds", seed=42)
    assert len(set(s1_data["pos_train_labels"])) == 46
    assert all(f == 0 for f in s1_data["pos_train_flags"])
    assert len(s1_data["pos_train_texts"]) > 3000
    assert not (set(s1_data["replay_domain_train_df"]["sample_id"]) & set(s1_data["bitext_cal_df"]["sample_id"]))

    fit_calls = []
    cal_calls = []

    def _fake_single_fit(**kwargs):
        fit_calls.append(kwargs)
        out = kwargs["output_dir"]
        out.mkdir(parents=True, exist_ok=True)
        for fname in ("model.safetensors", "tokenizer.json", "config.json"):
            (out / fname).write_bytes(b"stub")
        return {"fit": kwargs["fit_name"]}

    def _fake_cal(**kwargs):
        cal_calls.append(kwargs)
        return 1.04, {"enabled": True, "type": "logistic_regression_v1", "feature_spec": "cls_l2_plus_logit_geometry_v1", "feature_dim": 776, "scaler_mean": [0.0]*776, "scaler_scale": [1.0]*776, "weights": [0.0]*776, "bias": 0.0, "threshold": 0.74, "reject_when": "below", "positive_label": "in_scope"}, {"utility": 1.0}

    with (
        patch.object(restore_mod, "run_preflight_validation", return_value={"dry_run": True}),
        patch.object(restore_mod, "_train_closure_single_fit", side_effect=_fake_single_fit),
        patch.object(restore_mod, "_build_closure_rejector_on_train_and_cal", side_effect=_fake_cal),
        patch.object(restore_mod, "write_calibration_manifest", return_value=tmp_path / "cal_m.json") as mock_wcm,
        patch.object(restore_mod, "_archive_to_main", return_value={"archive_dir": str(tmp_path / "arch1")}),
        patch.object(restore_mod, "MAIN_CANDIDATES_DIR", tmp_path / "main_cand"),
        patch.object(restore_mod, "LOCAL_RESTORE_ROOT", tmp_path / "local_restore"),
        patch.object(restore_mod, "assemble_stage1_closure_data", return_value=s1_data),
        patch.object(sys, "argv", ["prog", "--run-stage1-closure-fit1", "--stage1-run-id", "test-s1"]),
    ):
        (tmp_path / "cal_m.json").write_text("{}", encoding="utf-8")
        restore_mod.main()

    assert len(fit_calls) == 1
    assert fit_calls[0]["fit_name"] == "fit1_closure_dual_head"
    assert fit_calls[0]["objective_mode"] == "clean_positive_ce"
    assert len(set(fit_calls[0]["train_labels"])) == 46
    assert all(f == 0 for f in fit_calls[0]["train_is_negative"])
    assert len(cal_calls) == 1
    mock_wcm.assert_called_once()


def test_combined_stage1_and_stage2_passes_new_stage1_archive(tmp_path: Path) -> None:
    """Combined flags make Stage 2 consume the newly archived Stage 1 MAIN dir, not unset args."""
    syn_lineage = _build_synthetic_46_label_lineage(tmp_path / "syn_46")
    with patch.object(restore_mod, "verify_original_46_label_lineage", return_value=syn_lineage):
        s1_data = restore_mod.assemble_stage1_closure_data(REPO_ROOT, tmp_path / "ds", seed=42)
    main_cand = tmp_path / "main_cand"
    stage2_calls = []

    def _fake_single_fit(**kwargs):
        out = kwargs["output_dir"]
        out.mkdir(parents=True, exist_ok=True)
        for fname in ("model.safetensors", "tokenizer.json", "config.json"):
            (out / fname).write_bytes(b"stub")
        return {"fit": kwargs["fit_name"]}

    def _fake_stage2(**kwargs):
        stage2_calls.append(kwargs)
        return {"fit_mode": kwargs["fit_mode"]}

    with (
        patch.object(restore_mod, "run_preflight_validation", return_value={"dry_run": True}),
        patch.object(restore_mod, "assemble_stage1_closure_data", return_value=s1_data),
        patch.object(restore_mod, "_train_closure_single_fit", side_effect=_fake_single_fit),
        patch.object(restore_mod, "_build_closure_rejector_on_train_and_cal", return_value=(1.0, {}, {})),
        patch.object(restore_mod, "write_calibration_manifest", return_value=tmp_path / "cal_m.json"),
        patch.object(restore_mod, "_archive_to_main", return_value={"archive_dir": "ok"}),
        patch.object(restore_mod, "verify_stage1_archive_before_stage2") as mock_vs1,
        patch.object(restore_mod, "prepare_and_lock_splits", return_value={"counts": {}}),
        patch.object(restore_mod, "run_fit_and_lock_candidate", side_effect=_fake_stage2),
        patch.object(restore_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(restore_mod, "LOCAL_RESTORE_ROOT", tmp_path / "local_restore"),
        patch.object(sys, "argv", ["prog", "--run-stage1-closure-fit1", "--run-stage2-boundary-fit2", "--stage1-run-id", "s1-run", "--stage2-run-id", "s2-run"]),
    ):
        (tmp_path / "cal_m.json").write_text("{}", encoding="utf-8")
        restore_mod.main()

    mock_vs1.assert_called_once_with(main_cand / "s1-run")
    assert len(stage2_calls) == 1
    assert stage2_calls[0]["fit_mode"] == "fit2_supcon_energy"
    assert stage2_calls[0]["init_model_dir"] == main_cand / "s1-run"


def test_tampered_preflight_or_preexisting_archive_prevents_training(tmp_path: Path) -> None:
    """Fail-closed preflight and archive uniqueness block training before any fit runs."""
    main_cand = tmp_path / "main_cand"
    existing = main_cand / "dup-s1"
    existing.mkdir(parents=True)

    with (
        patch.object(restore_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(restore_mod, "_train_closure_single_fit") as mock_fit,
        patch.object(sys, "argv", ["prog", "--run-stage1-closure-fit1", "--stage1-run-id", "dup-s1"]),
    ):
        with pytest.raises(FileExistsError):
            restore_mod.main()
        mock_fit.assert_not_called()

    with (
        patch.object(restore_mod, "MAIN_CANDIDATES_DIR", main_cand),
        patch.object(restore_mod, "run_preflight_validation", side_effect=RuntimeError("tampered hash")),
        patch.object(restore_mod, "_train_closure_single_fit") as mock_fit,
        patch.object(sys, "argv", ["prog", "--run-stage1-closure-fit1", "--stage1-run-id", "fresh-s1"]),
    ):
        with pytest.raises(RuntimeError, match="tampered hash"):
            restore_mod.main()
        mock_fit.assert_not_called()


def test_wrong_stage1_archive_fails_before_stage2_training(tmp_path: Path) -> None:
    """Incomplete or wrong-lineage Stage 1 archive fails verify_stage1_archive_before_stage2 before Stage 2 trains."""
    bad_s1 = tmp_path / "bad_s1"
    bad_s1.mkdir()
    with pytest.raises(FileNotFoundError):
        restore_mod.verify_stage1_archive_before_stage2(bad_s1)

    (bad_s1 / "model.safetensors").write_bytes(b"x")
    (bad_s1 / "calibration_manifest.json").write_text("{}", encoding="utf-8")
    (bad_s1 / "candidate_provenance_manifest.json").write_text(json.dumps({"selected_fit": "wrong_fit"}), encoding="utf-8")
    (bad_s1 / "archive_sha_inventory.json").write_text(
        json.dumps({"model.safetensors": restore_mod._sha256_lower(bad_s1 / "model.safetensors")}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Unexpected Stage 1 selected_fit"):
        restore_mod.verify_stage1_archive_before_stage2(bad_s1)


def test_missing_original_46_label_lineage_fails_closed(tmp_path: Path) -> None:
    """Absent 46-label preparation manifest/data raises MissingLineageBlockerError fail-closed."""
    with pytest.raises(MissingLineageBlockerError):
        verify_original_46_label_lineage(repo_root=tmp_path)


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_local_bitext_46_data(),
    reason="Requires gitignored local 46-label Bitext cleaned.csv and split_assignments.csv.",
)
def test_stage1_real_bitext_assembly_preflight(tmp_path: Path) -> None:
    """Integration preflight: real local Bitext dataset produces 46 labels and disjoint calibration split."""
    s1_data = restore_mod.assemble_stage1_closure_data(REPO_ROOT, tmp_path / "ds_real", seed=42)
    assert len(set(s1_data["pos_train_labels"])) == 46
    assert all(f == 0 for f in s1_data["pos_train_flags"])
    assert len(s1_data["pos_train_texts"]) > 3000
    assert not (set(s1_data["replay_domain_train_df"]["sample_id"]) & set(s1_data["bitext_cal_df"]["sample_id"]))


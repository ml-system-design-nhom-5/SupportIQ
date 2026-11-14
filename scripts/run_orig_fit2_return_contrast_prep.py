"""Strictly zero-fit preflight & MAIN prep archive for Original Fit2 return-channel contrast.

Anchors strictly to Original Fit2 (`reconstructed-fit2-supcon-20261113`,
`f695b1fe...`), reproduces original faithful Stage-2 inputs bit-for-bit, applies
ONLY the 18-row balanced TRAIN-only return-channel contrast delta, verifies full
cross-suite isolation, and writes an immutable `-prep` bundle with zero fits.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import torch
import transformers
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from pipeline.evaluation.classifier_acceptance_gate import (
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
)
from pipeline.training.orig_fit2_return_contrast_data import (
    _read_jsonl,
    prepare_and_lock_orig_fit2_return_contrast_splits,
    prepare_and_lock_orig_fit2_zero_delta_control_splits,
)
from pipeline.training.train_boundary_candidate import (
    _configure_trainable_scope,
    _snapshot_frozen_component_hashes,
    verify_original_46_label_lineage,
)
from scripts.run_boundary_contrast_fit import (
    EXPECTED_FIT2_SHA256,
    EXPECTED_SERVING_SHA256,
    FIT2_BASELINE_DIR,
    MAIN_CANDIDATES_DIR,
    SERVING_DIR,
    _sha256_lower,
    _verify_dir_matches_lock_hashes,
    _write_and_verify_sha_inventory,
    validate_zero_fit_prep_namespace,
    verify_fit2_starting_checkpoint,
)

DEFAULT_PREP_PROFILE = "lr5e6"
DEFAULT_PREP_RUN_ID = "fit2-orig-ret-channel-v4"
DEFAULT_PLANNED_FIT_RUN_ID = "fit2-orig-ret-channel-lr5e6-v1"
LOCAL_ORIG_CONTRAST_ROOT = Path(__file__).resolve().parents[1] / "artifacts/evaluation/fit2_orig_ret_channel_20261114"
FIT1_CHECKPOINT_REL = "artifacts/models/candidates/reconstructed-closure-fit1-20261113"
EXPECTED_FIT1_SHA256 = "95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6"
ORIG_FAITHFUL_RECORDS_REL = "artifacts/models/candidates/run-records-faithful-fit2-20261113"

AUTHORIZED_FIT_PROFILES: Dict[str, Dict[str, Any]] = {
    "option_a": {
        "profile": "option_a",
        "selected_recipe": "option_a_original_fit2_hyperparams",
        "lr": 2e-5,
        "epochs": 3,
        "batch_size": 32,
        "seed": 42,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
    },
    "lr5e6": {
        "profile": "lr5e6",
        "selected_recipe": "lr5e6_low_lr_original_fit2_hyperparams",
        "lr": 5e-6,
        "epochs": 3,
        "batch_size": 32,
        "seed": 42,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
    },
    "option_a_teacher_kl": {
        "profile": "option_a_teacher_kl",
        "selected_recipe": "option_a_masked_teacher_kl_v1",
        "lr": 2e-5,
        "epochs": 3,
        "batch_size": 32,
        "seed": 42,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "teacher_weights_sha256": EXPECTED_FIT2_SHA256,
        "teacher_kl_weight": 1.0,
        "teacher_temperature": 1.0,
    },
    "option_a_teacher_kl_deterministic": {
        "profile": "option_a_teacher_kl_deterministic",
        "selected_recipe": "option_a_masked_deterministic_teacher_kl_v1",
        "lr": 2e-5,
        "epochs": 3,
        "batch_size": 32,
        "seed": 42,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "teacher_weights_sha256": EXPECTED_FIT2_SHA256,
        "teacher_kl_weight": 1.0,
        "teacher_temperature": 1.0,
        "teacher_student_anchor_mode": "eval_no_dropout_autograd_enabled",
    },
    "option_a_classifier_head_only_v1": {
        "profile": "option_a_classifier_head_only_v1",
        "selected_recipe": "option_a_classifier_head_only_adamw_1e4_2ep",
        "lr": 1e-4,
        "epochs": 2,
        "batch_size": 32,
        "seed": 42,
        "weight_decay": 0.01,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "trainable_scope": "classifier_head_only",
        "feature_dropout_eval_mode": True,
        "expected_trainable_param_count": 35374,
        "expected_frozen_param_count": 66953472,
    },
    "option_a_pre_classifier_head_v1": {
        "profile": "option_a_pre_classifier_head_v1",
        "selected_recipe": "option_a_pre_classifier_head_adamw_5e5_3ep",
        "lr": 5e-5,
        "epochs": 3,
        "batch_size": 32,
        "seed": 42,
        "weight_decay": 0.01,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "trainable_scope": "pre_classifier_and_classifier",
        "feature_dropout_eval_mode": True,
        "expected_trainable_param_count": 625966,
        "expected_frozen_param_count": 66362880,
    },
}

SUBHEAD_PROFILE_MANIFEST_KEYS: Dict[str, str] = {
    "option_a_classifier_head_only_v1": "classifier_head_only_config",
    "option_a_pre_classifier_head_v1": "subhead_scope_config",
}
SUBHEAD_FIT_PROFILES: Tuple[str, ...] = tuple(SUBHEAD_PROFILE_MANIFEST_KEYS.keys())


def validate_subhead_config_block(block: Any, profile_name: str) -> None:
    """Validate frozen subhead manifest/run-config metadata against AUTHORIZED_FIT_PROFILES."""
    cfg = AUTHORIZED_FIT_PROFILES[profile_name]
    if (
        not isinstance(block, dict)
        or block.get("enabled") is not True
        or str(block.get("trainable_scope", "")) != str(cfg["trainable_scope"])
        or block.get("feature_dropout_eval_mode") is not True
        or abs(float(block.get("weight_decay", -1.0)) - float(cfg["weight_decay"])) > 1e-12
        or block.get("teacher_used") is not False
        or int(block.get("trainable_param_count", -1)) != int(cfg["expected_trainable_param_count"])
        or int(block.get("frozen_param_count", -1)) != int(cfg["expected_frozen_param_count"])
        or not block.get("initial_frozen_tensors_sha256")
        or not isinstance(block.get("initial_freeze_component_hashes"), dict)
    ):
        raise ValueError(f"Invalid {SUBHEAD_PROFILE_MANIFEST_KEYS[profile_name]} in prep_manifest: {block}")

CAL_GUARD_FLOAT_TOLERANCE = 3e-6
CAL_GUARD_DENOMINATORS: Dict[str, int] = {
    "boundary_pos_cal": 86,
    "boundary_pos_cal_sup12": 48,
    "boundary_pos_cal_esc34": 38,
    "bitext_cal": 690,
    "boundary_neg_cal": 48,
    "pos_train_added_18": 18,
}
CAL_GUARD_DEFINITION: Dict[str, Any] = {
    "schema_version": "orig_fit2_cal_guard_def.v1",
    "surface": "unpseudonymized raw text post-T softmax probabilities",
    "denominators": dict(CAL_GUARD_DENOMINATORS),
    "float_tolerance": CAL_GUARD_FLOAT_TOLERANCE,
    "float_tolerance_justification": "CPU-vs-CUDA float rounding bound (<= 3e-6) verified in Worker B parity audit; zero tolerance on integer count gates.",
    "integer_count_gates": {
        "boundary_pos_cal_correct_min": 68,
        "boundary_pos_cal_sup12_correct_min": 38,
        "bitext_cal_correct_min": 687,
        "pos_train_added_18_correct_min": 15,
        "boundary_pos_cal_sup12_conf_ge_070_min": 26,
        "boundary_pos_cal_sup12_conf_ge_080_min": 24,
        "boundary_neg_cal_pred_sup12_max": 9,
    },
    "float_drift_and_ceiling_gates": {
        "boundary_pos_cal_delta_mean_max_prob_formula": (
            "<= (0.015 if correct <= 68 else min(0.025, 0.015 + 0.5 * (acc_cand - 68/86))) + tol"
        ),
        "boundary_pos_cal_esc34_delta_mean_max_prob_max": 0.015,
        "boundary_pos_cal_esc34_max_sup12_mass_max": 0.55,
        "boundary_neg_cal_max_sup12_mass_rule": "<= baseline_neg_cal_max_sup12_mass + tol",
        "boundary_neg_cal_max_single_sup12_prob_rule": "<= baseline_neg_cal_max_single_sup12_prob + tol",
    },
}

RELEVANT_SOURCE_PATHS: Tuple[str, ...] = (
    "scripts/run_orig_fit2_return_contrast_prep.py",
    "scripts/run_orig_fit2_return_contrast_fit.py",
    "scripts/run_boundary_contrast_fit.py",
    "pipeline/training/orig_fit2_return_contrast_data.py",
    "pipeline/training/boundary_contrast_data.py",
    "pipeline/training/train_boundary_candidate.py",
    "pipeline/training/train_selective_candidate.py",
    "pipeline/training/train_domain_candidate.py",
    "pipeline/training/boundary_curriculum_data.py",
    "pipeline/training/closure_domain_data.py",
    "pipeline/training/selective_domain_data.py",
    "pipeline/training/domain_templates.py",
    "pipeline/preparation/utils.py",
    "pipeline/evaluation/classifier_acceptance_gate.py",
    "apps/backend/tickets/privacy.py",
    "apps/core_backend/intent/routing.py",
    "apps/core_backend/config/policies/intent_policy.v2.json",
    "data/knowledge/approved_kb.v2.json",
    "apps/ai_service/kb-release.json",
)

UNCHANGED_ORIGINAL_RECIPE_PARAMETERS: Dict[str, Any] = {
    "fit_mode": "fit2_supcon_energy",
    "batch_size": 32,
    "max_length": 64,
    "seed": 42,
    "label_smoothing": 0.03,
    "supcon_weight": 0.25,
    "supcon_temperature": 0.12,
    "neg_kl_weight": 0.80,
    "neg_sup12_ceil_weight": 3.0,
    "neg_sup12_ceil_threshold": 0.18,
    "neg_energy_weight": 0.25,
    "neg_energy_margin": 2.0,
    "neg_repeat": 12,
    "supported12_pos_repeat": 4,
    "escalated34_pos_repeat": 5,
    "replay_per_class": 160,
    "noise_aug_per_class": 80,
    "bitext_cal_per_class": 15,
    "bitext_seed": 20261113,
    "apply_active_kb_audit": False,
    "exclude_noisy_test_overlap": False,
    "min_temperature": 1.0,
    "selective_rejector_enabled": False,
}


def verify_orig_relevant_source_provenance(repo_root: Path) -> Dict[str, Any]:
    """Fail closed if any relevant prep/training/gate/KB/policy file has uncommitted or untracked changes vs HEAD."""
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        raise RuntimeError(f"Expected 40-char HEAD SHA, got {git_sha!r}")

    porcelain = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *RELEVANT_SOURCE_PATHS],
        cwd=str(repo_root),
        text=True,
    ).strip()
    if porcelain:
        raise RuntimeError(f"Uncommitted changes in relevant source files vs HEAD {git_sha}: {porcelain}")

    source_hashes: Dict[str, str] = {}
    for rel in RELEVANT_SOURCE_PATHS:
        p = repo_root / rel
        if not p.is_file():
            raise FileNotFoundError(f"Missing relevant source file: {p}")
        source_hashes[rel] = _sha256_lower(p)
    return {"git_commit": git_sha, "source_hashes": source_hashes}


def verify_git_commit_ancestor(repo_root: Path, ancestor_sha: str, descendant_ref: str = "HEAD") -> str:
    """Verify ancestor_sha is a 40-char commit reachable as an ancestor of descendant_ref (default HEAD)."""
    anc = str(ancestor_sha or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", anc):
        raise ValueError(f"Invalid prep git_commit SHA (expected 40-char hex): {ancestor_sha!r}")

    head_sha = subprocess.check_output(
        ["git", "rev-parse", descendant_ref],
        cwd=str(repo_root),
        text=True,
    ).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise RuntimeError(f"Expected 40-char SHA for {descendant_ref}, got {head_sha!r}")

    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", anc, head_sha],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ValueError(
            f"Locked prep git_commit {anc} is not an ancestor of current HEAD {head_sha}"
            + (f" ({detail})" if detail else "")
        )
    return head_sha


def run_orig_fit2_preflight(
    repo_root: Path,
    dryrun_root: Path,
    *,
    zero_delta_control: bool = False,
) -> Dict[str, Any]:
    """Fail-closed zero-fit preflight verifying baseline anchors, split parity/diff, and isolation."""
    serving_sha = _sha256_lower(SERVING_DIR / "model.safetensors")
    if serving_sha != EXPECTED_SERVING_SHA256:
        raise ValueError(f"Serving weights SHA mismatch: {serving_sha} != {EXPECTED_SERVING_SHA256}")

    fit1_weights = repo_root / FIT1_CHECKPOINT_REL / "model.safetensors"
    if not fit1_weights.exists():
        raise FileNotFoundError(f"Missing Fit1 reference checkpoint: {fit1_weights}")
    fit1_sha = _sha256_lower(fit1_weights)
    if fit1_sha != EXPECTED_FIT1_SHA256:
        raise ValueError(f"Fit1 reference SHA mismatch: {fit1_sha} != {EXPECTED_FIT1_SHA256}")

    init_info = verify_fit2_starting_checkpoint(FIT2_BASELINE_DIR)
    lineage = verify_original_46_label_lineage(repo_root=repo_root)

    if (dryrun_root / "datasets").exists():
        shutil.rmtree(dryrun_root / "datasets")

    splitter = (
        prepare_and_lock_orig_fit2_zero_delta_control_splits
        if zero_delta_control
        else prepare_and_lock_orig_fit2_return_contrast_splits
    )
    lock = splitter(
        worktree_root=repo_root,
        data_repo_root=repo_root,
        init_model_dir=FIT2_BASELINE_DIR,
        artifact_root=dryrun_root,
    )
    ds_dir = dryrun_root / "datasets"
    _verify_dir_matches_lock_hashes(ds_dir, lock["dataset_hashes"])

    bitext_clean = _read_jsonl(ds_dir / "bitext_train_clean.jsonl")
    bitext_noisy = _read_jsonl(ds_dir / "bitext_train_noisy.jsonl")
    replay_intents = {str(r["intent"]) for r in (bitext_clean + bitext_noisy)}
    missing_46 = set(STANDARD_INTENTS_46) - replay_intents
    if missing_46:
        raise RuntimeError(f"Missing labels in Bitext replay: {sorted(missing_46)}")

    return {
        "dry_run": True,
        "fits_executed": 0,
        "optimizer_invoked": False,
        "calibrator_invoked": False,
        "zero_delta_control": zero_delta_control,
        "delta_absent": bool(lock.get("delta_absent", False)),
        "serving_weights_sha256": serving_sha,
        "fit1_reference_weights_sha256": fit1_sha,
        "starting_checkpoint": init_info,
        "canonical_prep": {
            "cleaned_sha256": lineage.cleaned_sha256,
            "splits_sha256": lineage.splits_sha256,
        },
        "extension_version": lock["extension_version"],
        "kb_version": lock["kb_version"],
        "policy_version": lock["policy_version"],
        "kb_rationale": lock.get("kb_rationale"),
        "counts": lock["counts"],
        "dataset_hashes": lock["dataset_hashes"],
        "orig_fit2_stage2_reference_hashes": lock["orig_fit2_stage2_reference_hashes"],
        "new_input_file_hashes": lock["new_input_file_hashes"],
        "baseline_vs_new_diff": lock["baseline_vs_new_diff"],
        "isolation_audit": lock.get("isolation_audit"),
        "token_truncation_audit_max_length_64": lock.get("token_truncation_audit_max_length_64"),
        "historical_baseline_noisy_overlap_disclosure": lock["historical_baseline_noisy_overlap_disclosure"],
    }


def _softmax_float64(logits: np.ndarray, temperature: float) -> np.ndarray:
    """Compute numerically stable float64 post-T softmax probabilities."""
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError(f"Invalid calibration temperature: {temperature}")
    scaled = np.asarray(logits, dtype=np.float64) / float(temperature)
    if scaled.ndim != 2 or scaled.shape[1] != len(STANDARD_INTENTS_46):
        raise ValueError(f"Expected (N, {len(STANDARD_INTENTS_46)}) logits, got {scaled.shape}")
    shifted = scaled - np.max(scaled, axis=1, keepdims=True)
    exp_vals = np.exp(shifted)
    return exp_vals / np.sum(exp_vals, axis=1, keepdims=True)


def _load_cal_guard_surfaces(
    datasets_dir: Path,
    *,
    include_added_18: bool = True,
) -> Dict[str, List[Dict[str, Any]]]:
    """Load exact unpseudonymized CAL surfaces (plus optional added-18 train slice) and verify fixed counts."""
    pos_cal = _read_jsonl(datasets_dir / "boundary_pos_calibration.jsonl")
    neg_cal = _read_jsonl(datasets_dir / "boundary_neg_calibration.jsonl")
    bitext_cal = _read_jsonl(datasets_dir / "bitext_cal.jsonl")
    pos_train = _read_jsonl(datasets_dir / "boundary_pos_train.jsonl")
    added_18 = [r for r in pos_train if str(r.get("sample_id", "")).startswith("orig_ret_ch_")]

    sup12_set = set(SUPPORTED_12_INTENTS)
    esc34_set = set(ESCALATED_34_INTENTS)
    pos_cal_sup12 = [r for r in pos_cal if str(r.get("intent", "")) in sup12_set]
    pos_cal_esc34 = [r for r in pos_cal if str(r.get("intent", "")) in esc34_set]

    expected_counts = {
        k: v for k, v in CAL_GUARD_DENOMINATORS.items() if include_added_18 or k != "pos_train_added_18"
    }
    actual_counts = {
        "boundary_pos_cal": len(pos_cal),
        "boundary_pos_cal_sup12": len(pos_cal_sup12),
        "boundary_pos_cal_esc34": len(pos_cal_esc34),
        "bitext_cal": len(bitext_cal),
        "boundary_neg_cal": len(neg_cal),
    }
    if include_added_18:
        actual_counts["pos_train_added_18"] = len(added_18)
    elif added_18:
        raise ValueError(
            f"Zero-delta control CAL load found unexpected orig_ret_ch_* rows in boundary_pos_train: {len(added_18)}"
        )

    if actual_counts != expected_counts:
        raise ValueError(f"CAL guard surface denominators mismatch: {actual_counts} != {expected_counts}")
    if len(pos_cal_sup12) + len(pos_cal_esc34) != len(pos_cal):
        raise ValueError("boundary_pos_calibration contains intents outside SUPPORTED_12 union ESCALATED_34")
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        "boundary_pos_cal": pos_cal,
        "boundary_neg_cal": neg_cal,
        "bitext_cal": bitext_cal,
    }
    if include_added_18:
        surfaces["pos_train_added_18"] = added_18
    return surfaces


def _summarize_positive_surface(
    probs: np.ndarray,
    rows: Sequence[Dict[str, Any]],
    *,
    idx_by_label: Dict[str, int],
    sup12_indices: np.ndarray,
    include_sup12_conf_counts: bool = False,
    include_max_sup12_mass: bool = False,
) -> Dict[str, Any]:
    """Compute exact integer counts and float64 probability summaries for a positive surface."""
    true_ids = np.array([idx_by_label[str(r["intent"])] for r in rows], dtype=np.int64)
    preds = np.argmax(probs, axis=1)
    max_probs = np.max(probs, axis=1)
    n = len(rows)
    correct = int(np.sum(preds == true_ids))
    summary: Dict[str, Any] = {
        "count": n,
        "correct_count": correct,
        "accuracy": float(correct / n),
        "mean_max_prob": float(np.mean(max_probs)),
    }
    if include_sup12_conf_counts:
        summary["conf_ge_070_count"] = int(np.sum(max_probs >= 0.70))
        summary["conf_ge_080_count"] = int(np.sum(max_probs >= 0.80))
    if include_max_sup12_mass:
        summary["max_sup12_mass"] = float(np.max(np.sum(probs[:, sup12_indices], axis=1)))
    return summary


def _summarize_attribution_slice(
    probs: np.ndarray,
    rows: Sequence[Dict[str, Any]],
    *,
    idx_by_label: Dict[str, int],
    sup12_indices: np.ndarray,
) -> Dict[str, Any]:
    """Freeze reproducible CAL-only confidence decomposition (all vs correct vs incorrect rows)."""
    true_ids = np.array([idx_by_label[str(r["intent"])] for r in rows], dtype=np.int64)
    preds = np.argmax(probs, axis=1)
    corr_mask = preds == true_ids
    incorr_mask = ~corr_mask
    max_probs = np.max(probs, axis=1)
    true_probs = probs[np.arange(len(rows)), true_ids]
    sup12_mass = np.sum(probs[:, sup12_indices], axis=1)
    return {
        "count": len(rows),
        "correct_count": int(np.sum(corr_mask)),
        "incorrect_count": int(np.sum(incorr_mask)),
        "all_mean_max_prob": float(np.mean(max_probs)),
        "correct_mean_max_prob": float(np.mean(max_probs[corr_mask])) if np.any(corr_mask) else None,
        "incorrect_mean_max_prob": float(np.mean(max_probs[incorr_mask])) if np.any(incorr_mask) else None,
        "mean_true_class_prob": float(np.mean(true_probs)),
        "mean_sup12_mass": float(np.mean(sup12_mass)),
    }


def compute_cal_guard_metrics_from_logits(
    logits_by_surface: Dict[str, Any],
    surfaces: Dict[str, List[Dict[str, Any]]],
    *,
    temperature: float = 1.0,
    label_order: Sequence[str] = STANDARD_INTENTS_46,
    include_added_18: bool | None = None,
) -> Dict[str, Any]:
    """Compute all read-only post-T softmax CAL guard metrics (and frozen CAL attribution breakdown)."""
    if list(label_order) != list(STANDARD_INTENTS_46):
        raise ValueError("CAL guard requires canonical 46-intent label ordering")
    use_added_18 = ("pos_train_added_18" in surfaces) if include_added_18 is None else bool(include_added_18)
    idx_by_label = {label: i for i, label in enumerate(label_order)}
    sup12_indices = np.array([idx_by_label[label] for label in SUPPORTED_12_INTENTS], dtype=np.int64)
    sup12_idx_set = set(sup12_indices.tolist())
    sup12_label_set = set(SUPPORTED_12_INTENTS)

    pos_rows = surfaces["boundary_pos_cal"]
    pos_probs = _softmax_float64(np.asarray(logits_by_surface["boundary_pos_cal"]), temperature)
    if pos_probs.shape[0] != len(pos_rows):
        raise ValueError(f"boundary_pos_cal logits/rows mismatch: {pos_probs.shape[0]} != {len(pos_rows)}")

    sup12_mask = np.array([str(r["intent"]) in sup12_label_set for r in pos_rows], dtype=bool)
    esc34_mask = ~sup12_mask
    sup12_rows = [r for r, flag in zip(pos_rows, sup12_mask) if flag]
    esc34_rows = [r for r, flag in zip(pos_rows, esc34_mask) if flag]

    bit_rows = surfaces["bitext_cal"]
    bit_probs = _softmax_float64(np.asarray(logits_by_surface["bitext_cal"]), temperature)
    if bit_probs.shape[0] != len(bit_rows):
        raise ValueError(f"bitext_cal logits/rows mismatch: {bit_probs.shape[0]} != {len(bit_rows)}")

    neg_rows = surfaces["boundary_neg_cal"]
    neg_probs = _softmax_float64(np.asarray(logits_by_surface["boundary_neg_cal"]), temperature)
    if neg_probs.shape[0] != len(neg_rows):
        raise ValueError(f"boundary_neg_cal logits/rows mismatch: {neg_probs.shape[0]} != {len(neg_rows)}")

    neg_preds = np.argmax(neg_probs, axis=1)
    neg_sup12_probs = neg_probs[:, sup12_indices]
    neg_sup12_mass = np.sum(neg_sup12_probs, axis=1)

    metrics: Dict[str, Any] = {
        "temperature": float(temperature),
        "boundary_pos_cal": _summarize_positive_surface(pos_probs, pos_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices),
        "boundary_pos_cal_sup12": _summarize_positive_surface(
            pos_probs[sup12_mask],
            sup12_rows,
            idx_by_label=idx_by_label,
            sup12_indices=sup12_indices,
            include_sup12_conf_counts=True,
        ),
        "boundary_pos_cal_esc34": _summarize_positive_surface(
            pos_probs[esc34_mask],
            esc34_rows,
            idx_by_label=idx_by_label,
            sup12_indices=sup12_indices,
            include_max_sup12_mass=True,
        ),
        "bitext_cal": _summarize_positive_surface(bit_probs, bit_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices),
        "boundary_neg_cal": {
            "count": len(neg_rows),
            "pred_sup12_count": int(sum(int(p) in sup12_idx_set for p in neg_preds)),
            "max_sup12_mass": float(np.max(neg_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_sup12_probs)),
        },
        "attribution_breakdown": {
            "schema_version": "cal_attribution_breakdown.v1",
            "surface_note": (
                "Reproducible CAL-only confidence decomposition distinguishing all-rows mean_max_prob "
                "from correct-only and incorrect-only mean_max_prob (addresses C mean_max_prob caveat)."
            ),
            "boundary_pos_cal": _summarize_attribution_slice(
                pos_probs, pos_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
            ),
            "boundary_pos_cal_sup12": _summarize_attribution_slice(
                pos_probs[sup12_mask], sup12_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
            ),
            "boundary_pos_cal_esc34": _summarize_attribution_slice(
                pos_probs[esc34_mask], esc34_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
            ),
            "bitext_cal": _summarize_attribution_slice(
                bit_probs, bit_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
            ),
        },
    }
    if use_added_18:
        added_rows = surfaces["pos_train_added_18"]
        added_probs = _softmax_float64(np.asarray(logits_by_surface["pos_train_added_18"]), temperature)
        if added_probs.shape[0] != len(added_rows):
            raise ValueError(f"pos_train_added_18 logits/rows mismatch: {added_probs.shape[0]} != {len(added_rows)}")
        metrics["pos_train_added_18"] = _summarize_positive_surface(
            added_probs, added_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
        )
    return metrics


def evaluate_cal_guard_metrics_for_model(
    model_dir: Path,
    datasets_dir: Path,
    *,
    batch_size: int = 128,
    include_added_18: bool = True,
) -> Dict[str, Any]:
    """Run strictly read-only forward inference over locked CAL (and optional added-train) raw texts."""
    cal_path = model_dir / "calibration_manifest.json"
    cal_manifest = json.loads(cal_path.read_text(encoding="utf-8"))
    cal_block = cal_manifest.get("calibration") or {}
    temperature = float(cal_block.get("temperature", cal_manifest.get("temperature", float("nan"))))
    min_temp = float(cal_block.get("min_temperature", 1.0))
    if not math.isfinite(temperature) or temperature < min_temp or temperature <= 0.0:
        raise ValueError(f"Invalid calibration temperature {temperature} in {cal_path}")

    tok_cfg = cal_manifest.get("tokenization") or {}
    max_length = int(tok_cfg.get("max_length", 64))
    label_space = cal_manifest.get("label_space") or {}
    id2label = label_space.get("id2label") or {}
    label_order = [id2label.get(str(i)) for i in range(len(STANDARD_INTENTS_46))]
    if label_order != list(STANDARD_INTENTS_46):
        raise ValueError(f"calibration_manifest id2label does not match STANDARD_INTENTS_46 in {cal_path}")

    surfaces = _load_cal_guard_surfaces(datasets_dir, include_added_18=include_added_18)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True)
    model.to(device)
    model.eval()

    model_id2label = {int(k): v for k, v in (model.config.id2label or {}).items()}
    if [model_id2label.get(i) for i in range(len(STANDARD_INTENTS_46))] != list(STANDARD_INTENTS_46):
        raise ValueError(f"Model config id2label does not match STANDARD_INTENTS_46 in {model_dir}")

    logits_by_surface: Dict[str, np.ndarray] = {}
    with torch.no_grad():
        for name, rows in surfaces.items():
            texts = [str(r["text"]) for r in rows]
            chunks: List[np.ndarray] = []
            for start in range(0, len(texts), batch_size):
                enc = tokenizer(
                    texts[start : start + batch_size],
                    max_length=max_length,
                    padding="max_length",
                    truncation=True,
                    return_tensors="pt",
                )
                enc = {k: v.to(device) for k, v in enc.items()}
                logits = model(**enc).logits.detach().cpu().numpy().astype(np.float64)
                chunks.append(logits)
            logits_by_surface[name] = np.vstack(chunks)

    metrics = compute_cal_guard_metrics_from_logits(
        logits_by_surface,
        surfaces,
        temperature=temperature,
        label_order=label_order,
        include_added_18=include_added_18,
    )
    metrics["evaluation_metadata"] = {
        "model_dir": str(model_dir),
        "weights_sha256": _sha256_lower(model_dir / "model.safetensors"),
        "calibration_manifest_sha256": _sha256_lower(cal_path),
        "max_length": max_length,
        "device": str(device),
    }
    return metrics


def _opt_diff(a: float | None, b: float | None) -> float | None:
    return None if (a is None or b is None) else float(a) - float(b)


def evaluate_cal_guard_report(
    candidate_metrics: Dict[str, Any],
    baseline_metrics: Dict[str, Any],
    *,
    float_tolerance: float = CAL_GUARD_FLOAT_TOLERANCE,
    cal_guard_mode: str = "candidate",
) -> Dict[str, Any]:
    """Evaluate CAL guard checks ('candidate': all 12 checks; 'control': same 11 non-extension checks)."""
    if cal_guard_mode not in ("candidate", "control"):
        raise ValueError(f"Unsupported cal_guard_mode={cal_guard_mode!r}; expected 'candidate' or 'control'")

    c_pos = candidate_metrics["boundary_pos_cal"]
    c_sup12 = candidate_metrics["boundary_pos_cal_sup12"]
    c_esc34 = candidate_metrics["boundary_pos_cal_esc34"]
    c_bit = candidate_metrics["bitext_cal"]
    c_neg = candidate_metrics["boundary_neg_cal"]

    b_pos = baseline_metrics["boundary_pos_cal"]
    b_esc34 = baseline_metrics["boundary_pos_cal_esc34"]
    b_neg = baseline_metrics["boundary_neg_cal"]

    pos_correct = int(c_pos["correct_count"])
    pos_acc = pos_correct / float(CAL_GUARD_DENOMINATORS["boundary_pos_cal"])
    base_pos_acc_floor = 68.0 / float(CAL_GUARD_DENOMINATORS["boundary_pos_cal"])
    pos_cal_allowed_delta = (
        0.015 if pos_correct <= 68 else min(0.025, 0.015 + 0.5 * (pos_acc - base_pos_acc_floor))
    )
    pos_cal_delta = float(c_pos["mean_max_prob"]) - float(b_pos["mean_max_prob"])
    esc34_delta = float(c_esc34["mean_max_prob"]) - float(b_esc34["mean_max_prob"])

    checks: List[Dict[str, Any]] = [
        {
            "name": "boundary_pos_cal_correct_count",
            "kind": "integer",
            "actual": pos_correct,
            "rule": ">= 68",
            "passed": pos_correct >= 68,
        },
        {
            "name": "boundary_pos_cal_sup12_correct_count",
            "kind": "integer",
            "actual": int(c_sup12["correct_count"]),
            "rule": ">= 38",
            "passed": int(c_sup12["correct_count"]) >= 38,
        },
        {
            "name": "bitext_cal_correct_count",
            "kind": "integer",
            "actual": int(c_bit["correct_count"]),
            "rule": ">= 687",
            "passed": int(c_bit["correct_count"]) >= 687,
        },
    ]
    if cal_guard_mode == "candidate":
        c_added = candidate_metrics["pos_train_added_18"]
        checks.append(
            {
                "name": "pos_train_added_18_correct_count",
                "kind": "integer",
                "actual": int(c_added["correct_count"]),
                "rule": ">= 15",
                "passed": int(c_added["correct_count"]) >= 15,
            }
        )
    checks.extend(
        [
            {
                "name": "boundary_pos_cal_sup12_conf_ge_070_count",
                "kind": "integer",
                "actual": int(c_sup12["conf_ge_070_count"]),
                "rule": ">= 26",
                "passed": int(c_sup12["conf_ge_070_count"]) >= 26,
            },
            {
                "name": "boundary_pos_cal_sup12_conf_ge_080_count",
                "kind": "integer",
                "actual": int(c_sup12["conf_ge_080_count"]),
                "rule": ">= 24",
                "passed": int(c_sup12["conf_ge_080_count"]) >= 24,
            },
            {
                "name": "boundary_neg_cal_pred_sup12_count",
                "kind": "integer",
                "actual": int(c_neg["pred_sup12_count"]),
                "rule": "<= 9",
                "passed": int(c_neg["pred_sup12_count"]) <= 9,
            },
            {
                "name": "boundary_pos_cal_delta_mean_max_prob",
                "kind": "float",
                "actual": pos_cal_delta,
                "limit": pos_cal_allowed_delta,
                "tolerance": float_tolerance,
                "passed": pos_cal_delta <= pos_cal_allowed_delta + float_tolerance,
            },
            {
                "name": "boundary_pos_cal_esc34_delta_mean_max_prob",
                "kind": "float",
                "actual": esc34_delta,
                "limit": 0.015,
                "tolerance": float_tolerance,
                "passed": esc34_delta <= 0.015 + float_tolerance,
            },
            {
                "name": "boundary_pos_cal_esc34_max_sup12_mass",
                "kind": "float",
                "actual": float(c_esc34["max_sup12_mass"]),
                "limit": 0.55,
                "tolerance": float_tolerance,
                "passed": float(c_esc34["max_sup12_mass"]) <= 0.55 + float_tolerance,
            },
            {
                "name": "boundary_neg_cal_max_sup12_mass",
                "kind": "float",
                "actual": float(c_neg["max_sup12_mass"]),
                "limit": float(b_neg["max_sup12_mass"]),
                "tolerance": float_tolerance,
                "passed": float(c_neg["max_sup12_mass"]) <= float(b_neg["max_sup12_mass"]) + float_tolerance,
            },
            {
                "name": "boundary_neg_cal_max_single_sup12_prob",
                "kind": "float",
                "actual": float(c_neg["max_single_sup12_prob"]),
                "limit": float(b_neg["max_single_sup12_prob"]),
                "tolerance": float_tolerance,
                "passed": float(c_neg["max_single_sup12_prob"]) <= float(b_neg["max_single_sup12_prob"]) + float_tolerance,
            },
        ]
    )

    failed_checks = [c["name"] for c in checks if not c["passed"]]
    passed = len(failed_checks) == 0
    if cal_guard_mode == "control":
        recommended_status = (
            "CONTROL_CAL_NO_REGRESSION_SCIENTIFIC_ONLY"
            if passed
            else "CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED"
        )
    else:
        recommended_status = (
            "CAL_GUARD_PASS_READY_FOR_C_EVAL" if passed else "CAL_GUARD_REJECT_DO_NOT_PROMOTE"
        )

    c_attr = candidate_metrics.get("attribution_breakdown") or {}
    b_attr = baseline_metrics.get("attribution_breakdown") or {}
    attribution_deltas: Dict[str, Any] = {}
    for sname in ("boundary_pos_cal", "boundary_pos_cal_sup12", "boundary_pos_cal_esc34", "bitext_cal"):
        cs = c_attr.get(sname)
        bs = b_attr.get(sname)
        if cs and bs:
            attribution_deltas[sname] = {
                "delta_correct_count": int(cs["correct_count"]) - int(bs["correct_count"]),
                "delta_all_mean_max_prob": _opt_diff(cs.get("all_mean_max_prob"), bs.get("all_mean_max_prob")),
                "delta_correct_mean_max_prob": _opt_diff(cs.get("correct_mean_max_prob"), bs.get("correct_mean_max_prob")),
                "delta_incorrect_mean_max_prob": _opt_diff(
                    cs.get("incorrect_mean_max_prob"), bs.get("incorrect_mean_max_prob")
                ),
                "delta_mean_true_class_prob": _opt_diff(cs.get("mean_true_class_prob"), bs.get("mean_true_class_prob")),
            }

    return {
        "schema_version": "orig_fit2_cal_guard_report.v1",
        "cal_guard_mode": "matched_zero_delta_control_11_checks" if cal_guard_mode == "control" else "candidate_12_checks",
        "is_promotion_candidate": cal_guard_mode != "control",
        "read_only_post_fit_guard": True,
        "float_tolerance": float_tolerance,
        "passed": passed,
        "recommended_status": recommended_status,
        "failed_checks": failed_checks,
        "checks": checks,
        "deltas": {
            "boundary_pos_cal_delta_mean_max_prob": pos_cal_delta,
            "boundary_pos_cal_allowed_delta_mean_max_prob": pos_cal_allowed_delta,
            "boundary_pos_cal_esc34_delta_mean_max_prob": esc34_delta,
        },
        "attribution_deltas": attribution_deltas,
        "candidate_metrics": candidate_metrics,
        "baseline_metrics": baseline_metrics,
    }


def _format_lr_cli(lr: float) -> str:
    if lr == 5e-6:
        return "5e-6"
    if lr == 2e-5:
        return "2e-5"
    if lr == 5e-5:
        return "5e-5"
    if lr == 1e-4:
        return "1e-4"
    return str(lr)


def _snapshot_init_freeze_component_hashes(model_dir: Path, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Load baseline model read-only in eval mode and snapshot frozen component + tensor SHA-256 digests."""
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()
    scope_info = _configure_trainable_scope(
        model,
        str(cfg["trainable_scope"]),
        expected_trainable_param_count=int(cfg["expected_trainable_param_count"]),
        expected_frozen_param_count=int(cfg["expected_frozen_param_count"]),
    )
    snap = _snapshot_frozen_component_hashes(model)
    return {
        "trainable_param_count": scope_info["trainable_param_count"],
        "frozen_param_count": scope_info["frozen_param_count"],
        "trainable_param_names": scope_info["trainable_param_names"],
        "initial_frozen_tensors_sha256": snap["all_frozen_tensors_sha256"],
        "initial_freeze_component_hashes": snap["component_hashes"],
    }


def _build_planned_execution_plan(
    *,
    profile_name: str,
    prep_records_dir: Path,
    planned_fit_run_id: str,
    planned_future_paths: Dict[str, str],
    experiment_mode: str = "return_contrast",
) -> Dict[str, Any]:
    """Document the sole authorized runner CLI and locked profile hyperparameters."""
    if profile_name not in AUTHORIZED_FIT_PROFILES:
        raise ValueError(f"Unsupported profile {profile_name!r}; expected one of {sorted(AUTHORIZED_FIT_PROFILES)}")
    if experiment_mode not in ("return_contrast", "zero_delta_control"):
        raise ValueError(f"Unsupported experiment_mode {experiment_mode!r}")
    if experiment_mode == "zero_delta_control" and profile_name != "option_a":
        raise ValueError(f"zero_delta_control requires profile_name='option_a'; got {profile_name!r}")

    cfg = AUTHORIZED_FIT_PROFILES[profile_name]
    is_teacher_kl = profile_name in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic")
    is_det_teacher_kl = profile_name == "option_a_teacher_kl_deterministic"
    is_subhead = profile_name in SUBHEAD_FIT_PROFILES
    run_flag = (
        "--run-authorized-fit"
        if (experiment_mode == "zero_delta_control" or profile_name != "option_a")
        else "--run-option-a-fit"
    )
    planned_cli = [
        ".venv/Scripts/python.exe",
        "-m",
        "scripts.run_orig_fit2_return_contrast_fit",
        "--prep-dir",
        str(prep_records_dir),
        "--run-id",
        planned_fit_run_id,
        "--profile",
        profile_name,
        "--epochs",
        str(cfg["epochs"]),
        "--lr",
        _format_lr_cli(float(cfg["lr"])),
        "--batch-size",
        str(cfg["batch_size"]),
        "--seed",
        str(cfg["seed"]),
        "--fit-mode",
        str(cfg["fit_mode"]),
    ]
    if is_teacher_kl:
        planned_cli.extend(
            [
                "--teacher-kl-weight",
                str(cfg["teacher_kl_weight"]),
                "--teacher-temperature",
                str(cfg["teacher_temperature"]),
                "--teacher-weights-sha256",
                str(cfg["teacher_weights_sha256"]),
            ]
        )
        if is_det_teacher_kl:
            planned_cli.extend(
                [
                    "--teacher-student-anchor-mode",
                    str(cfg["teacher_student_anchor_mode"]),
                ]
            )
    if is_subhead:
        planned_cli.extend(
            [
                "--weight-decay",
                str(cfg["weight_decay"]),
                "--trainable-scope",
                str(cfg["trainable_scope"]),
                "--feature-dropout-eval-mode",
            ]
        )
    planned_cli.append(run_flag)
    is_control = experiment_mode == "zero_delta_control"
    if is_control:
        caveat = (
            "Matched zero-delta scientific control ONLY (is_promotion_candidate=False): warm-starts Original Fit2 "
            "(f695b1fe...) for epochs=3, lr=2e-5 on bit-identical 13 original stage2_inputs (11,320 full_train rows, "
            "181 boundary_pos_train rows, 13,000 effective rows; 0 added return-contrast rows) to isolate continuation "
            "optimization drift from the +18-row data delta. NOT a promotion candidate."
        )
    elif profile_name == "option_a_pre_classifier_head_v1":
        caveat = (
            "Original Fit2 (f695b1fe...) trained from Fit1 (95a940b6...) with epochs=3, lr=2e-5. "
            "option_a_pre_classifier_head_v1 freezes embeddings + all 6 transformer layers + dropout (66,362,880 params "
            "+ 1 buffer in deterministic .eval() with dropout off) and trains pre_classifier + classifier (625,966 "
            "params) with AdamW(lr=5e-5, weight_decay=0.01), epochs=3, batch_size=32, seed=42 on untouched L_pos + L_neg "
            "(SupCon inactive on frozen encoder; no teacher KL/tether/LoRA). Multi-factor change (architecture + lr + "
            "epochs at n=1, 3 historical noisy overlaps preserved) and high feature-geometry risk (0/8 "
            "return_product_in_store 1-NN in h_cls); FINAL Attempt 2/2 -> permanent STOP if CAL < 12/12."
        )
    elif profile_name == "option_a_classifier_head_only_v1":
        caveat = (
            "Original Fit2 (f695b1fe...) trained from Fit1 (95a940b6...) with epochs=3, lr=2e-5. "
            "option_a_classifier_head_only_v1 locks frozen embeddings + 6 transformer layers + pre_classifier "
            "(66,953,472 params in deterministic .eval() with dropout p=0.2 off) and trains ONLY classifier.weight/"
            "classifier.bias (35,374 params) with AdamW(lr=1e-4, weight_decay=0.01), epochs=2, batch_size=32, seed=42 "
            "on untouched L_pos + L_neg (SupCon has zero head gradient and is inactive; no teacher KL/tether/LoRA). "
            "Compares architecture constraint + matched locked recipe exploratory (Attempt 1/2 pending release, NOT "
            "a single-factor randomized cause); frozen feature geometry sits at 0/8 return_product_in_store 1-NN/centroid "
            "match on added_18 (does not prove impossibility, high risk of linear-separability ceiling -> hard EARLY STOP "
            "if accuracy/separation gates fail)."
        )
    elif is_det_teacher_kl:
        caveat = (
            "Original Fit2 (f695b1fe...) was trained from Fit1 (95a940b6...) for epochs=3, lr=2e-5. "
            "option_a_teacher_kl_deterministic warm-starts from Original Fit2 at lr=2e-5, epochs=3 over 13,080 "
            "effective TRAIN rows with base pos_ce+supcon+neg on stochastic model.train() and masked teacher-KL "
            "(alpha_kl=1.0, T_teacher=1.0, 13,000 canonical anchored / 80 added orig_ret_ch_* masked off) evaluated on "
            "a separate deterministic model.eval() student forward (autograd ON, no dropout). Addresses step-0 dropout "
            "noise only under an n=1 exploratory alpha_kl=1.0 budget; does not guarantee CAL or holdout pass."
        )
    elif is_teacher_kl:
        caveat = (
            "Original Fit2 (f695b1fe...) was trained from Fit1 (95a940b6...) for epochs=3, lr=2e-5. "
            "option_a_teacher_kl warm-starts from Original Fit2 at lr=2e-5, epochs=3 over 13,080 effective TRAIN rows "
            "with frozen Original Fit2 masked teacher-KL (alpha_kl=1.0, T_teacher=1.0) on 13,000 canonical replay rows "
            "(m=1) and masked off on the 80 effective added orig_ret_ch_* rows (m=0). alpha_kl=1.0 is exploratory "
            "under a one-run budget (not pre-validated as optimal); direct comparison against untouched Original Fit2 "
            "remains a comparative candidate evaluation."
        )
    else:
        caveat = (
            f"Original Fit2 (f695b1fe...) was trained from Fit1 (95a940b6...) for epochs=3, lr=2e-5. "
            f"Warm-starting {profile_name} continuation (lr={_format_lr_cli(float(cfg['lr']))}) from converged "
            "Fit2 applies 3 additional full epochs over 13,080 effective rows on top of f695b1fe...; direct "
            "comparison against untouched Original Fit2 is a comparative candidate evaluation, NOT a matched "
            "causal control."
        )
    plan: Dict[str, Any] = {
        "experiment_mode": "matched_zero_delta_control" if is_control else "return_contrast",
        "is_promotion_candidate": not is_control,
        "profile": profile_name,
        "selected_recipe": cfg["selected_recipe"],
        "epochs": cfg["epochs"],
        "lr": cfg["lr"],
        "batch_size": cfg["batch_size"],
        "seed": cfg["seed"],
        "fit_mode": cfg["fit_mode"],
        "min_temperature": cfg["min_temperature"],
        "enable_selective_rejector": cfg["enable_selective_rejector"],
        "init_weights_sha256": cfg["init_weights_sha256"],
        "planned_cli": planned_cli,
        "planned_future_paths": planned_future_paths,
        "authorized_to_train_now": False,
        "requires_worker_b_re_review_pass_and_coordinator_release": True,
        "causal_control_caveat": caveat,
    }
    if is_teacher_kl:
        plan["teacher_kl_weight"] = cfg["teacher_kl_weight"]
        plan["teacher_temperature"] = cfg["teacher_temperature"]
        plan["teacher_weights_sha256"] = cfg["teacher_weights_sha256"]
        if is_det_teacher_kl:
            plan["teacher_student_anchor_mode"] = cfg["teacher_student_anchor_mode"]
    if is_subhead:
        plan["weight_decay"] = cfg["weight_decay"]
        plan["trainable_scope"] = cfg["trainable_scope"]
        plan["feature_dropout_eval_mode"] = cfg["feature_dropout_eval_mode"]
        plan["expected_trainable_param_count"] = cfg["expected_trainable_param_count"]
        plan["expected_frozen_param_count"] = cfg["expected_frozen_param_count"]
        plan["budget_attempt_label"] = (
            "Attempt_2_of_2_final_pending_coordinator_release"
            if profile_name == "option_a_pre_classifier_head_v1"
            else "Attempt_1_of_2_pending_coordinator_release"
        )
    return plan


def _build_planned_option_a_plan(
    *,
    prep_records_dir: Path,
    planned_fit_run_id: str,
    planned_future_paths: Dict[str, str],
) -> Dict[str, Any]:
    """Backwards-compatible wrapper returning the locked Option A (lr=2e-5) execution plan."""
    return _build_planned_execution_plan(
        profile_name="option_a",
        prep_records_dir=prep_records_dir,
        planned_fit_run_id=planned_fit_run_id,
        planned_future_paths=planned_future_paths,
    )


def _archive_orig_fit2_prep_bundle(
    *,
    dest_dir: Path,
    repo_root: Path,
    dryrun_root: Path,
    preflight: Dict[str, Any],
    source_prov: Dict[str, Any],
    prep_run_id: str,
    planned_fit_run_id: str,
    planned_future_paths: Dict[str, str],
    profile_name: str = DEFAULT_PREP_PROFILE,
    experiment_mode: str = "return_contrast",
) -> None:
    """Write immutable zero-fit prep bundle with actual input snapshots, baseline CAL reference, and SHA inventory."""
    if profile_name not in AUTHORIZED_FIT_PROFILES:
        raise ValueError(f"Unsupported profile {profile_name!r}; expected one of {sorted(AUTHORIZED_FIT_PROFILES)}")
    if experiment_mode not in ("return_contrast", "zero_delta_control"):
        raise ValueError(f"Unsupported experiment_mode {experiment_mode!r}")
    if experiment_mode == "zero_delta_control" and profile_name != "option_a":
        raise ValueError(f"zero_delta_control requires profile_name='option_a'; got {profile_name!r}")

    is_control = experiment_mode == "zero_delta_control"
    dest_dir.mkdir(parents=True, exist_ok=False)
    (dest_dir / "status.json").write_text(
        json.dumps({"status": "preparing", "fits_executed": 0}, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        shutil.copytree(dryrun_root / "datasets", dest_dir / "datasets")
        _verify_dir_matches_lock_hashes(dest_dir / "datasets", preflight["dataset_hashes"])
        root_copies = (
            ("dataset_lock_manifest.json",)
            if is_control
            else ("dataset_lock_manifest.json", "orig_fit2_return_contrast_extension.jsonl")
        )
        for root_copy in root_copies:
            shutil.copy2(dest_dir / "datasets" / root_copy, dest_dir / root_copy)
        if is_control and (dest_dir / "datasets" / "orig_fit2_return_contrast_extension.jsonl").exists():
            raise ValueError("zero_delta_control datasets/ must NOT contain orig_fit2_return_contrast_extension.jsonl")

        snap_dir = dest_dir / "source_snapshot"
        for rel, exp_sha in source_prov["source_hashes"].items():
            dst = snap_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_root / rel, dst)
            if _sha256_lower(dst) != exp_sha:
                raise ValueError(f"Source snapshot SHA mismatch for {rel}")

        (dest_dir / "environment.json").write_text(
            json.dumps(
                {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "torch": torch.__version__,
                    "cuda_available": torch.cuda.is_available(),
                    "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                    "transformers": transformers.__version__,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        orig_prov_path = FIT2_BASELINE_DIR / "candidate_provenance_manifest.json"
        orig_cal_path = FIT2_BASELINE_DIR / "calibration_manifest.json"
        orig_cal_sha = _sha256_lower(orig_cal_path)
        baseline_cal_metrics = evaluate_cal_guard_metrics_for_model(
            FIT2_BASELINE_DIR,
            dest_dir / "datasets",
            include_added_18=not is_control,
        )

        execution_plan = _build_planned_execution_plan(
            profile_name=profile_name,
            prep_records_dir=dest_dir,
            planned_fit_run_id=planned_fit_run_id,
            planned_future_paths=planned_future_paths,
            experiment_mode=experiment_mode,
        )
        if is_control:
            cal_guard_def = {
                "schema_version": "orig_fit2_zero_delta_control_cal_guard_def.v1",
                "cal_guard_mode": "matched_zero_delta_control_11_checks",
                "is_promotion_candidate": False,
                "surface": CAL_GUARD_DEFINITION["surface"],
                "denominators": {
                    k: v for k, v in CAL_GUARD_DENOMINATORS.items() if k != "pos_train_added_18"
                },
                "float_tolerance": CAL_GUARD_FLOAT_TOLERANCE,
                "float_tolerance_justification": CAL_GUARD_DEFINITION["float_tolerance_justification"],
                "integer_count_gates": {
                    k: v
                    for k, v in CAL_GUARD_DEFINITION["integer_count_gates"].items()
                    if k != "pos_train_added_18_correct_min"
                },
                "float_drift_and_ceiling_gates": dict(CAL_GUARD_DEFINITION["float_drift_and_ceiling_gates"]),
                "omitted_check": "pos_train_added_18_correct_count (extension data strictly absent by design)",
                "mean_max_prob_caveat": (
                    "_summarize_positive_surface computes mean_max_prob over ALL rows regardless of prediction "
                    "correctness; attribution_breakdown additionally records correct_mean_max_prob, "
                    "incorrect_mean_max_prob, mean_true_class_prob, and mean_sup12_mass without changing "
                    "the 11 non-extension CAL acceptance checks or thresholds."
                ),
            }
        else:
            cal_guard_def = CAL_GUARD_DEFINITION

        manifest = {
            "schema_version": (
                "orig_fit2_zero_delta_control_prep.v1" if is_control else "orig_fit2_return_contrast_prep.v4"
            ),
            "experiment_mode": "matched_zero_delta_control" if is_control else "return_contrast",
            "is_promotion_candidate": not is_control,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "git_commit": source_prov["git_commit"],
            "source_hashes": source_prov["source_hashes"],
            "cli_argv": list(sys.argv),
            "planned_prep_run_id": prep_run_id,
            "planned_future_fit_run_id": planned_fit_run_id,
            "authorized_fit_profile": dict(AUTHORIZED_FIT_PROFILES[profile_name]),
            "baseline_original_fit2": {
                "checkpoint_dir": str(FIT2_BASELINE_DIR),
                "model_safetensors_sha256": EXPECTED_FIT2_SHA256,
                "fit1_initializer_dir": str(repo_root / FIT1_CHECKPOINT_REL),
                "fit1_model_safetensors_sha256": EXPECTED_FIT1_SHA256,
                "faithful_stage2_records_dir": str(repo_root / ORIG_FAITHFUL_RECORDS_REL),
                "calibration_manifest_sha256": orig_cal_sha,
                "provenance_manifest_sha256": _sha256_lower(orig_prov_path),
                "temperature": 1.0,
                "min_temperature": 1.0,
                "selective_rejector_enabled": False,
            },
            "baseline_cal_reference": {
                "baseline_model_dir": str(FIT2_BASELINE_DIR),
                "baseline_weights_sha256": EXPECTED_FIT2_SHA256,
                "baseline_calibration_manifest_sha256": orig_cal_sha,
                "dataset_hashes": preflight["dataset_hashes"],
                "cal_guard_definition": cal_guard_def,
                "metrics": baseline_cal_metrics,
            },
            "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
            "execution_plan": execution_plan,
            "preflight": preflight,
        }
        if is_control:
            manifest["historical_token_truncation_audit_note"] = (
                "For this zero-delta control, token_truncation_audit_max_length_64.train_all is truthfully 11320 "
                "(matching full_train_split.jsonl=11320, boundary_pos_train.jsonl=181, effective=13000). "
                "Sealed historical candidates fit-v1 and lr5e6-v1 logged token_truncation_audit.train_all=11320 "
                "alongside 11338 actual input rows because train_boundary_candidate.py (line 1260) reads the static "
                "token_truncation_audit_max_length_64 metadata inherited into dataset_lock_manifest.json (cosmetic "
                "provenance mismatch only; training actually tokenized all 11338 rows; sealed archives untouched)."
            )
        if profile_name == "option_a":
            manifest["option_a_execution_plan"] = execution_plan
        elif profile_name in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic"):
            cfg_tkl = AUTHORIZED_FIT_PROFILES[profile_name]
            tkl_manifest_block: Dict[str, Any] = {
                "enabled": True,
                "teacher_checkpoint_dir": str(FIT2_BASELINE_DIR),
                "teacher_weights_sha256": cfg_tkl["teacher_weights_sha256"],
                "teacher_kl_weight": float(cfg_tkl["teacher_kl_weight"]),
                "teacher_temperature": float(cfg_tkl["teacher_temperature"]),
                "loss_scope": "TRAIN_ONLY_NO_CAL_OR_EVAL",
                "loss_formula": "1.0 * KL(p_teacher || p_student), normalized by sum(m_i) on active batch anchors (0.0 if sum(m_i)==0)",
                "mask_provenance_source": "orig_fit2_return_contrast_extension.jsonl:sample_id (orig_ret_ch_*)",
                "anchor_effective_count": 13000,
                "excluded_effective_count": 80,
                "excluded_raw_count": 18,
                "exploratory_coefficient_caveat": (
                    "alpha_kl=1.0 is an exploratory single-run regularization coefficient, not pre-validated as optimal; "
                    "base teacher accuracy on the 80 effective added rows is 40.0%."
                ),
            }
            if profile_name == "option_a_teacher_kl_deterministic":
                tkl_manifest_block["teacher_student_anchor_mode"] = cfg_tkl["teacher_student_anchor_mode"]
                tkl_manifest_block["loss_formula"] = (
                    "1.0 * KL(p_teacher || p_student_eval_det), deterministic dropout-disabled student forward "
                    "(autograd ON) normalized by sum(m_i) on active batch anchors (0.0 if sum(m_i)==0)"
                )
            manifest["teacher_anchor_config"] = tkl_manifest_block
        elif profile_name in SUBHEAD_FIT_PROFILES:
            cfg_head = AUTHORIZED_FIT_PROFILES[profile_name]
            init_freeze = _snapshot_init_freeze_component_hashes(FIT2_BASELINE_DIR, cfg_head)
            is_final_attempt = profile_name == "option_a_pre_classifier_head_v1"
            attempt_label = (
                "Attempt_2_of_2_final_pending_coordinator_release"
                if is_final_attempt
                else "Attempt_1_of_2_pending_coordinator_release"
            )
            geom_disclosure = (
                "Read-only Worker B audit on f695b1fe h_cls features found 0/8 added return_product_in_store 1-NN to "
                "canonical return_product_in_store (high geometry risk -> permanent STOP if CAL < 12/12)."
                if is_final_attempt
                else "Read-only Worker B audit on f695b1fe eval() features found 8/18 added_18 match canonical "
                "1-NN/centroid (8/10 return_policy, 0/8 return_product_in_store). Does not prove impossibility, "
                "but exposes high risk of linear-separability ceiling -> hard EARLY STOP on accuracy/separation fail."
            )
            manifest[SUBHEAD_PROFILE_MANIFEST_KEYS[profile_name]] = {
                "enabled": True,
                "trainable_scope": str(cfg_head["trainable_scope"]),
                "feature_dropout_eval_mode": bool(cfg_head["feature_dropout_eval_mode"]),
                "weight_decay": float(cfg_head["weight_decay"]),
                "teacher_used": False,
                "teacher_kl_weight": 0.0,
                "supcon_inactive_under_frozen_encoder": True,
                "budget_attempt_label": attempt_label,
                "budget_consumed_by_prep": 0,
                "feature_geometry_risk_disclosure": geom_disclosure,
                **init_freeze,
            }
        (dest_dir / "prep_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        status_payload: Dict[str, Any] = {"status": "complete", "fits_executed": 0, "prep_archive": True}
        if profile_name in SUBHEAD_FIT_PROFILES:
            status_payload["budget_attempt_label"] = attempt_label
            status_payload["budget_consumed_by_prep"] = 0
        (dest_dir / "status.json").write_text(json.dumps(status_payload, indent=2) + "\n", encoding="utf-8")
        _write_and_verify_sha_inventory(dest_dir, "sidecar_sha_inventory.json")
    except Exception as exc:
        (dest_dir / "status.json").write_text(
            json.dumps({"status": "incomplete", "fits_executed": 0, "error": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description="Strictly zero-fit prep for Original Fit2 single-factor return-channel contrast")
    ap.add_argument("--dry-run", action="store_true", help="Run fail-closed zero-fit preflight validation only")
    ap.add_argument("--archive-prep", action="store_true", help="Archive immutable zero-fit -prep bundle in MAIN")
    ap.add_argument("--run-id", default=DEFAULT_PREP_RUN_ID)
    ap.add_argument("--fit-run-id", default=DEFAULT_PLANNED_FIT_RUN_ID)
    ap.add_argument("--profile", default=DEFAULT_PREP_PROFILE, choices=tuple(AUTHORIZED_FIT_PROFILES.keys()))
    ap.add_argument(
        "--experiment-mode",
        default="return_contrast",
        choices=("return_contrast", "zero_delta_control"),
        help="Prep dataset mode: return_contrast (+18 rows) or zero_delta_control (bit-identical 13 orig stage2_inputs)",
    )
    args = ap.parse_args()

    if not args.dry_run and not args.archive_prep:
        raise ValueError("Specify --dry-run and/or --archive-prep (this script performs zero training fits)")
    if args.experiment_mode == "zero_delta_control" and args.profile != "option_a":
        raise ValueError(f"--experiment-mode zero_delta_control requires --profile option_a (lr=2e-5); got {args.profile!r}")

    repo_root = Path(__file__).resolve().parents[1]
    dryrun_root = (
        LOCAL_ORIG_CONTRAST_ROOT / f"dryrun-{args.run_id}"
        if (args.experiment_mode == "zero_delta_control" or args.run_id != DEFAULT_PREP_RUN_ID)
        else LOCAL_ORIG_CONTRAST_ROOT / "dryrun"
    )
    prep_ns: Dict[str, Path] | None = None
    source_prov: Dict[str, Any] | None = None

    if args.archive_prep:
        prep_ns = validate_zero_fit_prep_namespace(
            prep_run_id=args.run_id,
            fit_run_id=args.fit_run_id,
            main_candidates_dir=MAIN_CANDIDATES_DIR,
            local_contrast_root=LOCAL_ORIG_CONTRAST_ROOT,
        )
        source_prov = verify_orig_relevant_source_provenance(repo_root)

    preflight = run_orig_fit2_preflight(
        repo_root,
        dryrun_root,
        zero_delta_control=(args.experiment_mode == "zero_delta_control"),
    )
    if args.archive_prep:
        assert prep_ns is not None and source_prov is not None
        _archive_orig_fit2_prep_bundle(
            dest_dir=prep_ns["prep_records_dir"],
            repo_root=repo_root,
            dryrun_root=dryrun_root,
            preflight=preflight,
            source_prov=source_prov,
            prep_run_id=args.run_id,
            planned_fit_run_id=args.fit_run_id,
            profile_name=args.profile,
            experiment_mode=args.experiment_mode,
            planned_future_paths={
                "archive_dir": str(prep_ns["fit_archive_dir"]),
                "records_dir": str(prep_ns["fit_records_dir"]),
                "local_dir": str(prep_ns["fit_local_dir"]),
            },
        )
        print(f"ARCHIVED_ORIG_FIT2_PREP_BUNDLE: {prep_ns['prep_records_dir']}")
    print(
        json.dumps(
            {
                "fits_executed": 0,
                "dry_run": True,
                "experiment_mode": args.experiment_mode,
                "profile": args.profile,
                "counts": preflight["counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

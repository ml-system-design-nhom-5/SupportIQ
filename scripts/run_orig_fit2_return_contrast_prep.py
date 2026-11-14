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
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import torch
import transformers

from pipeline.evaluation.classifier_acceptance_gate import STANDARD_INTENTS_46
from pipeline.training.orig_fit2_return_contrast_data import (
    _read_jsonl,
    prepare_and_lock_orig_fit2_return_contrast_splits,
)
from pipeline.training.train_boundary_candidate import verify_original_46_label_lineage
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

DEFAULT_PREP_RUN_ID = "fit2-orig-ret-channel-v3"
DEFAULT_PLANNED_FIT_RUN_ID = "fit2-orig-ret-channel-fit-v1"
LOCAL_ORIG_CONTRAST_ROOT = Path(__file__).resolve().parents[1] / "artifacts/evaluation/fit2_orig_ret_channel_20261114"
FIT1_CHECKPOINT_REL = "artifacts/models/candidates/reconstructed-closure-fit1-20261113"
EXPECTED_FIT1_SHA256 = "95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6"
ORIG_FAITHFUL_RECORDS_REL = "artifacts/models/candidates/run-records-faithful-fit2-20261113"

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


def run_orig_fit2_preflight(repo_root: Path, dryrun_root: Path) -> Dict[str, Any]:
    """Fail-closed zero-fit preflight verifying baseline anchors, single-factor split diff, and isolation."""
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

    lock = prepare_and_lock_orig_fit2_return_contrast_splits(
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
        "kb_rationale": lock["kb_rationale"],
        "counts": lock["counts"],
        "dataset_hashes": lock["dataset_hashes"],
        "orig_fit2_stage2_reference_hashes": lock["orig_fit2_stage2_reference_hashes"],
        "new_input_file_hashes": lock["new_input_file_hashes"],
        "baseline_vs_new_diff": lock["baseline_vs_new_diff"],
        "isolation_audit": lock["isolation_audit"],
        "historical_baseline_noisy_overlap_disclosure": lock["historical_baseline_noisy_overlap_disclosure"],
    }


def _build_planned_option_a_plan(
    *,
    prep_records_dir: Path,
    planned_fit_run_id: str,
    planned_future_paths: Dict[str, str],
) -> Dict[str, Any]:
    """Document the sole authorized Option A runner CLI, locked hyperparameters, and causal caveat."""
    planned_cli = [
        ".venv/Scripts/python.exe",
        "-m",
        "scripts.run_orig_fit2_return_contrast_fit",
        "--prep-dir",
        str(prep_records_dir),
        "--run-id",
        planned_fit_run_id,
        "--epochs",
        "3",
        "--lr",
        "2e-5",
        "--batch-size",
        "32",
        "--seed",
        "42",
        "--fit-mode",
        "fit2_supcon_energy",
        "--run-option-a-fit",
    ]
    return {
        "selected_recipe": "option_a_original_fit2_hyperparams",
        "epochs": 3,
        "lr": 2e-5,
        "batch_size": 32,
        "seed": 42,
        "fit_mode": "fit2_supcon_energy",
        "min_temperature": 1.0,
        "enable_selective_rejector": False,
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "planned_cli": planned_cli,
        "planned_future_paths": planned_future_paths,
        "authorized_to_train_now": False,
        "requires_worker_b_re_review_pass_and_coordinator_release": True,
        "causal_control_caveat": (
            "Original Fit2 (f695b1fe...) was trained from Fit1 (95a940b6...) for epochs=3, lr=2e-5. "
            "Warm-starting Option A continuation from converged Fit2 applies 3 additional full epochs "
            "over 13,080 effective rows on top of f695b1fe...; direct comparison against untouched "
            "Original Fit2 is a comparative candidate evaluation, NOT a matched causal control (no "
            "matched no-added-data continuation fit is authorized)."
        ),
    }


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
) -> None:
    """Write immutable zero-fit prep bundle with actual input snapshots, sources, env, and SHA inventory."""
    dest_dir.mkdir(parents=True, exist_ok=False)
    (dest_dir / "status.json").write_text(
        json.dumps({"status": "preparing", "fits_executed": 0}, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        shutil.copytree(dryrun_root / "datasets", dest_dir / "datasets")
        _verify_dir_matches_lock_hashes(dest_dir / "datasets", preflight["dataset_hashes"])
        for root_copy in ("dataset_lock_manifest.json", "orig_fit2_return_contrast_extension.jsonl"):
            shutil.copy2(dest_dir / "datasets" / root_copy, dest_dir / root_copy)

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
        option_a_plan = _build_planned_option_a_plan(
            prep_records_dir=dest_dir,
            planned_fit_run_id=planned_fit_run_id,
            planned_future_paths=planned_future_paths,
        )
        manifest = {
            "schema_version": "orig_fit2_return_contrast_prep.v3",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "git_commit": source_prov["git_commit"],
            "source_hashes": source_prov["source_hashes"],
            "cli_argv": list(sys.argv),
            "planned_prep_run_id": prep_run_id,
            "planned_future_fit_run_id": planned_fit_run_id,
            "baseline_original_fit2": {
                "checkpoint_dir": str(FIT2_BASELINE_DIR),
                "model_safetensors_sha256": EXPECTED_FIT2_SHA256,
                "fit1_initializer_dir": str(repo_root / FIT1_CHECKPOINT_REL),
                "fit1_model_safetensors_sha256": EXPECTED_FIT1_SHA256,
                "faithful_stage2_records_dir": str(repo_root / ORIG_FAITHFUL_RECORDS_REL),
                "calibration_manifest_sha256": _sha256_lower(orig_cal_path),
                "provenance_manifest_sha256": _sha256_lower(orig_prov_path),
                "temperature": 1.0,
                "min_temperature": 1.0,
                "selective_rejector_enabled": False,
            },
            "unchanged_original_recipe_parameters": UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
            "option_a_execution_plan": option_a_plan,
            "preflight": preflight,
        }
        (dest_dir / "prep_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (dest_dir / "status.json").write_text(
            json.dumps({"status": "complete", "fits_executed": 0, "prep_archive": True}, indent=2) + "\n",
            encoding="utf-8",
        )
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
    args = ap.parse_args()

    if not args.dry_run and not args.archive_prep:
        raise ValueError("Specify --dry-run and/or --archive-prep (this script performs zero training fits)")

    repo_root = Path(__file__).resolve().parents[1]
    dryrun_root = LOCAL_ORIG_CONTRAST_ROOT / "dryrun"
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

    preflight = run_orig_fit2_preflight(repo_root, dryrun_root)
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
            planned_future_paths={
                "archive_dir": str(prep_ns["fit_archive_dir"]),
                "records_dir": str(prep_ns["fit_records_dir"]),
                "local_dir": str(prep_ns["fit_local_dir"]),
            },
        )
        print(f"ARCHIVED_ORIG_FIT2_PREP_BUNDLE: {prep_ns['prep_records_dir']}")
    print(json.dumps({"fits_executed": 0, "dry_run": True, "counts": preflight["counts"]}, indent=2))


if __name__ == "__main__":
    main()

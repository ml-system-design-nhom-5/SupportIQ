"""Fail-closed preparation and bounded continuation runner for taxonomy-clean contrast + calibration.

Starts ONLY from MAIN reconstructed-fit2-supcon-20261113 (f695b1fe..., T=1.0, rejector disabled),
prepares taxonomy-clean, exposure-balanced 46-class contrast splits + non-retail OOD negatives,
enforces canonical Bitext (8bc10cfa / 1d366e89) lineage & split isolation, and optionally
fits the existing selective_calibration.v1 (776d CLS+logit) rejector strictly on TRAIN/CAL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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
from transformers import AutoModelForSequenceClassification

from apps.core_backend.intent.routing import STANDARD_INTENTS_46
from pipeline.evaluation.classifier_acceptance_gate import audit_candidate_provenance, validate_calibration_manifest
from pipeline.training.boundary_contrast_data import (
    prepare_and_lock_contrast_splits,
    validate_contrast_semantic_consistency,
)
from pipeline.training.train_boundary_candidate import (
    DEFAULT_REJECTOR_C_GRID,
    _read_jsonl,
    resolve_neg_repeat,
    run_fit_and_lock_candidate,
    validate_boundary_split_taxonomy,
    verify_reload_from_archive,
)
from pipeline.training.train_domain_candidate import verify_original_46_label_lineage

SERVING_DIR = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\trained\distilbert-supportiq")
EXPECTED_SERVING_SHA256 = "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302"
MAIN_CANDIDATES_DIR = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates")
FIT2_BASELINE_DIR = MAIN_CANDIDATES_DIR / "reconstructed-fit2-supcon-20261113"
EXPECTED_FIT2_SHA256 = "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"
LOCAL_CONTRAST_ROOT = Path(__file__).resolve().parents[1] / "artifacts/evaluation/boundary_contrast_20261114"
RELEVANT_SOURCE_PATHS: Tuple[str, ...] = (
    "scripts/run_boundary_contrast_fit.py",
    "pipeline/training/boundary_contrast_data.py",
    "pipeline/training/train_boundary_candidate.py",
    "pipeline/training/boundary_curriculum_data.py",
    "pipeline/training/train_selective_candidate.py",
    "pipeline/training/train_domain_candidate.py",
    "pipeline/training/closure_domain_data.py",
    "pipeline/training/selective_domain_data.py",
    "pipeline/training/domain_templates.py",
    "pipeline/evaluation/classifier_acceptance_gate.py",
    "apps/core_backend/intent/routing.py",
    "apps/core_backend/config/policies/intent_policy.v2.json",
)


def _sha256_lower(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def _write_and_verify_sha_inventory(root: Path, inv_filename: str, exclude: set[str] | None = None) -> Dict[str, str]:
    skip = (exclude or set()) | {inv_filename}
    inv = {
        str(p.relative_to(root)).replace("\\", "/"): _sha256_lower(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name not in skip
    }
    inv_path = root / inv_filename
    inv_path.write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(inv_path.read_text(encoding="utf-8"))
    mismatches = [k for k, v in loaded.items() if _sha256_lower(root / k) != v]
    if mismatches:
        raise ValueError(f"SHA verification failed for {inv_path}: {mismatches}")
    return loaded


def _verify_dir_matches_lock_hashes(datasets_dir: Path, expected_hashes: Dict[str, str]) -> None:
    """Ensure every locked dataset artifact in datasets_dir matches dataset_lock_manifest SHA-256s."""
    special_names = {"boundary_split_manifest": "split_manifest.json"}
    for key, exp_sha in expected_hashes.items():
        fname = special_names.get(key, f"{key}.jsonl")
        p = datasets_dir / fname
        if not p.exists():
            raise FileNotFoundError(f"Missing locked dataset file {p}")
        actual = _sha256_lower(p)
        if actual != str(exp_sha).lower():
            raise ValueError(f"Dataset SHA mismatch for {p}: {actual} != {exp_sha}")


def verify_fit2_starting_checkpoint(init_dir: Path) -> Dict[str, Any]:
    """Fail closed unless init_dir is the exact verified reconstructed-fit2-supcon-20261113 checkpoint."""
    weights = init_dir / "model.safetensors"
    if not weights.exists():
        raise FileNotFoundError(f"Missing starting Fit2 weights: {weights}")
    actual_sha = _sha256_lower(weights)
    if actual_sha != EXPECTED_FIT2_SHA256:
        raise ValueError(f"Starting Fit2 weights SHA mismatch: {actual_sha} != {EXPECTED_FIT2_SHA256}")

    cal_audit = validate_calibration_manifest(init_dir, init_dir / "calibration_manifest.json")
    if not cal_audit.get("valid"):
        raise ValueError(f"Invalid starting calibration_manifest.json: {cal_audit.get('failure_reasons')}")
    if float(cal_audit.get("temperature") or 0.0) != 1.0:
        raise ValueError(f"Expected starting T=1.0, got {cal_audit.get('temperature')}")
    rej = cal_audit.get("rejector") or {}
    if bool(rej.get("enabled")):
        raise ValueError("Expected starting selective_rejector.enabled=false")

    model = AutoModelForSequenceClassification.from_pretrained(str(init_dir), local_files_only=True)
    if int(model.config.num_labels) != 46:
        raise ValueError(f"Expected 46 labels, got {model.config.num_labels}")
    id2label = {int(k): v for k, v in model.config.id2label.items()}
    if [id2label[i] for i in range(46)] != list(STANDARD_INTENTS_46):
        raise ValueError("Starting checkpoint label bijection mismatch with STANDARD_INTENTS_46")

    return {"weights_sha256": actual_sha, "temperature": 1.0, "rejector_enabled": False, "num_labels": 46}


def run_preflight_validation(repo_root: Path, dryrun_root: Path) -> Dict[str, Any]:
    """Fail-closed preflight validating Serving, Fit2 start checkpoint, canonical prep, and contrast splits."""
    serving_sha = _sha256_lower(SERVING_DIR / "model.safetensors")
    if serving_sha != EXPECTED_SERVING_SHA256:
        raise ValueError(f"Serving weights SHA mismatch: {serving_sha} != {EXPECTED_SERVING_SHA256}")

    init_info = verify_fit2_starting_checkpoint(FIT2_BASELINE_DIR)
    lineage = verify_original_46_label_lineage(repo_root=repo_root)

    if (dryrun_root / "datasets").exists():
        shutil.rmtree(dryrun_root / "datasets")

    lock = prepare_and_lock_contrast_splits(
        worktree_root=repo_root,
        data_repo_root=repo_root,
        init_model_dir=FIT2_BASELINE_DIR,
        artifact_root=dryrun_root,
    )
    ds_dir = dryrun_root / "datasets"
    for key, meta in lock["files"].items():
        p = Path(meta["path"])
        if not p.exists() or _sha256_lower(p) != meta["sha256"].lower():
            raise ValueError(f"Contrast dataset SHA mismatch for {key}: {p}")
    _verify_dir_matches_lock_hashes(ds_dir, lock["dataset_hashes"])

    if not lock["contrast_extension"]["isolation_passed"]:
        raise RuntimeError("Contrast split isolation failed")
    if lock["counts"]["domain_pos_eval"] < 160 or lock["counts"]["domain_neg_eval"] < 45:
        raise RuntimeError(f"Insufficient internal eval counts (expected >=160 pos / >=45 neg): {lock['counts']}")

    pos_train_rows = _read_jsonl(ds_dir / "boundary_pos_train.jsonl")
    pos_cal_rows = _read_jsonl(ds_dir / "boundary_pos_calibration.jsonl")
    pos_eval_rows = _read_jsonl(ds_dir / "boundary_pos_evaluation.jsonl")
    neg_train_rows = _read_jsonl(ds_dir / "boundary_neg_train.jsonl")
    neg_cal_rows = _read_jsonl(ds_dir / "boundary_neg_calibration.jsonl")
    neg_eval_rows = _read_jsonl(ds_dir / "boundary_neg_evaluation.jsonl")

    validate_boundary_split_taxonomy(pos_train_rows, neg_train_rows, split_name="contrast_train")
    validate_boundary_split_taxonomy(pos_cal_rows, neg_cal_rows, split_name="contrast_calibration")
    validate_boundary_split_taxonomy(pos_eval_rows, neg_eval_rows, split_name="contrast_evaluation")
    validate_contrast_semantic_consistency(pos_train_rows, neg_train_rows, "contrast_train", check_train_balance=True)
    validate_contrast_semantic_consistency(pos_cal_rows, neg_cal_rows, "contrast_calibration")
    validate_contrast_semantic_consistency(pos_eval_rows, neg_eval_rows, "contrast_evaluation")

    for r in pos_train_rows + pos_cal_rows + pos_eval_rows:
        if "neg_repeat" in r:
            raise ValueError(f"Positive 46-class row must not carry neg_repeat: {r.get('sample_id')}")
        if int(r.get("is_negative", 0)) != 0 or int(r.get("selective_label", 1)) != 1:
            raise ValueError(f"Positive 46-class row has invalid mask flags: {r.get('sample_id')}")

    for r in neg_train_rows:
        rep = resolve_neg_repeat(r, 12)
        if str(r.get("sample_id", "")).startswith(("compound_auth_", "nonretail_ood_")) and rep != 12:
            raise ValueError(f"Expected neg_repeat=12 on {r.get('sample_id')}")

    standard_set = set(STANDARD_INTENTS_46)
    pos_req = ("order_history", "return_product_in_store", "track_delivery", "track_order", "return_policy", "return_product")
    neg_req = ("multi_intent", "out_of_scope", "other_domain")
    for split_label, p_rows, n_rows in (
        ("train", pos_train_rows, neg_train_rows),
        ("calibration", pos_cal_rows, neg_cal_rows),
        ("evaluation", pos_eval_rows, neg_eval_rows),
    ):
        pos_intents = {r["intent"] for r in p_rows}
        neg_intents = {r["intent"] for r in n_rows}
        if neg_intents & standard_set:
            raise RuntimeError(f"STANDARD_INTENTS_46 leaked into neg_{split_label}: {sorted(neg_intents & standard_set)}")
        for req in pos_req:
            if req not in pos_intents:
                raise RuntimeError(f"Missing target 46-class contrast intent {req} in boundary_pos_{split_label}")
        for req in neg_req:
            if req not in neg_intents:
                raise RuntimeError(f"Missing genuine negative intent {req} in boundary_neg_{split_label}")

    return {
        "dry_run": True,
        "fits_executed": 0,
        "serving_weights_sha256": serving_sha,
        "starting_checkpoint": init_info,
        "canonical_prep": {
            "cleaned_sha256": lineage.cleaned_sha256,
            "splits_sha256": lineage.splits_sha256,
        },
        "counts": lock["counts"],
        "contrast_extension": lock["contrast_extension"],
        "effective_exposure_counts": lock["effective_exposure_counts"],
        "dataset_hashes": lock["dataset_hashes"],
    }


def _parse_c_grid(raw: str) -> Tuple[float, ...]:
    vals = tuple(float(x.strip()) for x in raw.split(",") if x.strip())
    if not vals or any(v <= 0.0 for v in vals):
        raise ValueError(f"Invalid --c-grid: {raw!r}")
    return vals


def verify_relevant_source_provenance(repo_root: Path) -> Dict[str, Any]:
    """Fail closed if relevant runner/training/gate/routing/policy files differ from HEAD, ignoring unrelated PPTX/audit files."""
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", git_sha):
        raise RuntimeError(f"Expected 40-char HEAD SHA, got {git_sha!r}")

    porcelain = subprocess.check_output(
        ["git", "status", "--porcelain", "--", *RELEVANT_SOURCE_PATHS],
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


def _snapshot_relevant_sources(repo_root: Path, dest_root: Path, expected_hashes: Dict[str, str]) -> None:
    snap_dir = dest_root / "source_snapshot"
    for rel, exp_sha in expected_hashes.items():
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, dst)
        if _sha256_lower(dst) != exp_sha:
            raise ValueError(f"Archived source snapshot SHA mismatch for {rel}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Bounded confusable-boundary contrast continuation runner")
    ap.add_argument("--dry-run", action="store_true", help="Run fail-closed preflight without training")
    ap.add_argument("--archive-dryrun", action="store_true", help="Archive immutable dryrun datasets/manifest/env in MAIN")
    ap.add_argument("--run-contrast-fit", action="store_true", help="Run 1 bounded continuation fit (requires budget)")
    ap.add_argument("--run-id", default="fit2-boundary-contrast-v4p1")
    ap.add_argument("--enable-selective-rejector", action="store_true", help="Fit existing 776d CLS+logit rejector on TRAIN/CAL")
    ap.add_argument("--c-grid", default=",".join(str(x) for x in DEFAULT_REJECTOR_C_GRID))
    args = ap.parse_args()

    c_grid = _parse_c_grid(args.c_grid)
    repo_root = Path(__file__).resolve().parents[1]
    dryrun_root = LOCAL_CONTRAST_ROOT / "dryrun"
    archive_dir = MAIN_CANDIDATES_DIR / args.run_id
    records_dir = MAIN_CANDIDATES_DIR / f"run-records-{args.run_id}"
    dryrun_records_dir = MAIN_CANDIDATES_DIR / f"run-records-{args.run_id}-dryrun"
    local_root = LOCAL_CONTRAST_ROOT / args.run_id

    if args.run_contrast_fit:
        if archive_dir.exists():
            raise FileExistsError(f"MAIN archive already exists: {archive_dir}")
        if records_dir.exists():
            raise FileExistsError(f"MAIN run-records already exists: {records_dir}")
        if local_root.exists():
            raise FileExistsError(f"Local output dir already exists: {local_root}")
    if args.archive_dryrun and dryrun_records_dir.exists():
        raise FileExistsError(f"MAIN dryrun records already exist: {dryrun_records_dir}")

    source_prov = verify_relevant_source_provenance(repo_root) if (args.archive_dryrun or args.run_contrast_fit) else None
    preflight = run_preflight_validation(repo_root, dryrun_root)
    if args.archive_dryrun:
        assert source_prov is not None
        git_sha = source_prov["git_commit"]
        dryrun_records_dir.mkdir(parents=True, exist_ok=False)
        shutil.copytree(dryrun_root / "datasets", dryrun_records_dir / "datasets")
        _verify_dir_matches_lock_hashes(dryrun_records_dir / "datasets", preflight["dataset_hashes"])
        _snapshot_relevant_sources(repo_root, dryrun_records_dir, source_prov["source_hashes"])
        (dryrun_records_dir / "environment.json").write_text(
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
        (dryrun_records_dir / "dryrun_manifest.json").write_text(
            json.dumps(
                {
                    "git_commit": git_sha,
                    "source_hashes": source_prov["source_hashes"],
                    "cli_argv": list(sys.argv),
                    "planned_run_id": args.run_id,
                    "planned_future_cli": [
                        "python",
                        "-m",
                        "scripts.run_boundary_contrast_fit",
                        "--run-contrast-fit",
                        "--run-id",
                        args.run_id,
                        "--enable-selective-rejector",
                    ],
                    "planned_rejector_c_grid": list(c_grid),
                    "preflight": preflight,
                    "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _write_and_verify_sha_inventory(dryrun_records_dir, "sidecar_sha_inventory.json")
        preflight["dryrun_records_dir"] = str(dryrun_records_dir)

    if args.dry_run or not args.run_contrast_fit:
        print(json.dumps(preflight, indent=2))
        return

    assert source_prov is not None
    git_sha = source_prov["git_commit"]
    # Copy locked datasets to local_root and preserve durable inputs + metadata in MAIN BEFORE training
    shutil.copytree(dryrun_root / "datasets", local_root / "datasets")
    _verify_dir_matches_lock_hashes(local_root / "datasets", preflight["dataset_hashes"])

    records_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(local_root / "datasets", records_dir / "inputs")
    _verify_dir_matches_lock_hashes(records_dir / "inputs", preflight["dataset_hashes"])
    inputs_inv = _write_and_verify_sha_inventory(records_dir / "inputs", "inputs_sha256_inventory.json")
    for rel, sha in inputs_inv.items():
        if _sha256_lower(local_root / "datasets" / rel) != sha:
            raise ValueError(f"Copied input byte mismatch for {rel}")
    _snapshot_relevant_sources(repo_root, records_dir, source_prov["source_hashes"])

    (records_dir / "environment.json").write_text(
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
    (records_dir / "run_config.json").write_text(
        json.dumps(
            {
                "git_commit": git_sha,
                "source_hashes": source_prov["source_hashes"],
                "cli_argv": list(sys.argv),
                "init_model_dir": str(FIT2_BASELINE_DIR),
                "init_weights_sha256": EXPECTED_FIT2_SHA256,
                "canonical_prep": preflight.get("canonical_prep", {}),
                "fit_mode": "fit2_supcon_energy",
                "epochs": 2,
                "batch_size": 32,
                "lr": 1e-5,
                "seed": 42,
                "enable_selective_rejector": bool(args.enable_selective_rejector),
                "rejector_c_grid": list(c_grid) if args.enable_selective_rejector else [],
                "cal_selection_policy": "feasible_zero_cal_unsafe_and_nonzero_sup11_domain_and_bitext_cov",
                "effective_exposure_counts": preflight.get("effective_exposure_counts", {}),
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def _write_status(status: str, **extra: Any) -> None:
        payload = {
            "status": status,
            "git_commit": git_sha,
            "run_id": args.run_id,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **extra,
        }
        (records_dir / "status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    _write_status("training", fits_started=1, fits_completed=0)
    try:
        fit_result = run_fit_and_lock_candidate(
            worktree_root=repo_root,
            data_repo_root=repo_root,
            init_model_dir=FIT2_BASELINE_DIR,
            artifact_root=local_root,
            fit_mode="fit2_supcon_energy",
            output_subdir="candidate_model_contrast",
            epochs=2,
            batch_size=32,
            lr=1e-5,
            seed=42,
            enable_selective_rejector=bool(args.enable_selective_rejector),
            rejector_c_grid=c_grid,
            candidate_name=args.run_id,
        )
        cand_dir = local_root / "candidate_model_contrast"
        archive_dir.mkdir(parents=True, exist_ok=False)
        for p in sorted(cand_dir.iterdir()):
            if p.is_file():
                shutil.copy2(p, archive_dir / p.name)
        cal_check = validate_calibration_manifest(archive_dir, archive_dir / "calibration_manifest.json")
        if not cal_check.get("valid"):
            raise ValueError(f"Archived calibration_manifest invalid: {cal_check.get('failure_reasons')}")
        prov_check = audit_candidate_provenance(archive_dir, archive_dir / "candidate_provenance_manifest.json")
        if not prov_check.get("provenance_passed"):
            raise ValueError(f"Archived candidate_provenance_manifest invalid: {prov_check.get('failure_reasons')}")
        _write_and_verify_sha_inventory(archive_dir, "archive_sha_inventory.json")
        reload_info = verify_reload_from_archive(archive_dir)
    except Exception as exc:
        _write_status("incomplete", fits_started=1, fits_completed=0, error=str(exc))
        raise

    _write_status("complete", fits_started=1, fits_completed=1, archive_dir=str(archive_dir))
    _write_and_verify_sha_inventory(records_dir, "sidecar_sha_inventory.json")
    print(
        json.dumps(
            {
                "fit_result": fit_result,
                "archive_dir": str(archive_dir),
                "provenance_audit": {"provenance_passed": prov_check["provenance_passed"], "num_labels": prov_check["num_labels"]},
                "reload": reload_info,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

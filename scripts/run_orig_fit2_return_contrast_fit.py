"""Strict fail-closed Option A continuation runner & archival orchestrator.

Consumes ONLY an immutable locked `-prep` bundle (`--prep-dir`, defaulting to
`run-records-fit2-orig-ret-channel-v3-prep`), verifies ancestor git provenance,
frozen source_snapshot + relevant source hashes, dataset/sidecar inventories,
Original Fit2 `f695b1fe...` init, and locked Option A parameters (`epochs=3,
lr=2e-5, batch_size=32, seed=42, fit_mode="fit2_supcon_energy",
min_temperature=1.0, enable_selective_rejector=False`), before optionally
executing 1 authorized continuation fit and archiving complete provenance,
calibration, reload verification, logs, and SHA inventories in MAIN.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import torch
import transformers

from pipeline.evaluation.classifier_acceptance_gate import (
    audit_candidate_provenance,
    validate_calibration_manifest,
)
from pipeline.training.train_boundary_candidate import (
    run_fit_and_lock_candidate,
    verify_reload_from_archive,
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
    verify_fit2_starting_checkpoint,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    DEFAULT_PLANNED_FIT_RUN_ID,
    DEFAULT_PREP_RUN_ID,
    LOCAL_ORIG_CONTRAST_ROOT,
    UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
    verify_git_commit_ancestor,
    verify_orig_relevant_source_provenance,
)

EXPECTED_PREP_SCHEMAS: Tuple[str, ...] = (
    "orig_fit2_return_contrast_prep.v2",
    "orig_fit2_return_contrast_prep.v3",
)

OPTION_A_LOCKED: Dict[str, Any] = {
    "epochs": 3,
    "lr": 2e-5,
    "batch_size": 32,
    "seed": 42,
    "fit_mode": "fit2_supcon_energy",
    "min_temperature": 1.0,
    "enable_selective_rejector": False,
}


def validate_option_a_settings(
    *,
    epochs: int,
    lr: float,
    batch_size: int,
    seed: int,
    fit_mode: str,
    enable_selective_rejector: bool,
) -> None:
    """Fail closed on any deviation from authorized Option A parameters."""
    if int(epochs) != OPTION_A_LOCKED["epochs"]:
        raise ValueError(f"Option A enforces epochs=3; got {epochs}")
    if abs(float(lr) - float(OPTION_A_LOCKED["lr"])) > 1e-12:
        raise ValueError(f"Option A enforces lr=2e-5; got {lr}")
    if int(batch_size) != OPTION_A_LOCKED["batch_size"]:
        raise ValueError(f"Option A enforces batch_size=32; got {batch_size}")
    if int(seed) != OPTION_A_LOCKED["seed"]:
        raise ValueError(f"Option A enforces seed=42; got {seed}")
    if str(fit_mode) != OPTION_A_LOCKED["fit_mode"]:
        raise ValueError(f"Option A enforces fit_mode='fit2_supcon_energy'; got {fit_mode!r}")
    if bool(enable_selective_rejector):
        raise ValueError("Option A enforces selective rejector OFF (enable_selective_rejector=False)")


def verify_locked_prep_bundle(
    *,
    prep_dir: Path,
    repo_root: Path,
    expected_prep_schemas: Tuple[str, ...] = EXPECTED_PREP_SCHEMAS,
) -> Dict[str, Any]:
    """Verify frozen prep bundle integrity, sidecar SHA inventory, datasets, ancestor commit, and source SHAs."""
    if not prep_dir.is_dir():
        raise FileNotFoundError(f"Missing locked prep bundle directory: {prep_dir}")

    status_path = prep_dir / "status.json"
    if not status_path.is_file():
        raise FileNotFoundError(f"Missing prep status.json: {status_path}")
    status_data = json.loads(status_path.read_text(encoding="utf-8"))
    if status_data.get("status") != "complete" or not status_data.get("prep_archive") or int(status_data.get("fits_executed", -1)) != 0:
        raise ValueError(f"Invalid prep status.json (expected zero-fit complete prep): {status_data}")

    inv_path = prep_dir / "sidecar_sha_inventory.json"
    if not inv_path.is_file():
        raise FileNotFoundError(f"Missing prep sidecar_sha_inventory.json: {inv_path}")
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    actual_rel_files = {
        str(p.relative_to(prep_dir)).replace("\\", "/")
        for p in sorted(prep_dir.rglob("*"))
        if p.is_file() and p.name != "sidecar_sha_inventory.json"
    }
    if set(inv.keys()) != actual_rel_files:
        raise ValueError(
            f"Prep bundle file set mismatch vs sidecar_sha_inventory.json: "
            f"missing={sorted(set(inv.keys()) - actual_rel_files)}, "
            f"extra={sorted(actual_rel_files - set(inv.keys()))}"
        )
    sha_mismatches = [k for k, exp_sha in inv.items() if _sha256_lower(prep_dir / k) != str(exp_sha).lower()]
    if sha_mismatches:
        raise ValueError(f"Prep bundle SHA mismatch vs sidecar_sha_inventory.json: {sha_mismatches}")

    manifest_path = prep_dir / "prep_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") not in expected_prep_schemas:
        raise ValueError(
            f"Unexpected prep_manifest schema_version {manifest.get('schema_version')!r}; expected one of {expected_prep_schemas!r}"
        )

    preflight = manifest.get("preflight") or {}
    if preflight.get("extension_version") != "orig_fit2_return_channel_contrast_v2":
        raise ValueError(f"Unexpected extension_version in prep_manifest: {preflight.get('extension_version')!r}")
    if (preflight.get("counts") or {}).get("extension_pos_train_added") != 18:
        raise ValueError(f"Unexpected extension row count in prep_manifest: {preflight.get('counts')}")
    if (manifest.get("unchanged_original_recipe_parameters") or {}) != UNCHANGED_ORIGINAL_RECIPE_PARAMETERS:
        raise ValueError("prep_manifest unchanged_original_recipe_parameters drifted from expected Fit2 constants")

    plan = manifest.get("option_a_execution_plan") or {}
    if (plan.get("epochs"), plan.get("lr"), plan.get("enable_selective_rejector")) != (3, 2e-5, False):
        raise ValueError(f"Invalid option_a_execution_plan in prep_manifest: {plan}")

    ds_dir = prep_dir / "datasets"
    _verify_dir_matches_lock_hashes(ds_dir, preflight.get("dataset_hashes") or {})
    new_input_hashes = preflight.get("new_input_file_hashes") or {}
    if not new_input_hashes:
        raise ValueError("Missing new_input_file_hashes in prep_manifest")
    for fname, exp_sha in new_input_hashes.items():
        fp = ds_dir / fname
        if not fp.is_file():
            raise FileNotFoundError(f"Missing locked prep input file: {fp}")
        actual = _sha256_lower(fp)
        if actual != str(exp_sha).lower():
            raise ValueError(f"Prep input SHA mismatch for {fname}: {actual} != {exp_sha}")

    expected_source_hashes = manifest.get("source_hashes") or {}
    if not isinstance(expected_source_hashes, dict) or not expected_source_hashes:
        raise ValueError("Missing source_hashes in prep_manifest")

    snap_dir = prep_dir / "source_snapshot"
    for rel, exp_sha in expected_source_hashes.items():
        snap_fp = snap_dir / rel
        if not snap_fp.is_file():
            raise FileNotFoundError(f"Missing frozen source_snapshot file in prep bundle: {snap_fp}")
        if _sha256_lower(snap_fp) != str(exp_sha).lower():
            raise ValueError(f"Frozen source_snapshot SHA mismatch for {rel}")

    source_prov = verify_orig_relevant_source_provenance(repo_root)
    prep_commit = str(manifest.get("git_commit") or "").strip().lower()
    head_commit = verify_git_commit_ancestor(repo_root, prep_commit, source_prov["git_commit"])
    if source_prov["source_hashes"] != expected_source_hashes:
        raise ValueError("Relevant tracked source file hashes differ from locked prep source_hashes")

    return {
        "manifest": manifest,
        "manifest_sha256": _sha256_lower(manifest_path),
        "prep_schema_version": manifest.get("schema_version"),
        "prep_git_commit": prep_commit,
        "head_git_commit": head_commit,
        "new_input_hashes": new_input_hashes,
        "dataset_hashes": preflight["dataset_hashes"],
        "source_prov": source_prov,
    }


def _check_output_paths_unused(
    *,
    run_id: str,
    main_candidates_dir: Path,
    local_root_base: Path,
) -> Dict[str, Path]:
    archive_dir = main_candidates_dir / run_id
    records_dir = main_candidates_dir / f"run-records-{run_id}"
    local_root = local_root_base / run_id
    for p in (archive_dir, records_dir, local_root):
        if p.exists():
            raise FileExistsError(f"Output path already exists (fail-closed no-overwrite): {p}")
    return {"archive_dir": archive_dir, "records_dir": records_dir, "local_root": local_root}


def run_authorized_option_a_fit(
    *,
    repo_root: Path,
    prep_dir: Path,
    run_id: str,
    epochs: int = 3,
    lr: float = 2e-5,
    batch_size: int = 32,
    seed: int = 42,
    fit_mode: str = "fit2_supcon_energy",
    enable_selective_rejector: bool = False,
    execute_fit: bool = False,
    main_candidates_dir: Path = MAIN_CANDIDATES_DIR,
    local_root_base: Path = LOCAL_ORIG_CONTRAST_ROOT,
    init_model_dir: Path = FIT2_BASELINE_DIR,
    serving_dir: Path = SERVING_DIR,
) -> Dict[str, Any]:
    """Verify Option A guards and optionally run & archive the single authorized Fit2 continuation."""
    validate_option_a_settings(
        epochs=epochs,
        lr=lr,
        batch_size=batch_size,
        seed=seed,
        fit_mode=fit_mode,
        enable_selective_rejector=enable_selective_rejector,
    )
    out_paths = _check_output_paths_unused(
        run_id=run_id,
        main_candidates_dir=main_candidates_dir,
        local_root_base=local_root_base,
    )
    prep_verified = verify_locked_prep_bundle(prep_dir=prep_dir, repo_root=repo_root)

    serving_weights = serving_dir / "model.safetensors"
    if not serving_weights.is_file():
        raise FileNotFoundError(f"Missing Serving checkpoint weights: {serving_weights}")
    serving_sha = _sha256_lower(serving_weights)
    if serving_sha != EXPECTED_SERVING_SHA256:
        raise ValueError(f"Serving weights SHA mismatch: {serving_sha} != {EXPECTED_SERVING_SHA256}")

    init_info = verify_fit2_starting_checkpoint(init_model_dir)
    if not execute_fit:
        return {
            "validated_only": True,
            "fits_executed": 0,
            "prep_dir": str(prep_dir),
            "prep_schema_version": prep_verified["prep_schema_version"],
            "prep_manifest_sha256": prep_verified["manifest_sha256"],
            "prep_git_commit": prep_verified["prep_git_commit"],
            "head_git_commit": prep_verified["head_git_commit"],
            "git_commit": prep_verified["head_git_commit"],
            "starting_checkpoint": init_info,
            "serving_weights_sha256": serving_sha,
            "option_a_settings": OPTION_A_LOCKED,
            "planned_outputs": {k: str(v) for k, v in out_paths.items()},
        }

    archive_dir = out_paths["archive_dir"]
    records_dir = out_paths["records_dir"]
    local_root = out_paths["local_root"]
    source_prov = prep_verified["source_prov"]
    git_sha = prep_verified["head_git_commit"]
    prep_git_sha = prep_verified["prep_git_commit"]
    new_input_hashes = prep_verified["new_input_hashes"]

    # Consume ONLY locked prep datasets (never regenerate splits during fit).
    local_root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(prep_dir / "datasets", local_root / "datasets")
    _verify_dir_matches_lock_hashes(local_root / "datasets", prep_verified["dataset_hashes"])
    for fname, exp_sha in new_input_hashes.items():
        if _sha256_lower(local_root / "datasets" / fname) != str(exp_sha).lower():
            raise ValueError(f"Copied local input byte mismatch for {fname}")

    records_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(prep_dir / "datasets", records_dir / "inputs")
    _verify_dir_matches_lock_hashes(records_dir / "inputs", prep_verified["dataset_hashes"])
    inputs_inv = _write_and_verify_sha_inventory(records_dir / "inputs", "inputs_sha256_inventory.json")
    for fname, exp_sha in new_input_hashes.items():
        if inputs_inv.get(fname) != str(exp_sha).lower():
            raise ValueError(f"Archived input inventory mismatch for {fname}: {inputs_inv.get(fname)} != {exp_sha}")

    snap_dir = records_dir / "source_snapshot"
    for rel, exp_sha in source_prov["source_hashes"].items():
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / rel, dst)
        if _sha256_lower(dst) != exp_sha:
            raise ValueError(f"Source snapshot SHA mismatch for {rel}")

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
                "head_git_commit": git_sha,
                "prep_git_commit": prep_git_sha,
                "prep_schema_version": prep_verified["prep_schema_version"],
                "source_hashes": source_prov["source_hashes"],
                "cli_argv": list(sys.argv),
                "prep_dir": str(prep_dir),
                "prep_manifest_sha256": prep_verified["manifest_sha256"],
                "init_model_dir": str(init_model_dir),
                "init_weights_sha256": EXPECTED_FIT2_SHA256,
                "fit_mode": fit_mode,
                "epochs": epochs,
                "batch_size": batch_size,
                "lr": lr,
                "seed": seed,
                "min_temperature": 1.0,
                "enable_selective_rejector": False,
                "dataset_hashes": prep_verified["dataset_hashes"],
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    log_lines: list[str] = []

    def _log(msg: str) -> None:
        line = f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {msg}"
        log_lines.append(line)
        (records_dir / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    def _write_status(status: str, **extra: Any) -> None:
        payload = {
            "status": status,
            "git_commit": git_sha,
            "head_git_commit": git_sha,
            "prep_git_commit": prep_git_sha,
            "run_id": run_id,
            "prep_dir": str(prep_dir),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **extra,
        }
        (records_dir / "status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    _write_status("training", fits_started=1, fits_completed=0)
    _log(f"Starting Option A fit run_id={run_id} prep_dir={prep_dir} init={EXPECTED_FIT2_SHA256}")
    try:
        fit_result = run_fit_and_lock_candidate(
            worktree_root=repo_root,
            data_repo_root=repo_root,
            init_model_dir=init_model_dir,
            artifact_root=local_root,
            fit_mode="fit2_supcon_energy",
            output_subdir="candidate_model_option_a",
            epochs=3,
            batch_size=32,
            lr=2e-5,
            seed=42,
            enable_selective_rejector=False,
            candidate_name=run_id,
        )
        cand_dir = local_root / "candidate_model_option_a"
        archive_dir.mkdir(parents=True, exist_ok=False)
        for p in sorted(cand_dir.iterdir()):
            if p.is_file():
                shutil.copy2(p, archive_dir / p.name)
            elif p.is_dir():
                shutil.copytree(p, archive_dir / p.name)

        cal_check = validate_calibration_manifest(archive_dir, archive_dir / "calibration_manifest.json")
        if not cal_check.get("valid"):
            raise ValueError(f"Archived calibration_manifest invalid: {cal_check.get('failure_reasons')}")
        if float(cal_check.get("temperature") or 0.0) < 1.0:
            raise ValueError(f"Archived calibration temperature < 1.0: {cal_check.get('temperature')}")
        if bool((cal_check.get("rejector") or {}).get("enabled")):
            raise ValueError("Archived candidate unexpectedly enabled selective_rejector")

        prov_check = audit_candidate_provenance(archive_dir, archive_dir / "candidate_provenance_manifest.json")
        if not prov_check.get("provenance_passed"):
            raise ValueError(f"Archived candidate_provenance_manifest invalid: {prov_check.get('failure_reasons')}")

        reload_info = verify_reload_from_archive(archive_dir)
        archive_inv = _write_and_verify_sha_inventory(archive_dir, "archive_sha_inventory.json")
        (records_dir / "fit_result.json").write_text(json.dumps(fit_result, indent=2) + "\n", encoding="utf-8")
        _log(
            f"Archived & verified candidate_dir={archive_dir} T={cal_check.get('temperature')} "
            f"files={len(archive_inv)} reload_labels={reload_info.get('num_labels')}"
        )
    except Exception as exc:
        _log(f"FAILED: {exc}")
        _write_status("incomplete", fits_started=1, fits_completed=0, error=str(exc))
        raise

    _write_status("complete", fits_started=1, fits_completed=1, archive_dir=str(archive_dir))
    sidecar_inv = _write_and_verify_sha_inventory(records_dir, "sidecar_sha_inventory.json")
    return {
        "validated_only": False,
        "fits_executed": 1,
        "fit_result": fit_result,
        "archive_dir": str(archive_dir),
        "records_dir": str(records_dir),
        "calibration_audit": {"valid": cal_check["valid"], "temperature": cal_check["temperature"]},
        "provenance_audit": {"provenance_passed": prov_check["provenance_passed"], "num_labels": prov_check["num_labels"]},
        "reload": reload_info,
        "archive_sha_inventory_count": len(archive_inv),
        "sidecar_sha_inventory_count": len(sidecar_inv),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fail-closed Option A Fit2 return-channel continuation runner")
    ap.add_argument(
        "--prep-dir",
        type=Path,
        default=MAIN_CANDIDATES_DIR / f"run-records-{DEFAULT_PREP_RUN_ID}-prep",
        help="Locked prep bundle directory",
    )
    ap.add_argument("--run-id", default=DEFAULT_PLANNED_FIT_RUN_ID)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fit-mode", default="fit2_supcon_energy")
    ap.add_argument("--enable-selective-rejector", action="store_true")
    ap.add_argument("--validate-only", action="store_true", help="Run fail-closed Option A & locked prep checks without fitting")
    ap.add_argument("--run-option-a-fit", action="store_true", help="Execute the single authorized Option A continuation fit")
    args = ap.parse_args()

    if args.validate_only == args.run_option_a_fit:
        raise ValueError("Specify exactly one of --validate-only or --run-option-a-fit")

    repo_root = Path(__file__).resolve().parents[1]
    res = run_authorized_option_a_fit(
        repo_root=repo_root,
        prep_dir=args.prep_dir.resolve(),
        run_id=args.run_id,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        seed=args.seed,
        fit_mode=args.fit_mode,
        enable_selective_rejector=args.enable_selective_rejector,
        execute_fit=args.run_option_a_fit,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

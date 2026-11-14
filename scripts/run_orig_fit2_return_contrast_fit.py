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
from pipeline.training.orig_fit2_return_contrast_data import EXPECTED_ORIG_STAGE2_LOCKED_FILES
from pipeline.training.train_boundary_candidate import (
    VALID_TRAINABLE_SCOPES,
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
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_DENOMINATORS,
    DEFAULT_PLANNED_FIT_RUN_ID,
    DEFAULT_PREP_RUN_ID,
    LOCAL_ORIG_CONTRAST_ROOT,
    SUBHEAD_FIT_PROFILES,
    SUBHEAD_PROFILE_MANIFEST_KEYS,
    UNCHANGED_ORIGINAL_RECIPE_PARAMETERS,
    _format_lr_cli,
    evaluate_cal_guard_metrics_for_model,
    evaluate_cal_guard_report,
    validate_subhead_config_block,
    verify_git_commit_ancestor,
    verify_orig_relevant_source_provenance,
)

EXPECTED_PREP_SCHEMAS: Tuple[str, ...] = (
    "orig_fit2_return_contrast_prep.v2",
    "orig_fit2_return_contrast_prep.v3",
    "orig_fit2_return_contrast_prep.v4",
    "orig_fit2_zero_delta_control_prep.v1",
)

OPTION_A_LOCKED: Dict[str, Any] = dict(AUTHORIZED_FIT_PROFILES["option_a"])


def validate_profile_settings(
    *,
    profile: str,
    epochs: int,
    lr: float,
    batch_size: int,
    seed: int,
    fit_mode: str,
    enable_selective_rejector: bool,
    teacher_kl_weight: Optional[float] = None,
    teacher_temperature: Optional[float] = None,
    teacher_weights_sha256: Optional[str] = None,
    teacher_student_anchor_mode: Optional[str] = None,
    weight_decay: Optional[float] = None,
    trainable_scope: Optional[str] = None,
    feature_dropout_eval_mode: Optional[bool] = None,
) -> Dict[str, Any]:
    """Fail closed on any deviation from the locked parameters for an authorized fit profile."""
    if profile not in AUTHORIZED_FIT_PROFILES:
        raise ValueError(f"Unsupported profile {profile!r}; expected one of {sorted(AUTHORIZED_FIT_PROFILES)}")
    cfg = AUTHORIZED_FIT_PROFILES[profile]
    if int(epochs) != int(cfg["epochs"]):
        raise ValueError(f"{profile} enforces epochs={cfg['epochs']}; got {epochs}")
    if abs(float(lr) - float(cfg["lr"])) > 1e-12:
        raise ValueError(f"{profile} enforces lr={_format_lr_cli(float(cfg['lr']))}; got {lr}")
    if int(batch_size) != int(cfg["batch_size"]):
        raise ValueError(f"{profile} enforces batch_size={cfg['batch_size']}; got {batch_size}")
    if int(seed) != int(cfg["seed"]):
        raise ValueError(f"{profile} enforces seed={cfg['seed']}; got {seed}")
    if str(fit_mode) != str(cfg["fit_mode"]):
        raise ValueError(f"{profile} enforces fit_mode={cfg['fit_mode']!r}; got {fit_mode!r}")
    if bool(enable_selective_rejector) != bool(cfg["enable_selective_rejector"]):
        raise ValueError(f"{profile} enforces selective rejector OFF (enable_selective_rejector=False)")

    if profile in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic"):
        if teacher_kl_weight is None or abs(float(teacher_kl_weight) - float(cfg["teacher_kl_weight"])) > 1e-12:
            raise ValueError(
                f"{profile} requires explicit teacher_kl_weight={cfg['teacher_kl_weight']}; got {teacher_kl_weight!r}"
            )
        if teacher_temperature is None or abs(float(teacher_temperature) - float(cfg["teacher_temperature"])) > 1e-12:
            raise ValueError(
                f"{profile} requires explicit teacher_temperature={cfg['teacher_temperature']}; got {teacher_temperature!r}"
            )
        norm_sha = str(teacher_weights_sha256 or "").strip().lower()
        exp_sha = str(cfg["teacher_weights_sha256"]).lower()
        if norm_sha != exp_sha:
            raise ValueError(f"{profile} requires exact teacher_weights_sha256={exp_sha}; got {teacher_weights_sha256!r}")
        mode_val = str(teacher_student_anchor_mode or "").strip()
        if profile == "option_a_teacher_kl_deterministic":
            if mode_val != str(cfg["teacher_student_anchor_mode"]):
                raise ValueError(
                    f"{profile} requires explicit teacher_student_anchor_mode={cfg['teacher_student_anchor_mode']!r}; "
                    f"got {teacher_student_anchor_mode!r}"
                )
        elif mode_val and mode_val != "train_stochastic":
            raise ValueError(
                f"{profile} forbids non-stochastic teacher_student_anchor_mode; got {teacher_student_anchor_mode!r}"
            )
    else:
        if teacher_kl_weight is not None and abs(float(teacher_kl_weight)) > 1e-12:
            raise ValueError(f"{profile} forbids non-zero teacher_kl_weight; got {teacher_kl_weight!r}")
        if teacher_temperature is not None and abs(float(teacher_temperature) - 1.0) > 1e-12:
            raise ValueError(f"{profile} forbids custom teacher_temperature; got {teacher_temperature!r}")
        if teacher_weights_sha256 is not None and str(teacher_weights_sha256).strip():
            raise ValueError(f"{profile} forbids teacher_weights_sha256; got {teacher_weights_sha256!r}")
        if teacher_student_anchor_mode is not None and str(teacher_student_anchor_mode).strip():
            raise ValueError(f"{profile} forbids teacher_student_anchor_mode; got {teacher_student_anchor_mode!r}")

    if profile in SUBHEAD_FIT_PROFILES:
        if weight_decay is None or abs(float(weight_decay) - float(cfg["weight_decay"])) > 1e-12:
            raise ValueError(
                f"{profile} requires explicit weight_decay={cfg['weight_decay']}; got {weight_decay!r}"
            )
        if str(trainable_scope or "").strip() != str(cfg["trainable_scope"]):
            raise ValueError(
                f"{profile} requires explicit trainable_scope={cfg['trainable_scope']!r}; got {trainable_scope!r}"
            )
        if feature_dropout_eval_mode is not True:
            raise ValueError(
                f"{profile} requires explicit feature_dropout_eval_mode=True; got {feature_dropout_eval_mode!r}"
            )
    else:
        if weight_decay is not None and abs(float(weight_decay) - 0.01) > 1e-12:
            raise ValueError(f"{profile} forbids custom weight_decay; got {weight_decay!r}")
        if trainable_scope is not None and str(trainable_scope).strip() not in ("", "all"):
            raise ValueError(f"{profile} forbids non-all trainable_scope; got {trainable_scope!r}")
        if bool(feature_dropout_eval_mode):
            raise ValueError(f"{profile} forbids feature_dropout_eval_mode=True")
    return dict(cfg)


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
    validate_profile_settings(
        profile="option_a",
        epochs=epochs,
        lr=lr,
        batch_size=batch_size,
        seed=seed,
        fit_mode=fit_mode,
        enable_selective_rejector=enable_selective_rejector,
    )


def verify_locked_prep_bundle(
    *,
    prep_dir: Path,
    repo_root: Path,
    expected_prep_schemas: Tuple[str, ...] = EXPECTED_PREP_SCHEMAS,
    expected_profile: str | None = None,
) -> Dict[str, Any]:
    """Verify frozen prep bundle integrity, sidecar SHA inventory, datasets, ancestor commit, profile, and source SHAs."""
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
    schema_version = manifest.get("schema_version")
    if schema_version not in expected_prep_schemas:
        raise ValueError(
            f"Unexpected prep_manifest schema_version {schema_version!r}; expected one of {expected_prep_schemas!r}"
        )

    is_control = schema_version == "orig_fit2_zero_delta_control_prep.v1"
    preflight = manifest.get("preflight") or {}
    counts = preflight.get("counts") or {}
    if is_control:
        if preflight.get("extension_version") != "orig_fit2_zero_delta_control_v1":
            raise ValueError(
                f"Unexpected extension_version in zero-delta control prep_manifest: {preflight.get('extension_version')!r}"
            )
        if preflight.get("delta_absent") is not True or counts.get("extension_pos_train_added") != 0:
            raise ValueError(f"Zero-delta control prep_manifest must have delta_absent=True and added=0: {counts}")
        if counts.get("domain_pos_train") != 181 or counts.get("full_train_split_rows") != 11320 or counts.get("effective_train_total") != 13000:
            raise ValueError(f"Unexpected zero-delta control split counts in prep_manifest: {counts}")
        if (prep_dir / "datasets" / "orig_fit2_return_contrast_extension.jsonl").exists() or (
            prep_dir / "orig_fit2_return_contrast_extension.jsonl"
        ).exists():
            raise ValueError("Zero-delta control prep bundle unexpectedly contains orig_fit2_return_contrast_extension.jsonl")
    else:
        if preflight.get("extension_version") != "orig_fit2_return_channel_contrast_v2":
            raise ValueError(f"Unexpected extension_version in prep_manifest: {preflight.get('extension_version')!r}")
        if counts.get("extension_pos_train_added") != 18:
            raise ValueError(f"Unexpected extension row count in prep_manifest: {counts}")

    if (manifest.get("unchanged_original_recipe_parameters") or {}) != UNCHANGED_ORIGINAL_RECIPE_PARAMETERS:
        raise ValueError("prep_manifest unchanged_original_recipe_parameters drifted from expected Fit2 constants")

    if schema_version in ("orig_fit2_return_contrast_prep.v4", "orig_fit2_zero_delta_control_prep.v1"):
        auth_profile = manifest.get("authorized_fit_profile") or {}
        prep_profile = str(auth_profile.get("profile") or "")
        if prep_profile not in AUTHORIZED_FIT_PROFILES:
            raise ValueError(f"Invalid authorized_fit_profile in prep_manifest: {auth_profile}")
        if is_control and prep_profile != "option_a":
            raise ValueError(f"Zero-delta control requires authorized_fit_profile='option_a'; got {prep_profile!r}")
        expected_cfg = AUTHORIZED_FIT_PROFILES[prep_profile]
        plan = manifest.get("execution_plan") or {}
        if is_control and (
            plan.get("experiment_mode") != "matched_zero_delta_control"
            or plan.get("is_promotion_candidate") is not False
        ):
            raise ValueError(f"Invalid zero-delta control execution_plan metadata: {plan}")
        for holder_name, holder in (("authorized_fit_profile", auth_profile), ("execution_plan", plan)):
            if (
                holder.get("profile") != prep_profile
                or int(holder.get("epochs", -1)) != int(expected_cfg["epochs"])
                or abs(float(holder.get("lr", -1.0)) - float(expected_cfg["lr"])) > 1e-12
                or int(holder.get("batch_size", -1)) != int(expected_cfg["batch_size"])
                or int(holder.get("seed", -1)) != int(expected_cfg["seed"])
                or str(holder.get("fit_mode")) != str(expected_cfg["fit_mode"])
                or bool(holder.get("enable_selective_rejector", True)) is not False
                or str(holder.get("init_weights_sha256", "")).lower() != EXPECTED_FIT2_SHA256
            ):
                raise ValueError(f"Invalid {holder_name} in prep_manifest: {holder}")
            if prep_profile in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic") and (
                abs(float(holder.get("teacher_kl_weight", -1.0)) - float(expected_cfg["teacher_kl_weight"])) > 1e-12
                or abs(float(holder.get("teacher_temperature", -1.0)) - float(expected_cfg["teacher_temperature"])) > 1e-12
                or str(holder.get("teacher_weights_sha256", "")).lower() != str(expected_cfg["teacher_weights_sha256"]).lower()
            ):
                raise ValueError(f"Invalid teacher-KL config in {holder_name}: {holder}")
            if prep_profile == "option_a_teacher_kl_deterministic" and (
                str(holder.get("teacher_student_anchor_mode", "")) != str(expected_cfg["teacher_student_anchor_mode"])
            ):
                raise ValueError(f"Invalid teacher_student_anchor_mode in {holder_name}: {holder}")
            if prep_profile in SUBHEAD_FIT_PROFILES and (
                abs(float(holder.get("weight_decay", -1.0)) - float(expected_cfg["weight_decay"])) > 1e-12
                or str(holder.get("trainable_scope", "")) != str(expected_cfg["trainable_scope"])
                or holder.get("feature_dropout_eval_mode") is not True
                or int(holder.get("expected_trainable_param_count", -1)) != int(expected_cfg["expected_trainable_param_count"])
                or int(holder.get("expected_frozen_param_count", -1)) != int(expected_cfg["expected_frozen_param_count"])
            ):
                raise ValueError(f"Invalid subhead scope config in {holder_name}: {holder}")

        tkl_cfg = manifest.get("teacher_anchor_config")
        if prep_profile in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic"):
            if (
                not isinstance(tkl_cfg, dict)
                or tkl_cfg.get("enabled") is not True
                or abs(float(tkl_cfg.get("teacher_kl_weight", -1.0)) - float(expected_cfg["teacher_kl_weight"])) > 1e-12
                or abs(float(tkl_cfg.get("teacher_temperature", -1.0)) - float(expected_cfg["teacher_temperature"])) > 1e-12
                or str(tkl_cfg.get("teacher_weights_sha256", "")).lower() != str(expected_cfg["teacher_weights_sha256"]).lower()
                or int(tkl_cfg.get("anchor_effective_count", -1)) != 13000
                or int(tkl_cfg.get("excluded_effective_count", -1)) != 80
            ):
                raise ValueError(f"Invalid teacher_anchor_config in prep_manifest: {tkl_cfg}")
            if prep_profile == "option_a_teacher_kl_deterministic" and (
                str(tkl_cfg.get("teacher_student_anchor_mode", "")) != str(expected_cfg["teacher_student_anchor_mode"])
            ):
                raise ValueError(f"Invalid teacher_student_anchor_mode in teacher_anchor_config: {tkl_cfg}")
            if prep_profile == "option_a_teacher_kl" and tkl_cfg.get("teacher_student_anchor_mode") not in (
                None,
                "train_stochastic",
            ):
                raise ValueError(f"Stochastic teacher-KL prep has invalid anchor mode: {tkl_cfg}")
        elif tkl_cfg is not None:
            raise ValueError(f"Unexpected teacher_anchor_config in non-teacher-KL prep profile {prep_profile!r}")

        for sub_prof, mkey in SUBHEAD_PROFILE_MANIFEST_KEYS.items():
            sub_block = manifest.get(mkey)
            if prep_profile == sub_prof:
                validate_subhead_config_block(sub_block, prep_profile)
            elif sub_block is not None:
                raise ValueError(f"Unexpected {mkey} in prep profile {prep_profile!r}")

        base_cal_ref = manifest.get("baseline_cal_reference") or {}
        base_metrics = base_cal_ref.get("metrics") or {}
        expected_surfaces = (
            [k for k in CAL_GUARD_DENOMINATORS if k != "pos_train_added_18"]
            if is_control
            else list(CAL_GUARD_DENOMINATORS)
        )
        missing_surfaces = [k for k in expected_surfaces if k not in base_metrics]
        if (
            str(base_cal_ref.get("baseline_weights_sha256", "")).lower() != EXPECTED_FIT2_SHA256
            or not base_cal_ref.get("baseline_calibration_manifest_sha256")
            or (base_cal_ref.get("dataset_hashes") or {}) != (preflight.get("dataset_hashes") or {})
            or missing_surfaces
            or (is_control and "pos_train_added_18" in base_metrics)
        ):
            raise ValueError(
                f"Invalid or incomplete baseline_cal_reference in prep_manifest (missing={missing_surfaces})"
            )
    else:
        prep_profile = "option_a"
        plan = manifest.get("option_a_execution_plan") or {}
        if (plan.get("epochs"), plan.get("lr"), plan.get("enable_selective_rejector")) != (3, 2e-5, False):
            raise ValueError(f"Invalid option_a_execution_plan in prep_manifest: {plan}")
        base_cal_ref = manifest.get("baseline_cal_reference")

    if expected_profile is not None and prep_profile != expected_profile:
        raise ValueError(
            f"Requested profile {expected_profile!r} mismatches locked prep authorized_fit_profile {prep_profile!r}"
        )

    ds_dir = prep_dir / "datasets"
    ds_hashes = preflight.get("dataset_hashes") or {}
    _verify_dir_matches_lock_hashes(ds_dir, ds_hashes)
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
    if is_control:
        orig_ref_hashes = preflight.get("orig_fit2_stage2_reference_hashes") or {}
        if set(new_input_hashes.keys()) != set(EXPECTED_ORIG_STAGE2_LOCKED_FILES):
            raise ValueError(
                f"Zero-delta control new_input_file_hashes must cover exact 13 orig files; "
                f"got={sorted(new_input_hashes.keys())}"
            )
        bit_diffs = [
            fname
            for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES
            if str(new_input_hashes.get(fname, "")).lower() != str(orig_ref_hashes.get(fname, "")).lower()
        ]
        if bit_diffs or len(orig_ref_hashes) != len(EXPECTED_ORIG_STAGE2_LOCKED_FILES):
            raise ValueError(
                f"Zero-delta control inputs not bit-identical to 13 Original Fit2 stage2 files: {bit_diffs}"
            )

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
        "prep_schema_version": schema_version,
        "authorized_fit_profile": prep_profile,
        "baseline_cal_reference": base_cal_ref,
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


def run_authorized_fit(
    *,
    repo_root: Path,
    prep_dir: Path,
    run_id: str,
    profile: str,
    epochs: int,
    lr: float,
    batch_size: int = 32,
    seed: int = 42,
    fit_mode: str = "fit2_supcon_energy",
    enable_selective_rejector: bool = False,
    teacher_kl_weight: Optional[float] = None,
    teacher_temperature: Optional[float] = None,
    teacher_weights_sha256: Optional[str] = None,
    teacher_student_anchor_mode: Optional[str] = None,
    teacher_model_dir: Optional[Path] = None,
    weight_decay: Optional[float] = None,
    trainable_scope: Optional[str] = None,
    feature_dropout_eval_mode: Optional[bool] = None,
    execute_fit: bool = False,
    main_candidates_dir: Path = MAIN_CANDIDATES_DIR,
    local_root_base: Path = LOCAL_ORIG_CONTRAST_ROOT,
    init_model_dir: Path = FIT2_BASELINE_DIR,
    serving_dir: Path = SERVING_DIR,
) -> Dict[str, Any]:
    """Verify profile + locked prep guards and optionally execute & archive one continuation fit with CAL guard."""
    profile_cfg = validate_profile_settings(
        profile=profile,
        epochs=epochs,
        lr=lr,
        batch_size=batch_size,
        seed=seed,
        fit_mode=fit_mode,
        enable_selective_rejector=enable_selective_rejector,
        teacher_kl_weight=teacher_kl_weight,
        teacher_temperature=teacher_temperature,
        teacher_weights_sha256=teacher_weights_sha256,
        teacher_student_anchor_mode=teacher_student_anchor_mode,
        weight_decay=weight_decay,
        trainable_scope=trainable_scope,
        feature_dropout_eval_mode=feature_dropout_eval_mode,
    )
    out_paths = _check_output_paths_unused(
        run_id=run_id,
        main_candidates_dir=main_candidates_dir,
        local_root_base=local_root_base,
    )
    prep_verified = verify_locked_prep_bundle(
        prep_dir=prep_dir,
        repo_root=repo_root,
        expected_profile=profile,
    )

    serving_weights = serving_dir / "model.safetensors"
    if not serving_weights.is_file():
        raise FileNotFoundError(f"Missing Serving checkpoint weights: {serving_weights}")
    serving_sha = _sha256_lower(serving_weights)
    if serving_sha != EXPECTED_SERVING_SHA256:
        raise ValueError(f"Serving weights SHA mismatch: {serving_sha} != {EXPECTED_SERVING_SHA256}")

    init_info = verify_fit2_starting_checkpoint(init_model_dir)
    is_teacher_kl = profile in ("option_a_teacher_kl", "option_a_teacher_kl_deterministic")
    is_det_teacher_kl = profile == "option_a_teacher_kl_deterministic"
    is_subhead = profile in SUBHEAD_FIT_PROFILES
    subhead_manifest_key = SUBHEAD_PROFILE_MANIFEST_KEYS.get(profile)
    resolved_teacher_dir = (teacher_model_dir if teacher_model_dir is not None else init_model_dir) if is_teacher_kl else None
    if is_teacher_kl:
        assert resolved_teacher_dir is not None
        t_weights = resolved_teacher_dir / "model.safetensors"
        if not t_weights.is_file():
            raise FileNotFoundError(f"Missing frozen teacher weights: {t_weights}")
        t_sha = _sha256_lower(t_weights)
        if t_sha != str(profile_cfg["teacher_weights_sha256"]).lower():
            raise ValueError(f"Teacher checkpoint SHA mismatch: {t_sha} != {profile_cfg['teacher_weights_sha256']}")

    if not execute_fit:
        val_res: Dict[str, Any] = {
            "validated_only": True,
            "fits_executed": 0,
            "prep_dir": str(prep_dir),
            "prep_schema_version": prep_verified["prep_schema_version"],
            "prep_manifest_sha256": prep_verified["manifest_sha256"],
            "prep_git_commit": prep_verified["prep_git_commit"],
            "head_git_commit": prep_verified["head_git_commit"],
            "git_commit": prep_verified["head_git_commit"],
            "authorized_fit_profile": profile,
            "starting_checkpoint": init_info,
            "serving_weights_sha256": serving_sha,
            "profile_settings": profile_cfg,
            "planned_outputs": {k: str(v) for k, v in out_paths.items()},
        }
        if is_teacher_kl:
            val_tkl_cfg: Dict[str, Any] = {
                "teacher_model_dir": str(resolved_teacher_dir),
                "teacher_weights_sha256": str(profile_cfg["teacher_weights_sha256"]),
                "teacher_kl_weight": float(profile_cfg["teacher_kl_weight"]),
                "teacher_temperature": float(profile_cfg["teacher_temperature"]),
            }
            if is_det_teacher_kl:
                val_tkl_cfg["teacher_student_anchor_mode"] = str(profile_cfg["teacher_student_anchor_mode"])
            val_res["teacher_anchor_config"] = val_tkl_cfg
        if is_subhead:
            assert subhead_manifest_key is not None
            val_res[subhead_manifest_key] = prep_verified["manifest"].get(subhead_manifest_key)
        return val_res

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
    run_config_payload: Dict[str, Any] = {
        "git_commit": git_sha,
        "head_git_commit": git_sha,
        "prep_git_commit": prep_git_sha,
        "prep_schema_version": prep_verified["prep_schema_version"],
        "source_hashes": source_prov["source_hashes"],
        "cli_argv": list(sys.argv),
        "prep_dir": str(prep_dir),
        "prep_manifest_sha256": prep_verified["manifest_sha256"],
        "authorized_fit_profile": profile,
        "init_model_dir": str(init_model_dir),
        "init_weights_sha256": EXPECTED_FIT2_SHA256,
        "fit_mode": str(profile_cfg["fit_mode"]),
        "epochs": int(profile_cfg["epochs"]),
        "batch_size": int(profile_cfg["batch_size"]),
        "lr": float(profile_cfg["lr"]),
        "seed": int(profile_cfg["seed"]),
        "min_temperature": float(profile_cfg["min_temperature"]),
        "enable_selective_rejector": bool(profile_cfg["enable_selective_rejector"]),
        "dataset_hashes": prep_verified["dataset_hashes"],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if is_teacher_kl:
        run_tkl_cfg: Dict[str, Any] = {
            "teacher_model_dir": str(resolved_teacher_dir),
            "teacher_weights_sha256": str(profile_cfg["teacher_weights_sha256"]),
            "teacher_kl_weight": float(profile_cfg["teacher_kl_weight"]),
            "teacher_temperature": float(profile_cfg["teacher_temperature"]),
        }
        if is_det_teacher_kl:
            run_tkl_cfg["teacher_student_anchor_mode"] = str(profile_cfg["teacher_student_anchor_mode"])
        run_config_payload["teacher_anchor_config"] = run_tkl_cfg
    if is_subhead:
        assert subhead_manifest_key is not None
        run_config_payload[subhead_manifest_key] = {
            "weight_decay": float(profile_cfg["weight_decay"]),
            "trainable_scope": str(profile_cfg["trainable_scope"]),
            "feature_dropout_eval_mode": bool(profile_cfg["feature_dropout_eval_mode"]),
            "expected_trainable_param_count": int(profile_cfg["expected_trainable_param_count"]),
            "expected_frozen_param_count": int(profile_cfg["expected_frozen_param_count"]),
            "teacher_used": False,
        }
    (records_dir / "run_config.json").write_text(json.dumps(run_config_payload, indent=2) + "\n", encoding="utf-8")

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
            "authorized_fit_profile": profile,
            "lr": float(profile_cfg["lr"]),
            "prep_dir": str(prep_dir),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            **extra,
        }
        (records_dir / "status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    is_control = prep_verified["prep_schema_version"] == "orig_fit2_zero_delta_control_prep.v1"
    output_subdir = (
        "candidate_model_zero_delta_control"
        if is_control
        else ("candidate_model_option_a" if profile == "option_a" else f"candidate_model_{profile}")
    )
    _write_status("training", fits_started=1, fits_completed=0)
    _log(
        f"Starting authorized fit profile={profile} lr={_format_lr_cli(float(profile_cfg['lr']))} "
        f"run_id={run_id} prep_dir={prep_dir} init={EXPECTED_FIT2_SHA256}"
    )
    cal_guard_report: Dict[str, Any] | None = None
    cal_guard_passed: bool | None = None
    cal_guard_status = "NOT_CONFIGURED_IN_LEGACY_PREP"
    cal_guard_failed_checks: list[str] = []
    try:
        trainer_kwargs: Dict[str, Any] = {}
        if is_teacher_kl:
            trainer_kwargs = {
                "teacher_kl_weight": float(profile_cfg["teacher_kl_weight"]),
                "teacher_temperature": float(profile_cfg["teacher_temperature"]),
                "teacher_model_dir": resolved_teacher_dir,
                "expected_teacher_weights_sha256": str(profile_cfg["teacher_weights_sha256"]),
            }
            if is_det_teacher_kl:
                trainer_kwargs["teacher_student_anchor_mode"] = str(profile_cfg["teacher_student_anchor_mode"])
        if is_subhead:
            trainer_kwargs.update(
                {
                    "trainable_scope": str(profile_cfg["trainable_scope"]),
                    "feature_dropout_eval_mode": bool(profile_cfg["feature_dropout_eval_mode"]),
                    "weight_decay": float(profile_cfg["weight_decay"]),
                    "expected_trainable_param_count": int(profile_cfg["expected_trainable_param_count"]),
                    "expected_frozen_param_count": int(profile_cfg["expected_frozen_param_count"]),
                }
            )
        fit_result = run_fit_and_lock_candidate(
            worktree_root=repo_root,
            data_repo_root=repo_root,
            init_model_dir=init_model_dir,
            artifact_root=local_root,
            fit_mode=str(profile_cfg["fit_mode"]),
            output_subdir=output_subdir,
            epochs=int(profile_cfg["epochs"]),
            batch_size=int(profile_cfg["batch_size"]),
            lr=float(profile_cfg["lr"]),
            seed=int(profile_cfg["seed"]),
            enable_selective_rejector=bool(profile_cfg["enable_selective_rejector"]),
            candidate_name=run_id,
            **trainer_kwargs,
        )
        cand_dir = local_root / output_subdir
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
        if is_teacher_kl:
            assert resolved_teacher_dir is not None
            post_t_sha = _sha256_lower(resolved_teacher_dir / "model.safetensors")
            if post_t_sha != str(profile_cfg["teacher_weights_sha256"]).lower():
                raise RuntimeError(f"Teacher weights SHA changed post-fit: {post_t_sha}")
            prov_json = json.loads((archive_dir / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))
            t_lineage = prov_json.get("training_lineage") or {}
            if (
                t_lineage.get("teacher_kl_enabled") is not True
                or str(t_lineage.get("teacher_weights_sha256", "")).lower()
                != str(profile_cfg["teacher_weights_sha256"]).lower()
                or abs(float(t_lineage.get("teacher_kl_weight", -1.0)) - float(profile_cfg["teacher_kl_weight"])) > 1e-12
                or abs(float(t_lineage.get("teacher_temperature", -1.0)) - float(profile_cfg["teacher_temperature"]))
                > 1e-12
                or (
                    is_det_teacher_kl
                    and str(t_lineage.get("teacher_student_anchor_mode", ""))
                    != str(profile_cfg["teacher_student_anchor_mode"])
                )
            ):
                raise ValueError(f"Candidate provenance manifest missing valid teacher-KL lineage: {t_lineage}")
        if is_subhead:
            assert subhead_manifest_key is not None
            prov_json = json.loads((archive_dir / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))
            h_lineage = prov_json.get("training_lineage") or {}
            prep_head_cfg = prep_verified["manifest"].get(subhead_manifest_key) or {}
            if (
                str(h_lineage.get("trainable_scope", "")) != str(profile_cfg["trainable_scope"])
                or h_lineage.get("feature_dropout_eval_mode") is not True
                or abs(float(h_lineage.get("weight_decay", -1.0)) - float(profile_cfg["weight_decay"])) > 1e-12
                or int(h_lineage.get("trainable_param_count", -1)) != int(profile_cfg["expected_trainable_param_count"])
                or int(h_lineage.get("frozen_param_count", -1)) != int(profile_cfg["expected_frozen_param_count"])
                or h_lineage.get("post_fit_freeze_verified") is not True
                or h_lineage.get("teacher_kl_enabled") is True
                or str(h_lineage.get("post_fit_frozen_tensors_sha256", ""))
                != str(prep_head_cfg.get("initial_frozen_tensors_sha256", ""))
                or (
                    profile == "option_a_pre_classifier_head_v1"
                    and h_lineage.get("trainable_layer_update_verified") is not True
                )
            ):
                raise ValueError(f"Candidate provenance manifest failed {profile} verification: {h_lineage}")

        reload_info = verify_reload_from_archive(archive_dir)
        archive_inv = _write_and_verify_sha_inventory(archive_dir, "archive_sha_inventory.json")
        (records_dir / "fit_result.json").write_text(json.dumps(fit_result, indent=2) + "\n", encoding="utf-8")

        base_cal_ref = prep_verified.get("baseline_cal_reference")
        if base_cal_ref is not None:
            cand_cal_metrics = (
                evaluate_cal_guard_metrics_for_model(archive_dir, records_dir / "inputs", include_added_18=False)
                if is_control
                else evaluate_cal_guard_metrics_for_model(archive_dir, records_dir / "inputs")
            )
            cal_guard_report = evaluate_cal_guard_report(
                cand_cal_metrics,
                base_cal_ref["metrics"],
                cal_guard_mode="control" if is_control else "candidate",
            )
            (records_dir / "cal_guard_report.json").write_text(
                json.dumps(cal_guard_report, indent=2) + "\n", encoding="utf-8"
            )
            cal_guard_passed = bool(cal_guard_report["passed"])
            cal_guard_status = str(cal_guard_report["recommended_status"])
            cal_guard_failed_checks = list(cal_guard_report["failed_checks"])
            _log(
                f"CAL guard completed: passed={cal_guard_passed} status={cal_guard_status} "
                f"failed={cal_guard_failed_checks}"
            )

        _log(
            f"Archived & verified candidate_dir={archive_dir} T={cal_check.get('temperature')} "
            f"files={len(archive_inv)} reload_labels={reload_info.get('num_labels')}"
        )
    except Exception as exc:
        _log(f"FAILED: {exc}")
        _write_status("incomplete", fits_started=1, fits_completed=0, error=str(exc))
        raise

    _write_status(
        "complete",
        fits_started=1,
        fits_completed=1,
        archive_dir=str(archive_dir),
        cal_guard_passed=cal_guard_passed,
        cal_guard_status=cal_guard_status,
        cal_guard_failed_checks=cal_guard_failed_checks,
    )
    sidecar_inv = _write_and_verify_sha_inventory(records_dir, "sidecar_sha_inventory.json")
    return {
        "validated_only": False,
        "fits_executed": 1,
        "authorized_fit_profile": profile,
        "fit_result": fit_result,
        "archive_dir": str(archive_dir),
        "records_dir": str(records_dir),
        "calibration_audit": {"valid": cal_check["valid"], "temperature": cal_check["temperature"]},
        "provenance_audit": {"provenance_passed": prov_check["provenance_passed"], "num_labels": prov_check["num_labels"]},
        "reload": reload_info,
        "cal_guard_passed": cal_guard_passed,
        "cal_guard_status": cal_guard_status,
        "cal_guard_failed_checks": cal_guard_failed_checks,
        "archive_sha_inventory_count": len(archive_inv),
        "sidecar_sha_inventory_count": len(sidecar_inv),
    }


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
    """Backwards-compatible Option A (profile='option_a', lr=2e-5) entrypoint."""
    return run_authorized_fit(
        repo_root=repo_root,
        prep_dir=prep_dir,
        run_id=run_id,
        profile="option_a",
        epochs=epochs,
        lr=lr,
        batch_size=batch_size,
        seed=seed,
        fit_mode=fit_mode,
        enable_selective_rejector=enable_selective_rejector,
        execute_fit=execute_fit,
        main_candidates_dir=main_candidates_dir,
        local_root_base=local_root_base,
        init_model_dir=init_model_dir,
        serving_dir=serving_dir,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Fail-closed Fit2 return-channel continuation runner (profile-locked)")
    ap.add_argument(
        "--prep-dir",
        type=Path,
        default=MAIN_CANDIDATES_DIR / f"run-records-{DEFAULT_PREP_RUN_ID}-prep",
        help="Locked prep bundle directory",
    )
    ap.add_argument("--run-id", default=DEFAULT_PLANNED_FIT_RUN_ID)
    ap.add_argument(
        "--profile",
        required=True,
        choices=tuple(AUTHORIZED_FIT_PROFILES.keys()),
        help="Authorized hyperparameter profile (must match locked prep authorized_fit_profile)",
    )
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, required=True, help="Explicit learning rate (must match --profile)")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fit-mode", default="fit2_supcon_energy")
    ap.add_argument("--enable-selective-rejector", action="store_true")
    ap.add_argument("--teacher-kl-weight", type=float, default=None)
    ap.add_argument("--teacher-temperature", type=float, default=None)
    ap.add_argument("--teacher-weights-sha256", type=str, default=None)
    ap.add_argument("--teacher-student-anchor-mode", type=str, default=None)
    ap.add_argument("--weight-decay", type=float, default=None)
    ap.add_argument("--trainable-scope", type=str, default=None, choices=VALID_TRAINABLE_SCOPES)
    ap.add_argument("--feature-dropout-eval-mode", action="store_true")
    ap.add_argument("--validate-only", action="store_true", help="Run fail-closed profile & locked prep checks without fitting")
    ap.add_argument("--run-authorized-fit", action="store_true", help="Execute the single authorized continuation fit for --profile")
    ap.add_argument("--run-option-a-fit", action="store_true", help="Legacy Option A execution flag (requires --profile option_a)")
    args = ap.parse_args()

    if args.run_authorized_fit and args.run_option_a_fit:
        raise ValueError("Specify at most one of --run-authorized-fit or --run-option-a-fit")
    execute_fit = bool(args.run_authorized_fit or args.run_option_a_fit)
    if args.validate_only == execute_fit:
        raise ValueError("Specify exactly one of --validate-only or (--run-authorized-fit / --run-option-a-fit)")
    if args.run_option_a_fit and args.profile != "option_a":
        raise ValueError("--run-option-a-fit requires --profile option_a; use --run-authorized-fit for lr5e6")

    repo_root = Path(__file__).resolve().parents[1]
    res = run_authorized_fit(
        repo_root=repo_root,
        prep_dir=args.prep_dir.resolve(),
        run_id=args.run_id,
        profile=args.profile,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        seed=args.seed,
        fit_mode=args.fit_mode,
        enable_selective_rejector=args.enable_selective_rejector,
        teacher_kl_weight=args.teacher_kl_weight,
        teacher_temperature=args.teacher_temperature,
        teacher_weights_sha256=args.teacher_weights_sha256,
        teacher_student_anchor_mode=args.teacher_student_anchor_mode,
        weight_decay=args.weight_decay,
        trainable_scope=args.trainable_scope,
        feature_dropout_eval_mode=args.feature_dropout_eval_mode,
        execute_fit=execute_fit,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

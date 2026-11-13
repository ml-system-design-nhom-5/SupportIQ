"""Faithful Fit2 restoration entrypoint: Stage 1 (c6cae7a fit1_closure_dual_head) -> Stage 2 (d7ddaf2 fit2_supcon_energy).

Fail-closed preflight validates Serving, canonical prep 13-11-2026-00, Stage 1 46-label
replay+closure data, and Stage 2 d7ddaf2 reconstructed splits BEFORE any training runs.
Runs ONLY the selected single fit per stage, archives each stage with full calibration +
provenance + SHA inventory to MAIN, and verifies reload + lineage before Stage 2.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from apps.core_backend.intent.routing import STANDARD_INTENTS_46, load_policy_v2
from pipeline.evaluation.classifier_acceptance_gate import validate_calibration_manifest
from pipeline.training.closure_domain_data import export_closure_datasets
from pipeline.training.train_boundary_candidate import (
    prepare_and_lock_splits,
    run_fit_and_lock_candidate,
    verify_reload_from_archive,
)
from pipeline.training.train_closure_candidate import (
    _build_closure_rejector_on_train_and_cal,
    _train_closure_single_fit,
)
from pipeline.training.train_domain_candidate import (
    build_replay_and_domain_train_df,
    verify_original_46_label_lineage,
)
from pipeline.training.train_selective_candidate import (
    SUPPORTED_11_DRAFT_INTENTS,
    write_calibration_manifest,
)

SERVING_DIR = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\trained\distilbert-supportiq")
EXPECTED_SERVING_SHA256 = "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302"
MAIN_CANDIDATES_DIR = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts\models\candidates")
ORIG_SIDECAR_DIR = MAIN_CANDIDATES_DIR / "run-records-original-fit2-20261113"
LOCAL_RESTORE_ROOT = Path(__file__).resolve().parents[1] / "artifacts/evaluation/original_fit2_restore"


def _sha256_lower(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while c := f.read(65536):
            h.update(c)
    return h.hexdigest().lower()


def _sha256_json_rows(rows: List[Dict[str, Any]]) -> str:
    payload = "\n".join(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().lower()


def _archive_to_main(local_dir: Path, archive_dir: Path) -> Dict[str, Any]:
    if archive_dir.exists():
        raise FileExistsError(f"Archive already exists (immutable): {archive_dir}")
    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(local_dir, archive_dir)
    inv = {p.name: _sha256_lower(p) for p in sorted(archive_dir.iterdir()) if p.is_file()}
    (archive_dir / "archive_sha_inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")
    reload_res = verify_reload_from_archive(archive_dir)
    return {"archive_dir": str(archive_dir), "files": len(inv), "reload_check": reload_res}


def assemble_stage1_closure_data(repo_root: Path, datasets_dir: Path, seed: int = 42) -> Dict[str, Any]:
    """Assemble exact c6cae7a Stage 1 positive CE replay+domain data & rejector train/cal splits."""
    lineage = verify_original_46_label_lineage(repo_root=repo_root)
    ds_manifest = export_closure_datasets(datasets_dir, repo_root=repo_root)

    def _load(name: str) -> List[Dict[str, Any]]:
        return [json.loads(l) for l in (datasets_dir / name).read_text(encoding="utf-8").splitlines() if l.strip()]

    pos_train = _load("closure_positive_train.jsonl")
    neg_train = _load("closure_negative_train.jsonl")
    pos_cal = _load("closure_positive_calibration.jsonl")
    neg_cal = _load("closure_negative_calibration.jsonl")

    replay_domain_train_df, bitext_cal_df = build_replay_and_domain_train_df(
        lineage,
        pos_train,
        replay_per_other_label=80,
        replay_per_supported_label=35,
        domain_train_repeat=4,
        cal_per_label=5,
        seed=seed,
    )
    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}
    pos_train_texts = replay_domain_train_df["instruction"].tolist()
    pos_train_labels = [label2id[x] for x in replay_domain_train_df["intent"].tolist()]
    pos_train_flags = [0] * len(pos_train_texts)

    bitext_train_only = lineage.train_df[~lineage.train_df["sample_id"].isin(set(bitext_cal_df["sample_id"]))].copy()
    bitext_sup11_df = pd.concat(
        [
            bitext_train_only[bitext_train_only["intent"] == lbl].sample(
                n=min(35, len(bitext_train_only[bitext_train_only["intent"] == lbl])),
                random_state=seed + i,
            )
            for i, lbl in enumerate(SUPPORTED_11_DRAFT_INTENTS)
        ],
        ignore_index=True,
    )
    non_draft_intents = [lbl for lbl in STANDARD_INTENTS_46 if lbl not in SUPPORTED_11_DRAFT_INTENTS]
    bitext_nondraft_df = pd.concat(
        [
            bitext_train_only[bitext_train_only["intent"] == lbl].sample(
                n=min(8, len(bitext_train_only[bitext_train_only["intent"] == lbl])),
                random_state=seed + 100 + i,
            )
            for i, lbl in enumerate(non_draft_intents)
        ],
        ignore_index=True,
    )
    dom_sup11_train = [r for r in pos_train if r["intent"] in SUPPORTED_11_DRAFT_INTENTS]
    dom_nondraft_train = [r for r in pos_train if r["intent"] not in SUPPORTED_11_DRAFT_INTENTS]

    rej_y1_texts = [r["instruction"] for _ in range(4) for r in dom_sup11_train] + bitext_sup11_df["instruction"].tolist()
    rej_y0_texts = (
        [r["instruction"] for _ in range(6) for r in neg_train]
        + [r["instruction"] for _ in range(2) for r in dom_nondraft_train]
        + bitext_nondraft_df["instruction"].tolist()
    )
    return {
        "lineage": lineage,
        "ds_manifest": ds_manifest,
        "pos_train_texts": pos_train_texts,
        "pos_train_labels": pos_train_labels,
        "pos_train_flags": pos_train_flags,
        "rej_train_texts": rej_y1_texts + rej_y0_texts,
        "rej_train_y": ([1] * len(rej_y1_texts)) + ([0] * len(rej_y0_texts)),
        "cal_pos_df": pd.DataFrame(pos_cal),
        "cal_neg_df": pd.DataFrame(neg_cal),
        "bitext_cal_df": bitext_cal_df,
        "replay_domain_train_df": replay_domain_train_df,
    }


def run_preflight_validation(repo_root: Path, dryrun_root: Path) -> Dict[str, Any]:
    """Fail-closed preflight: recomputes & verifies all Stage 1 + Stage 2 data hashes, splits, and Serving."""
    serving_sha = _sha256_lower(SERVING_DIR / "model.safetensors")
    if serving_sha != EXPECTED_SERVING_SHA256:
        raise RuntimeError(f"Serving SHA mismatch: {serving_sha}")

    mdl = AutoModelForSequenceClassification.from_pretrained(str(SERVING_DIR), local_files_only=True)
    id2label = {int(k): v for k, v in mdl.config.id2label.items()}
    if len(id2label) != 46 or set(id2label.values()) != set(STANDARD_INTENTS_46):
        raise RuntimeError("Invalid 46-label bijection on Serving model")

    # Stage 1: always re-export & assemble from canonical prep (never trust stale lock)
    s1_ds_dir = dryrun_root / "stage1_datasets"
    s1 = assemble_stage1_closure_data(repo_root, s1_ds_dir, seed=42)
    c6_ref_manifest = json.loads(
        (ORIG_SIDECAR_DIR / "c6cae7a/artifacts/evaluation/task_a_closure_20261113/datasets/closure_dataset_manifest.json").read_text(encoding="utf-8")
    )
    c6_hashes_ok = {}
    for k, meta in c6_ref_manifest.get("files", {}).items():
        p = s1_ds_dir / Path(meta["path"]).name
        c6_hashes_ok[k] = p.is_file() and (_sha256_lower(p).upper() == str(meta["sha256"]).upper())
    if not c6_hashes_ok or not all(c6_hashes_ok.values()):
        raise RuntimeError(f"Stage 1 closure dataset hash mismatch: {c6_hashes_ok}")
    if len(set(s1["pos_train_labels"])) != 46 or any(f != 0 for f in s1["pos_train_flags"]):
        raise RuntimeError("Stage 1 positive CE must cover all 46 labels with zero OOD rows")
    if set(s1["replay_domain_train_df"]["sample_id"].dropna()) & set(s1["bitext_cal_df"]["sample_id"].dropna()):
        raise RuntimeError("Stage 1 replay train and bitext cal sample_id overlap detected")

    # Stage 2: always recompute prepare_and_lock_splits (never reuse stale dataset_lock_manifest.json)
    d7_lock = json.loads(
        (ORIG_SIDECAR_DIR / "d7ddaf2/artifacts/evaluation/task_a_boundary_20261113/datasets/dataset_lock_manifest.json").read_text(encoding="utf-8")
    )
    new_lock = prepare_and_lock_splits(
        worktree_root=repo_root,
        data_repo_root=Path(r"F:\Năm 3\SD\project\SupportIQ"),
        init_model_dir=SERVING_DIR,
        artifact_root=dryrun_root,
    )
    d7_hashes_ok = {k: (new_lock["dataset_hashes"].get(k) == v) for k, v in d7_lock["dataset_hashes"].items()}
    if not d7_hashes_ok or not all(d7_hashes_ok.values()):
        raise RuntimeError(f"Stage 2 boundary dataset hash mismatch: {d7_hashes_ok}")
    flagged = {k: v["flagged_count"] for k, v in new_lock["boundary_audit_summary"].items()}
    if any(v > 0 for v in flagged.values()):
        raise RuntimeError(f"Stage 2 boundary audit flagged overlaps: {flagged}")

    return {
        "dry_run": True,
        "fits_executed": 0,
        "serving_weights_sha256": serving_sha,
        "valid_46_label_bijection": True,
        "canonical_prep": {
            "cleaned_sha256": s1["lineage"].cleaned_sha256,
            "splits_sha256": s1["lineage"].splits_sha256,
        },
        "stage1_c6cae7a_dataset_hashes_match": c6_hashes_ok,
        "stage1_assembly_counts": {
            "pos_train_total": len(s1["pos_train_texts"]),
            "pos_train_unique_labels": len(set(s1["pos_train_labels"])),
            "pos_train_ood_rows": sum(s1["pos_train_flags"]),
            "bitext_cal_rows": len(s1["bitext_cal_df"]),
            "rej_train_rows": len(s1["rej_train_texts"]),
            "stage1_replay_sha256": _sha256_json_rows(s1["replay_domain_train_df"].to_dict("records")),
        },
        "stage2_d7ddaf2_dataset_hashes_match": d7_hashes_ok,
        "stage2_counts": new_lock["counts"],
        "stage2_boundary_audit_flagged": flagged,
    }


def verify_stage1_archive_before_stage2(stage1_dir: Path) -> None:
    """Verify Stage 1 MAIN archive inventory, calibration, provenance lineage, and reload."""
    if not stage1_dir.is_dir():
        raise FileNotFoundError(f"Stage 1 archive missing: {stage1_dir}")
    inv_path = stage1_dir / "archive_sha_inventory.json"
    prov_path = stage1_dir / "candidate_provenance_manifest.json"
    cal_path = stage1_dir / "calibration_manifest.json"
    for req in (inv_path, prov_path, cal_path, stage1_dir / "model.safetensors"):
        if not req.is_file():
            raise FileNotFoundError(f"Stage 1 archive incomplete, missing {req.name}")

    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    for fname, expected_sha in inv.items():
        fp = stage1_dir / fname
        if not fp.is_file() or _sha256_lower(fp) != str(expected_sha).lower():
            raise RuntimeError(f"Stage 1 archive SHA mismatch for {fname}")

    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    if prov.get("selected_fit") != "fit1_closure_dual_head":
        raise RuntimeError(f"Unexpected Stage 1 selected_fit: {prov.get('selected_fit')}")
    if str(prov.get("base_model", {}).get("weights_sha256", "")).lower() != EXPECTED_SERVING_SHA256:
        raise RuntimeError("Stage 1 base_model.weights_sha256 does not match Serving")

    cal_audit = validate_calibration_manifest(stage1_dir, cal_path)
    if not cal_audit.get("valid"):
        raise RuntimeError(f"Stage 1 calibration_manifest invalid: {cal_audit.get('failure_reasons')}")
    verify_reload_from_archive(stage1_dir)


def main() -> None:
    ap = argparse.ArgumentParser(description="Faithful Fit2 single-fit-per-stage restoration runner")
    ap.add_argument("--dry-run", action="store_true", help="Run fail-closed preflight without training")
    ap.add_argument("--run-stage1-closure-fit1", action="store_true", help="Run ONLY Stage 1 fit1_closure_dual_head (requires budget)")
    ap.add_argument("--run-stage2-boundary-fit2", action="store_true", help="Run ONLY Stage 2 fit2_supcon_energy (requires budget)")
    ap.add_argument("--stage1-run-id", default="faithful-stage1-closure-fit1")
    ap.add_argument("--stage2-run-id", default="faithful-stage2-boundary-fit2")
    ap.add_argument("--stage1-archive-dir", type=Path, default=None)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    dryrun_root = repo_root / "artifacts/evaluation/original_fit2_dryrun_20261113"

    # Fail closed on pre-existing archives/outputs BEFORE preflight or training
    stage1_archive = MAIN_CANDIDATES_DIR / args.stage1_run_id
    stage2_archive = MAIN_CANDIDATES_DIR / args.stage2_run_id
    if args.run_stage1_closure_fit1 and stage1_archive.exists():
        raise FileExistsError(f"Stage 1 archive already exists: {stage1_archive}")
    if args.run_stage2_boundary_fit2 and stage2_archive.exists():
        raise FileExistsError(f"Stage 2 archive already exists: {stage2_archive}")

    preflight = run_preflight_validation(repo_root, dryrun_root)
    if args.dry_run or (not args.run_stage1_closure_fit1 and not args.run_stage2_boundary_fit2):
        print(json.dumps(preflight, indent=2))
        return

    resolved_stage1_dir = args.stage1_archive_dir
    if args.run_stage1_closure_fit1:
        local_root = LOCAL_RESTORE_ROOT / args.stage1_run_id
        local_model = local_root / "candidate_model"
        if local_root.exists():
            raise FileExistsError(f"Local Stage 1 dir already exists: {local_root}")
        s1 = assemble_stage1_closure_data(repo_root, local_root / "datasets", seed=42)
        _train_closure_single_fit(
            fit_name="fit1_closure_dual_head",
            objective_mode="clean_positive_ce",
            base_model_dir=SERVING_DIR,
            output_dir=local_model,
            train_texts=s1["pos_train_texts"],
            train_labels=s1["pos_train_labels"],
            train_is_negative=s1["pos_train_flags"],
            seed=42,
            epochs=3,
        )
        policy_v2 = load_policy_v2(str(repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"))
        s1_temp, s1_rej, s1_cal = _build_closure_rejector_on_train_and_cal(
            fit_name="fit1_closure_dual_head",
            model_dir=local_model,
            feature_spec="cls_l2_plus_logit_geometry_v1",
            c_grid=(0.15, 0.35, 0.75, 1.5),
            rej_train_texts=s1["rej_train_texts"],
            rej_train_y=s1["rej_train_y"],
            cal_pos_df=s1["cal_pos_df"],
            cal_neg_df=s1["cal_neg_df"],
            bitext_cal_df=s1["bitext_cal_df"],
            policy_v2=policy_v2,
        )
        cal_manifest_path = write_calibration_manifest(
            model_dir=local_model,
            model_version=args.stage1_run_id,
            fit_name="fit1_closure_dual_head",
            temperature=s1_temp,
            rejector=s1_rej,
            train_split_sha256=s1["ds_manifest"]["files"]["closure_combined_train"]["sha256"],
            calibration_split_sha256=s1["ds_manifest"]["files"]["closure_combined_calibration"]["sha256"],
        )
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True).strip()
        prov = {
            "provenance_status": "verified",
            "model_version": args.stage1_run_id,
            "selected_fit": "fit1_closure_dual_head",
            "git_commit": git_sha,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "base_model": {
                "name": "distilbert-supportiq",
                "path": str(SERVING_DIR),
                "weights_sha256": EXPECTED_SERVING_SHA256,
            },
            "dataset_hashes": {
                "bitext_cleaned_csv": s1["lineage"].cleaned_sha256,
                "bitext_split_assignments_csv": s1["lineage"].splits_sha256,
                **{k: v["sha256"] for k, v in s1["ds_manifest"]["files"].items()},
            },
            "calibration_summary": s1_cal,
            "calibration_manifest_sha256": _sha256_lower(cal_manifest_path),
            "artifact_hashes": {
                "model.safetensors": _sha256_lower(local_model / "model.safetensors"),
                "tokenizer.json": _sha256_lower(local_model / "tokenizer.json"),
                "config.json": _sha256_lower(local_model / "config.json"),
            },
        }
        (local_model / "candidate_provenance_manifest.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
        arch1 = _archive_to_main(local_model, stage1_archive)
        resolved_stage1_dir = stage1_archive
        print(json.dumps({"stage": 1, "archive": arch1}, indent=2))

    if args.run_stage2_boundary_fit2:
        if resolved_stage1_dir is None:
            raise ValueError("--stage1-archive-dir is required for Stage 2 when Stage 1 is not run in the same invocation")
        verify_stage1_archive_before_stage2(resolved_stage1_dir)
        art_root = repo_root / "artifacts/evaluation/original_fit2_restore" / args.stage2_run_id
        if art_root.exists():
            raise FileExistsError(f"Local Stage 2 dir already exists: {art_root}")
        prepare_and_lock_splits(
            worktree_root=repo_root,
            data_repo_root=Path(r"F:\Năm 3\SD\project\SupportIQ"),
            init_model_dir=resolved_stage1_dir,
            artifact_root=art_root,
        )
        res = run_fit_and_lock_candidate(
            worktree_root=repo_root,
            data_repo_root=Path(r"F:\Năm 3\SD\project\SupportIQ"),
            init_model_dir=resolved_stage1_dir,
            artifact_root=art_root,
            fit_mode="fit2_supcon_energy",
            output_subdir="candidate_model_fit2",
        )
        arch2 = _archive_to_main(art_root / "candidate_model_fit2", stage2_archive)
        print(json.dumps({"stage": 2, "fit_result": res, "archive": arch2}, indent=2))


if __name__ == "__main__":
    main()

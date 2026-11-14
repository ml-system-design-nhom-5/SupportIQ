"""Worker C independent read-only verification for fit2-orig-zero-delta-control-v1.

Strictly reads locked inputs and sealed model archives without mutating any sealed artifact
and without executing any holdout, OOD, full eval, or unseen acceptance inference.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.ml_inference.app import ModelContainer
from pipeline.evaluation.classifier_acceptance_gate import (
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
)
from pipeline.training.orig_fit2_return_contrast_data import (
    EXPECTED_ORIG_STAGE2_LOCKED_FILES,
    ORIG_FIT2_STAGE2_REL,
    compute_effective_train_exposure,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_DENOMINATORS,
    CAL_GUARD_FLOAT_TOLERANCE,
    evaluate_cal_guard_report,
)

OUT_DIR = Path(__file__).resolve().parent

ARCH_CTRL = ROOT / "artifacts/models/candidates/fit2-orig-zero-delta-control-v1"
REC_CTRL = ROOT / "artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1"
PREP_CTRL = ROOT / "artifacts/models/candidates/run-records-fit2-orig-zero-delta-control-v1-prep"
STAGE2_ORIG = ROOT / ORIG_FIT2_STAGE2_REL

ARCH_ORIG = ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
ARCH_2E5 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
ARCH_LR5E6 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1"
PREP_V4 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep"
SERVING_DIR = ROOT / "artifacts/models/trained/distilbert-supportiq"
FIT1_DIR = ROOT / "artifacts/models/candidates/reconstructed-closure-fit1-20261113"

EXPECTED_HASHES = {
    "ctrl_archive_inv": "ab01eb821e47923018adfbb6269ecdef1201ef21a1c58b6b7638cdabd8e3f337",
    "ctrl_weights": "904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee",
    "ctrl_cal": "70e86f044d3f2f496bc5682e472a35e64d60ab4b51a2e6ade2757b75140c2c5e",
    "ctrl_sidecar_inv": "df5e33b608516763bfd29cfe8a13c316b832170c3b7b0ba49aa9f4d9c1e6b5f1",
    "ctrl_cal_guard": "4224d16e6f7d3dde6f2c87b64ea61e89d4c1ef6afb1efb6ee8691eb3d2f3e4c3",
    "ctrl_prep_manifest": "5ad2f3eb888979e6cd913850aa423c77cae1cc60b345b3326ee17fa0c7aa3b92",
    "orig_weights": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "prior_2e5_weights": "dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d",
    "lr5e6_weights": "b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2",
    "serving_weights": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "fit1_weights": "95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def norm_text(text: str) -> str:
    return " ".join(str(text).strip().lower().split())


def verify_inventory(base: Path, inv_path: Path) -> Tuple[int, List[str], Dict[str, str]]:
    payload = json.loads(inv_path.read_text(encoding="utf-8"))
    files = payload.get("files", payload)
    mismatches: List[str] = []
    actuals: Dict[str, str] = {}
    for rel, meta in files.items():
        fp = base / rel
        exp = (meta["sha256"] if isinstance(meta, dict) else str(meta)).lower()
        act = sha256_file(fp) if fp.is_file() else "MISSING"
        actuals[rel] = act
        if act != exp:
            mismatches.append(f"{rel}: {act} != {exp}")
    return len(files), mismatches, actuals


def pure_softmax_float64(logits: np.ndarray, temperature: float) -> np.ndarray:
    if not math.isfinite(temperature) or temperature <= 0.0:
        raise ValueError(f"Invalid temperature: {temperature}")
    scaled = np.asarray(logits, dtype=np.float64) / float(temperature)
    shifted = scaled - np.max(scaled, axis=1, keepdims=True)
    exps = np.exp(shifted)
    return exps / np.sum(exps, axis=1, keepdims=True)


def forward_logits(
    model_dir: Path,
    texts: Sequence[str],
    *,
    device_str: str,
    max_length: int = 64,
    batch_size: int = 128,
) -> np.ndarray:
    device = torch.device(device_str)
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True)
    model.to(device)
    model.eval()
    id2label = {int(k): v for k, v in (model.config.id2label or {}).items()}
    if [id2label.get(i) for i in range(46)] != list(STANDARD_INTENTS_46):
        raise ValueError(f"Model id2label mismatch in {model_dir}")
    chunks: List[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            enc = tokenizer(
                list(texts[i : i + batch_size]),
                max_length=max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            enc = {k: v.to(device) for k, v in enc.items()}
            logits = model(**enc).logits.detach().cpu().numpy().astype(np.float64)
            chunks.append(logits)
    return np.vstack(chunks)


def summarize_positive_with_breakdown(
    probs: np.ndarray,
    rows: Sequence[Dict[str, Any]],
    *,
    idx_by_label: Dict[str, int],
    sup12_indices: np.ndarray,
    sup12_set: set[str],
) -> Tuple[Dict[str, Any], Dict[str, Any], np.ndarray, np.ndarray]:
    y_true = np.array([idx_by_label[str(r["intent"])] for r in rows], dtype=np.int64)
    preds = np.argmax(probs, axis=1)
    max_probs = np.max(probs, axis=1)
    true_probs = probs[np.arange(len(rows)), y_true]
    sup12_mass = np.sum(probs[:, sup12_indices], axis=1)
    corr_mask = preds == y_true
    wrong_mask = ~corr_mask
    pred_sup12_count = int(sum(STANDARD_INTENTS_46[int(p)] in sup12_set for p in preds))

    summary = {
        "count": len(rows),
        "correct_count": int(np.sum(corr_mask)),
        "incorrect_count": int(np.sum(wrong_mask)),
        "accuracy": float(np.mean(corr_mask)),
        "mean_max_prob": float(np.mean(max_probs)),
        "conf_ge_070_count": int(np.sum(max_probs >= 0.70)),
        "conf_ge_080_count": int(np.sum(max_probs >= 0.80)),
        "max_sup12_mass": float(np.max(sup12_mass)),
        "mean_sup12_mass": float(np.mean(sup12_mass)),
        "pred_sup12_count": pred_sup12_count,
    }
    breakdown = {
        "count": len(rows),
        "correct_count": int(np.sum(corr_mask)),
        "incorrect_count": int(np.sum(wrong_mask)),
        "all_mean_max_prob": float(np.mean(max_probs)),
        "correct_mean_max_prob": float(np.mean(max_probs[corr_mask])) if np.any(corr_mask) else None,
        "incorrect_mean_max_prob": float(np.mean(max_probs[wrong_mask])) if np.any(wrong_mask) else None,
        "mean_true_class_prob": float(np.mean(true_probs)),
        "mean_sup12_mass": float(np.mean(sup12_mass)),
        "max_sup12_mass": float(np.max(sup12_mass)),
        "pred_sup12_count": pred_sup12_count,
    }
    return summary, breakdown, preds, max_probs


def evaluate_model_surfaces(
    model_dir: Path,
    surfaces: Dict[str, List[Dict[str, Any]]],
    *,
    device_str: str,
    check_mc_parity: bool = False,
) -> Dict[str, Any]:
    cal_manifest = json.loads((model_dir / "calibration_manifest.json").read_text(encoding="utf-8"))
    temp = float(cal_manifest["calibration"]["temperature"])
    min_temp = float(cal_manifest["calibration"]["min_temperature"])
    if abs(temp - 1.0) > 1e-12 or abs(min_temp - 1.0) > 1e-12:
        raise ValueError(f"Expected T=1.0, min_T=1.0 in {model_dir}; got T={temp}, min_T={min_temp}")
    max_len = int(cal_manifest["tokenization"]["max_length"])
    idx_by_label = {lbl: i for i, lbl in enumerate(STANDARD_INTENTS_46)}
    sup12_indices = np.array([idx_by_label[l] for l in SUPPORTED_12_INTENTS], dtype=np.int64)
    sup12_set = set(SUPPORTED_12_INTENTS)
    esc34_set = set(ESCALATED_34_INTENTS)

    probs_by_surface: Dict[str, np.ndarray] = {}
    for name, rows in surfaces.items():
        logits = forward_logits(
            model_dir,
            [str(r["text"]) for r in rows],
            device_str=device_str,
            max_length=max_len,
        )
        probs_by_surface[name] = pure_softmax_float64(logits, temp)

    pos_cal_rows = surfaces["boundary_pos_cal"]
    pos_cal_probs = probs_by_surface["boundary_pos_cal"]
    cal_sup12_mask = np.array([r["intent"] in sup12_set for r in pos_cal_rows], dtype=bool)
    cal_esc34_mask = np.array([r["intent"] in esc34_set for r in pos_cal_rows], dtype=bool)
    if int(np.sum(cal_sup12_mask)) != 48 or int(np.sum(cal_esc34_mask)) != 38:
        raise ValueError("Unexpected boundary_pos_cal split counts")

    pos_train_rows = surfaces["boundary_pos_train"]
    pos_train_probs = probs_by_surface["boundary_pos_train"]
    trn_sup12_mask = np.array([r["intent"] in sup12_set for r in pos_train_rows], dtype=bool)
    trn_esc34_mask = np.array([r["intent"] in esc34_set for r in pos_train_rows], dtype=bool)
    if int(np.sum(trn_sup12_mask)) != 133 or int(np.sum(trn_esc34_mask)) != 48:
        raise ValueError("Unexpected boundary_pos_train split counts")

    pos_sum, pos_bd, pos_preds, pos_confs = summarize_positive_with_breakdown(
        pos_cal_probs, pos_cal_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set
    )
    sup_sum, sup_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_sup12_mask],
        [r for r, f in zip(pos_cal_rows, cal_sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )
    esc_sum, esc_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_esc34_mask],
        [r for r, f in zip(pos_cal_rows, cal_esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )
    bit_sum, bit_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["bitext_cal"],
        surfaces["bitext_cal"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )
    add18_sum, add18_bd, add18_preds, add18_confs = summarize_positive_with_breakdown(
        probs_by_surface["pos_train_added_18"],
        surfaces["pos_train_added_18"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )
    trn_pos_sum, trn_pos_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs, pos_train_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set
    )
    trn_sup_sum, trn_sup_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs[trn_sup12_mask],
        [r for r, f in zip(pos_train_rows, trn_sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )
    trn_esc_sum, trn_esc_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs[trn_esc34_mask],
        [r for r, f in zip(pos_train_rows, trn_esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
    )

    neg_cal_probs = probs_by_surface["boundary_neg_cal"]
    neg_cal_preds = np.argmax(neg_cal_probs, axis=1)
    neg_cal_sup12_probs = neg_cal_probs[:, sup12_indices]
    neg_cal_sup12_mass = np.sum(neg_cal_sup12_probs, axis=1)
    neg_cal_max_single = np.max(neg_cal_sup12_probs, axis=1)
    neg_cal_pred_sup12_mask = np.array([STANDARD_INTENTS_46[int(p)] in sup12_set for p in neg_cal_preds], dtype=bool)

    neg_trn_probs = probs_by_surface["boundary_neg_train"]
    neg_trn_preds = np.argmax(neg_trn_probs, axis=1)
    neg_trn_sup12_probs = neg_trn_probs[:, sup12_indices]
    neg_trn_sup12_mass = np.sum(neg_trn_sup12_probs, axis=1)
    neg_trn_max_single = np.max(neg_trn_sup12_probs, axis=1)
    neg_trn_pred_sup12_mask = np.array([STANDARD_INTENTS_46[int(p)] in sup12_set for p in neg_trn_preds], dtype=bool)

    cal_guard_metrics = {
        "temperature": temp,
        "boundary_pos_cal": {k: pos_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "boundary_pos_cal_sup12": {
            k: sup_sum[k]
            for k in (
                "count",
                "correct_count",
                "accuracy",
                "mean_max_prob",
                "conf_ge_070_count",
                "conf_ge_080_count",
            )
        },
        "boundary_pos_cal_esc34": {
            k: esc_sum[k]
            for k in ("count", "correct_count", "accuracy", "mean_max_prob", "max_sup12_mass")
        },
        "bitext_cal": {k: bit_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "boundary_neg_cal": {
            "count": len(surfaces["boundary_neg_cal"]),
            "pred_sup12_count": int(np.sum(neg_cal_pred_sup12_mask)),
            "max_sup12_mass": float(np.max(neg_cal_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_cal_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_cal_sup12_probs)),
        },
        "attribution_breakdown": {
            "boundary_pos_cal": pos_bd,
            "boundary_pos_cal_sup12": sup_bd,
            "boundary_pos_cal_esc34": esc_bd,
            "bitext_cal": bit_bd,
        },
    }

    train_metrics = {
        "boundary_pos_train": trn_pos_bd,
        "boundary_pos_train_sup12": trn_sup_bd,
        "boundary_pos_train_esc34": trn_esc_bd,
        "boundary_neg_train": {
            "count": len(surfaces["boundary_neg_train"]),
            "pred_sup12_count": int(np.sum(neg_trn_pred_sup12_mask)),
            "max_sup12_mass": float(np.max(neg_trn_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_trn_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_trn_sup12_probs)),
        },
        "pos_train_added_18_unseen_or_delta": add18_bd,
    }

    mc_parity = None
    if check_mc_parity:
        mc = ModelContainer()
        mc.load(model_dir, calibration_manifest_path=model_dir / "calibration_manifest.json")
        max_diff = 0.0
        intent_mismatches = 0
        for r, pr in zip(pos_cal_rows, pos_cal_probs):
            out = mc.predict(str(r["text"]))
            if out["intent"] != STANDARD_INTENTS_46[int(np.argmax(pr))]:
                intent_mismatches += 1
            max_diff = max(max_diff, abs(float(out["confidence"]) - float(np.max(pr))))
        for r, pr in zip(surfaces["boundary_neg_cal"], neg_cal_probs):
            out = mc.predict(str(r["text"]))
            if out["intent"] != STANDARD_INTENTS_46[int(np.argmax(pr))]:
                intent_mismatches += 1
            max_diff = max(max_diff, abs(float(out["confidence"]) - float(np.max(pr))))
        mc_parity = {
            "checked_rows": len(pos_cal_rows) + len(surfaces["boundary_neg_cal"]),
            "intent_mismatches": intent_mismatches,
            "max_confidence_abs_diff": max_diff,
        }

    row_preds = {
        "boundary_pos_cal": [
            {
                "sample_id": r.get("sample_id"),
                "gold": r["intent"],
                "is_sup12": r["intent"] in sup12_set,
                "pred": STANDARD_INTENTS_46[int(p)],
                "correct": bool(STANDARD_INTENTS_46[int(p)] == r["intent"]),
                "conf": float(c),
                "sup12_mass": float(np.sum(pr[sup12_indices])),
                "text": r["text"],
            }
            for r, p, c, pr in zip(pos_cal_rows, pos_preds, pos_confs, pos_cal_probs)
        ],
        "boundary_neg_cal": [
            {
                "sample_id": r.get("sample_id"),
                "pred": STANDARD_INTENTS_46[int(p)],
                "pred_is_sup12": bool(STANDARD_INTENTS_46[int(p)] in sup12_set),
                "max_prob": float(np.max(pr)),
                "sup12_mass": float(sm),
                "max_single_sup12_prob": float(ms),
                "text": r["text"],
            }
            for r, p, pr, sm, ms in zip(
                surfaces["boundary_neg_cal"],
                neg_cal_preds,
                neg_cal_probs,
                neg_cal_sup12_mass,
                neg_cal_max_single,
            )
        ],
    }

    return {
        "weights_sha256": sha256_file(model_dir / "model.safetensors"),
        "calibration_manifest_sha256": sha256_file(model_dir / "calibration_manifest.json"),
        "rejector_enabled": bool(cal_manifest["selective_rejector"]["enabled"]),
        "cal_guard_metrics": cal_guard_metrics,
        "train_metrics": train_metrics,
        "mc_parity": mc_parity,
        "row_preds": row_preds,
    }


def main() -> None:
    t0 = time.perf_counter()

    # 1. Sealed archive, sidecar, prep, and untouched checkpoint hash verification
    actual_top = {
        "ctrl_archive_inv": sha256_file(ARCH_CTRL / "archive_sha_inventory.json"),
        "ctrl_weights": sha256_file(ARCH_CTRL / "model.safetensors"),
        "ctrl_cal": sha256_file(ARCH_CTRL / "calibration_manifest.json"),
        "ctrl_sidecar_inv": sha256_file(REC_CTRL / "sidecar_sha_inventory.json"),
        "ctrl_cal_guard": sha256_file(REC_CTRL / "cal_guard_report.json"),
        "ctrl_prep_manifest": sha256_file(PREP_CTRL / "prep_manifest.json"),
        "orig_weights": sha256_file(ARCH_ORIG / "model.safetensors"),
        "prior_2e5_weights": sha256_file(ARCH_2E5 / "model.safetensors"),
        "lr5e6_weights": sha256_file(ARCH_LR5E6 / "model.safetensors"),
        "serving_weights": sha256_file(SERVING_DIR / "model.safetensors"),
        "fit1_weights": sha256_file(FIT1_DIR / "model.safetensors"),
    }
    hash_mismatches = {
        k: {"actual": v, "expected": EXPECTED_HASHES[k]}
        for k, v in actual_top.items()
        if v != EXPECTED_HASHES[k]
    }
    if hash_mismatches:
        raise RuntimeError(f"Top-level SHA mismatch: {hash_mismatches}")

    arch_n, arch_mis, _ = verify_inventory(ARCH_CTRL, ARCH_CTRL / "archive_sha_inventory.json")
    side_n, side_mis, _ = verify_inventory(REC_CTRL, REC_CTRL / "sidecar_sha_inventory.json")
    if arch_mis or side_mis:
        raise RuntimeError(f"Inventory mismatches: arch={arch_mis}, side={side_mis}")

    # 2. Verify 13 bit-identical stage2_inputs vs control prep datasets/ + zero added rows
    ctrl_ds = PREP_CTRL / "datasets"
    if (ctrl_ds / "orig_fit2_return_contrast_extension.jsonl").exists():
        raise RuntimeError("Extension file unexpectedly exists in zero-delta control prep")
    stage2_file_comparison: Dict[str, Any] = {}
    bit_identical_count = 0
    for fname in EXPECTED_ORIG_STAGE2_LOCKED_FILES:
        h_ctrl = sha256_file(ctrl_ds / fname)
        h_orig = sha256_file(STAGE2_ORIG / fname)
        same = h_ctrl == h_orig
        if same:
            bit_identical_count += 1
        stage2_file_comparison[fname] = {"ctrl": h_ctrl, "orig_stage2": h_orig, "bit_identical": same}
    if bit_identical_count != 13:
        raise RuntimeError(f"Expected 13/13 bit-identical stage2 files, got {bit_identical_count}")

    # Verify sidecar run_config, prep_manifest, status, fit_result, and source_snapshot vs disk
    run_cfg = json.loads((REC_CTRL / "run_config.json").read_text(encoding="utf-8"))
    prep_man = json.loads((PREP_CTRL / "prep_manifest.json").read_text(encoding="utf-8"))
    status_json = json.loads((REC_CTRL / "status.json").read_text(encoding="utf-8"))
    fit_res = json.loads((REC_CTRL / "fit_result.json").read_text(encoding="utf-8"))
    recorded_cal_guard = json.loads((REC_CTRL / "cal_guard_report.json").read_text(encoding="utf-8"))

    assert run_cfg["authorized_fit_profile"] == "option_a"
    assert abs(float(run_cfg["lr"]) - 2e-5) < 1e-12
    assert int(run_cfg["epochs"]) == 3 and int(run_cfg["batch_size"]) == 32 and int(run_cfg["seed"]) == 42
    assert float(run_cfg["min_temperature"]) == 1.0 and run_cfg["enable_selective_rejector"] is False
    assert AUTHORIZED_FIT_PROFILES["option_a"]["lr"] == 2e-5
    assert prep_man["is_promotion_candidate"] is False
    assert recorded_cal_guard["is_promotion_candidate"] is False
    assert status_json["cal_guard_passed"] is False
    assert status_json["cal_guard_status"] == "CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED"

    snap_dir = REC_CTRL / "source_snapshot"
    snapshot_vs_run_cfg_mismatches: List[str] = []
    snapshot_vs_disk_diffs: List[str] = []
    for rel, rec_sha in run_cfg["source_hashes"].items():
        snap_sha = sha256_file(snap_dir / rel)
        if snap_sha != rec_sha.lower():
            snapshot_vs_run_cfg_mismatches.append(rel)
        disk_sha = sha256_file(ROOT / rel)
        if disk_sha != snap_sha:
            snapshot_vs_disk_diffs.append(rel)
    if snapshot_vs_run_cfg_mismatches:
        raise RuntimeError(f"source_snapshot mismatch vs run_config: {snapshot_vs_run_cfg_mismatches}")

    # 3. Verify exposure counts (11,320 rows / 13,000 effective / 0 added) & 3 historical overlaps
    pos_train = read_jsonl(ctrl_ds / "boundary_pos_train.jsonl")
    neg_train = read_jsonl(ctrl_ds / "boundary_neg_train.jsonl")
    bitext_clean = read_jsonl(ctrl_ds / "bitext_train_clean.jsonl")
    bitext_noisy = read_jsonl(ctrl_ds / "bitext_train_noisy.jsonl")
    pos_cal = read_jsonl(ctrl_ds / "boundary_pos_calibration.jsonl")
    neg_cal = read_jsonl(ctrl_ds / "boundary_neg_calibration.jsonl")
    pos_eval = read_jsonl(ctrl_ds / "boundary_pos_evaluation.jsonl")
    neg_eval = read_jsonl(ctrl_ds / "boundary_neg_evaluation.jsonl")
    bitext_cal = read_jsonl(ctrl_ds / "bitext_cal.jsonl")
    bitext_test = read_jsonl(ctrl_ds / "bitext_test_6690.jsonl")
    full_train = read_jsonl(ctrl_ds / "full_train_split.jsonl")
    full_cal = read_jsonl(ctrl_ds / "full_cal_split.jsonl")
    added_18 = read_jsonl(PREP_V4 / "datasets/orig_fit2_return_contrast_extension.jsonl")

    exposure = compute_effective_train_exposure(
        pos_train=pos_train,
        bitext_clean=bitext_clean,
        bitext_noisy=bitext_noisy,
        neg_train=neg_train,
    )
    assert len(full_train) == 11320
    assert int(exposure["effective_train_total"]) == 13000
    assert len(pos_train) == 181 and len(neg_train) == 99
    assert len(pos_cal) == 86 and len(neg_cal) == 48 and len(bitext_cal) == 690
    assert len(added_18) == 18
    assert not any(str(r.get("sample_id", "")).startswith("orig_ret_ch_") for r in pos_train + full_train)

    noisy_norm = {norm_text(r["text"]) for r in bitext_noisy}
    clean_norm = {norm_text(r["text"]) for r in bitext_clean}
    cal_norm = {norm_text(r["text"]) for r in full_cal}
    eval_norm = {norm_text(r["text"]) for r in pos_eval + neg_eval + bitext_test}
    overlap_audit = {
        "noisy_vs_cal": len(noisy_norm & cal_norm),
        "noisy_vs_eval_total": len(noisy_norm & eval_norm),
        "noisy_vs_bitext_test": len(noisy_norm & {norm_text(r["text"]) for r in bitext_test}),
        "clean_vs_cal": len(clean_norm & cal_norm),
        "clean_vs_eval_total": len(clean_norm & eval_norm),
    }

    # 4. Evaluate all 4 models on CAL & canonical TRAIN + 18-row delta slice (read-only)
    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    surfaces = {
        "boundary_pos_cal": pos_cal,
        "boundary_neg_cal": neg_cal,
        "bitext_cal": bitext_cal,
        "boundary_pos_train": pos_train,
        "boundary_neg_train": neg_train,
        "pos_train_added_18": added_18,
    }
    eval_orig = evaluate_model_surfaces(ARCH_ORIG, surfaces, device_str=device_str, check_mc_parity=False)
    eval_ctrl = evaluate_model_surfaces(ARCH_CTRL, surfaces, device_str=device_str, check_mc_parity=True)
    eval_2e5 = evaluate_model_surfaces(ARCH_2E5, surfaces, device_str=device_str, check_mc_parity=False)
    eval_lr5e6 = evaluate_model_surfaces(ARCH_LR5E6, surfaces, device_str=device_str, check_mc_parity=False)

    # 5. Recompute 11-check control CAL guard independently and compare vs recorded report
    recomputed_guard = evaluate_cal_guard_report(
        eval_ctrl["cal_guard_metrics"],
        eval_orig["cal_guard_metrics"],
        float_tolerance=CAL_GUARD_FLOAT_TOLERANCE,
        cal_guard_mode="control",
    )
    assert recomputed_guard["cal_guard_mode"] == "matched_zero_delta_control_11_checks"
    assert len(recomputed_guard["checks"]) == 11
    assert recomputed_guard["passed"] is False
    assert recomputed_guard["recommended_status"] == "CONTROL_CAL_DRIFT_OR_REGRESSION_DETECTED"
    assert recomputed_guard["failed_checks"] == recorded_cal_guard["failed_checks"]

    max_guard_float_diff = 0.0
    for rc, ac in zip(recomputed_guard["checks"], recorded_cal_guard["checks"]):
        assert rc["name"] == ac["name"] and rc["passed"] == ac["passed"]
        if rc["kind"] == "integer":
            assert rc["actual"] == ac["actual"]
        else:
            diff = abs(float(rc["actual"]) - float(ac["actual"]))
            max_guard_float_diff = max(max_guard_float_diff, diff)
            assert diff <= CAL_GUARD_FLOAT_TOLERANCE, f"{rc['name']} diff {diff}"
            if "limit" in ac:
                lim_diff = abs(float(rc["limit"]) - float(ac["limit"]))
                max_guard_float_diff = max(max_guard_float_diff, lim_diff)
                assert lim_diff <= CAL_GUARD_FLOAT_TOLERANCE

    # 6. Row-level flip analysis vs Original Fit2
    def flip_summary(other_rows: Sequence[Dict[str, Any]], orig_rows: Sequence[Dict[str, Any]], is_pos: bool) -> Dict[str, Any]:
        if is_pos:
            gained = [o["sample_id"] for b, o in zip(orig_rows, other_rows) if (not b["correct"]) and o["correct"]]
            lost = [o["sample_id"] for b, o in zip(orig_rows, other_rows) if b["correct"] and (not o["correct"])]
            return {"gained": gained, "lost": lost, "net": len(gained) - len(lost)}
        entered = [o["sample_id"] for b, o in zip(orig_rows, other_rows) if (not b["pred_is_sup12"]) and o["pred_is_sup12"]]
        exited = [o["sample_id"] for b, o in zip(orig_rows, other_rows) if b["pred_is_sup12"] and (not o["pred_is_sup12"])]
        return {"entered_sup12": entered, "exited_sup12": exited, "net": len(entered) - len(exited)}

    flips = {
        "zero_delta_control": {
            "pos_cal": flip_summary(eval_ctrl["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
            "neg_cal": flip_summary(eval_ctrl["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
        },
        "prior_2e5": {
            "pos_cal": flip_summary(eval_2e5["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
            "neg_cal": flip_summary(eval_2e5["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
        },
        "cand_lr5e6": {
            "pos_cal": flip_summary(eval_lr5e6["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
            "neg_cal": flip_summary(eval_lr5e6["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
        },
    }

    git_branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    git_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

    comparison = {
        "schema_version": "worker_c_zero_delta_control_review.v1",
        "device_used": device_str,
        "git_branch": git_branch,
        "git_head": git_head,
        "top_level_hashes": actual_top,
        "inventories_verified": {
            "archive_files_checked": arch_n,
            "archive_mismatches": arch_mis,
            "sidecar_files_checked": side_n,
            "sidecar_mismatches": side_mis,
        },
        "stage2_bit_identical_count": bit_identical_count,
        "source_snapshot_vs_disk_diffs": snapshot_vs_disk_diffs,
        "exposure": exposure,
        "overlap_audit": overlap_audit,
        "fit_metadata": {
            "train_seconds": fit_res["train_seconds"],
            "epoch_stats": fit_res["epoch_stats"],
            "batches_per_epoch_control": math.ceil(13000 / 32),
            "total_steps_control": math.ceil(13000 / 32) * 3,
            "batches_per_epoch_delta18": math.ceil(13080 / 32),
            "total_steps_delta18": math.ceil(13080 / 32) * 3,
        },
        "mc_parity_control": eval_ctrl["mc_parity"],
        "max_guard_float_diff_vs_recorded": max_guard_float_diff,
        "recomputed_control_cal_guard": recomputed_guard,
        "models": {
            name: {
                "weights_sha256": obj["weights_sha256"],
                "calibration_manifest_sha256": obj["calibration_manifest_sha256"],
                "rejector_enabled": obj["rejector_enabled"],
                "cal_guard_metrics": obj["cal_guard_metrics"],
                "train_metrics": obj["train_metrics"],
            }
            for name, obj in [
                ("orig_fit2", eval_orig),
                ("zero_delta_control", eval_ctrl),
                ("prior_2e5", eval_2e5),
                ("cand_lr5e6", eval_lr5e6),
            ]
        },
        "flips_vs_orig_fit2": flips,
    }
    comp_path = OUT_DIR / "control_cal_comparison.json"
    comp_path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "worker_c_review_manifest.v1",
        "task_id": "task_b49f9106865f",
        "dispatch_id": "ctx_2b47de192bb5",
        "git_branch": git_branch,
        "git_head": git_head,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "outputs": {
            "control_cal_comparison.json": sha256_file(comp_path),
            "verify_control_cal.py": sha256_file(Path(__file__)),
        },
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "device": device_str, "max_guard_diff": max_guard_float_diff, "mc_parity": eval_ctrl["mc_parity"]}, indent=2))


if __name__ == "__main__":
    main()

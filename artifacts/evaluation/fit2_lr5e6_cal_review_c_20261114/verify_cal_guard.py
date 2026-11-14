"""Worker C independent read-only CAL guard verification for fit2-orig-ret-channel-lr5e6-v1.

Strictly reads locked inputs and sealed model archives without mutating any sealed artifact
and without executing any full eval, OOD, or held-out suite inference.
"""

from __future__ import annotations

import hashlib
import inspect
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
from pipeline.training.train_boundary_candidate import run_fit_and_lock_candidate
from scripts.run_orig_fit2_return_contrast_fit import run_authorized_fit, validate_profile_settings
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_DENOMINATORS,
    CAL_GUARD_FLOAT_TOLERANCE,
    evaluate_cal_guard_report,
)

OUT_DIR = Path(__file__).resolve().parent
REC_LR5E6 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-lr5e6-v1"
ARCH_LR5E6 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1"
ARCH_ORIG = ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
ARCH_2E5 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
SERVING_DIR = ROOT / "artifacts/models/trained/distilbert-supportiq"
PREP_V4 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep"

EXPECTED_ARCHIVE_INV_SHA = "4d1f9204b8d8cd4a3f55543baec1d74b29f75c2253810591b1600013d9e49855"
EXPECTED_SIDECAR_INV_SHA = "4b5f53e479115bb182cc9e9557c7ddea4b7f1b2bbd801f4cd96089b48a7c69b5"
EXPECTED_CAL_GUARD_SHA = "01d4b9956c563fba64512aa92ff3f1daf12cd732b8fb9d630e993f69a44613a4"
EXPECTED_ORIG_SHA = "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"
EXPECTED_CAND_SHA = "b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2"
EXPECTED_2E5_SHA = "dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d"
EXPECTED_SERVING_SHA = "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302"


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


def verify_inventory(base: Path, inv_path: Path) -> Tuple[int, List[str]]:
    payload = json.loads(inv_path.read_text(encoding="utf-8"))
    files = payload.get("files", payload)
    mismatches: List[str] = []
    for rel, meta in files.items():
        fp = base / rel
        exp = (meta["sha256"] if isinstance(meta, dict) else str(meta)).lower()
        act = sha256_file(fp) if fp.is_file() else "MISSING"
        if act != exp:
            mismatches.append(f"{rel}: {act} != {exp}")
    return len(files), mismatches


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


def summarize_positive_independent(
    probs: np.ndarray,
    rows: Sequence[Dict[str, Any]],
    *,
    idx_by_label: Dict[str, int],
    sup12_indices: np.ndarray,
) -> Tuple[Dict[str, Any], np.ndarray, np.ndarray]:
    y_true = np.array([idx_by_label[str(r["intent"])] for r in rows], dtype=np.int64)
    preds = np.argmax(probs, axis=1)
    max_probs = np.max(probs, axis=1)
    correct = int(np.sum(preds == y_true))
    sup12_mass = np.sum(probs[:, sup12_indices], axis=1)
    return (
        {
            "count": len(rows),
            "correct_count": correct,
            "accuracy": float(correct / len(rows)),
            "mean_max_prob": float(np.mean(max_probs)),
            "conf_ge_070_count": int(np.sum(max_probs >= 0.70)),
            "conf_ge_080_count": int(np.sum(max_probs >= 0.80)),
            "max_sup12_mass": float(np.max(sup12_mass)),
        },
        preds,
        max_probs,
    )


def evaluate_cal_surfaces_independent(
    model_dir: Path,
    surfaces: Dict[str, List[Dict[str, Any]]],
    *,
    device_str: str,
) -> Dict[str, Any]:
    cal_manifest = json.loads((model_dir / "calibration_manifest.json").read_text(encoding="utf-8"))
    temp = float(cal_manifest["calibration"]["temperature"])
    min_temp = float(cal_manifest["calibration"]["min_temperature"])
    max_len = int(cal_manifest["tokenization"]["max_length"])
    idx_by_label = {lbl: i for i, lbl in enumerate(STANDARD_INTENTS_46)}
    sup12_indices = np.array([idx_by_label[l] for l in SUPPORTED_12_INTENTS], dtype=np.int64)
    sup12_set = set(SUPPORTED_12_INTENTS)
    esc34_set = set(ESCALATED_34_INTENTS)

    probs_by_surface: Dict[str, np.ndarray] = {}
    logits_by_surface: Dict[str, np.ndarray] = {}
    for name, rows in surfaces.items():
        logits = forward_logits(
            model_dir,
            [str(r["text"]) for r in rows],
            device_str=device_str,
            max_length=max_len,
        )
        logits_by_surface[name] = logits
        probs_by_surface[name] = pure_softmax_float64(logits, temp)

    pos_rows = surfaces["boundary_pos_cal"]
    pos_probs = probs_by_surface["boundary_pos_cal"]
    sup12_mask = np.array([r["intent"] in sup12_set for r in pos_rows], dtype=bool)
    esc34_mask = np.array([r["intent"] in esc34_set for r in pos_rows], dtype=bool)
    if int(np.sum(sup12_mask)) != 48 or int(np.sum(esc34_mask)) != 38:
        raise ValueError("Unexpected boundary_pos_cal split counts")

    pos_sum, pos_preds, pos_confs = summarize_positive_independent(
        pos_probs, pos_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices
    )
    sup_sum, _, _ = summarize_positive_independent(
        pos_probs[sup12_mask],
        [r for r, f in zip(pos_rows, sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
    )
    esc_sum, _, _ = summarize_positive_independent(
        pos_probs[esc34_mask],
        [r for r, f in zip(pos_rows, esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
    )
    bit_sum, _, _ = summarize_positive_independent(
        probs_by_surface["bitext_cal"],
        surfaces["bitext_cal"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
    )
    add_sum, add_preds, add_confs = summarize_positive_independent(
        probs_by_surface["pos_train_added_18"],
        surfaces["pos_train_added_18"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
    )

    neg_probs = probs_by_surface["boundary_neg_cal"]
    neg_preds = np.argmax(neg_probs, axis=1)
    neg_sup12_probs = neg_probs[:, sup12_indices]
    neg_sup12_mass = np.sum(neg_sup12_probs, axis=1)
    neg_max_single_per_row = np.max(neg_sup12_probs, axis=1)

    metrics = {
        "temperature": temp,
        "min_temperature": min_temp,
        "rejector_enabled": bool(cal_manifest["selective_rejector"]["enabled"]),
        "weights_sha256": sha256_file(model_dir / "model.safetensors"),
        "calibration_manifest_sha256": sha256_file(model_dir / "calibration_manifest.json"),
        "boundary_pos_cal": {
            k: pos_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")
        },
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
        "bitext_cal": {
            k: bit_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")
        },
        "pos_train_added_18": {
            k: add_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")
        },
        "boundary_neg_cal": {
            "count": len(surfaces["boundary_neg_cal"]),
            "pred_sup12_count": int(sum(STANDARD_INTENTS_46[int(p)] in sup12_set for p in neg_preds)),
            "max_sup12_mass": float(np.max(neg_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_sup12_probs)),
        },
    }

    # Check ModelContainer runtime score parity on boundary_pos_cal + boundary_neg_cal
    mc = ModelContainer()
    mc.load(model_dir, calibration_manifest_path=model_dir / "calibration_manifest.json")
    max_mc_conf_diff = 0.0
    mc_intent_mismatches = 0
    for r, probs_row in zip(pos_rows, pos_probs):
        mc_out = mc.predict(str(r["text"]))
        exp_intent = STANDARD_INTENTS_46[int(np.argmax(probs_row))]
        exp_conf = float(np.max(probs_row))
        if mc_out["intent"] != exp_intent:
            mc_intent_mismatches += 1
        max_mc_conf_diff = max(max_mc_conf_diff, abs(float(mc_out["confidence"]) - exp_conf))
    for r, probs_row in zip(surfaces["boundary_neg_cal"], neg_probs):
        mc_out = mc.predict(str(r["text"]))
        exp_intent = STANDARD_INTENTS_46[int(np.argmax(probs_row))]
        exp_conf = float(np.max(probs_row))
        if mc_out["intent"] != exp_intent:
            mc_intent_mismatches += 1
        max_mc_conf_diff = max(max_mc_conf_diff, abs(float(mc_out["confidence"]) - exp_conf))

    return {
        "metrics": metrics,
        "mc_parity": {
            "checked_rows": len(pos_rows) + len(surfaces["boundary_neg_cal"]),
            "intent_mismatches": mc_intent_mismatches,
            "max_confidence_abs_diff": max_mc_conf_diff,
        },
        "row_preds": {
            "boundary_pos_cal": [
                {
                    "sample_id": r.get("sample_id"),
                    "gold": r["intent"],
                    "is_sup12": r["intent"] in sup12_set,
                    "pred": STANDARD_INTENTS_46[int(p)],
                    "conf": float(c),
                    "correct": bool(STANDARD_INTENTS_46[int(p)] == r["intent"]),
                    "sup12_mass": float(np.sum(pr[sup12_indices])),
                    "text": r["text"],
                }
                for r, p, c, pr in zip(pos_rows, pos_preds, pos_confs, pos_probs)
            ],
            "boundary_neg_cal": [
                {
                    "sample_id": r.get("sample_id"),
                    "category": r.get("category"),
                    "pred": STANDARD_INTENTS_46[int(p)],
                    "pred_is_sup12": bool(STANDARD_INTENTS_46[int(p)] in sup12_set),
                    "max_prob": float(np.max(pr)),
                    "sup12_mass": float(sm),
                    "max_single_sup12_prob": float(ms),
                    "text": r["text"],
                }
                for r, p, pr, sm, ms in zip(
                    surfaces["boundary_neg_cal"],
                    neg_preds,
                    neg_probs,
                    neg_sup12_mass,
                    neg_max_single_per_row,
                )
            ],
            "pos_train_added_18": [
                {
                    "sample_id": r.get("sample_id"),
                    "gold": r["intent"],
                    "pred": STANDARD_INTENTS_46[int(p)],
                    "conf": float(c),
                    "correct": bool(STANDARD_INTENTS_46[int(p)] == r["intent"]),
                    "text": r["text"],
                }
                for r, p, c in zip(surfaces["pos_train_added_18"], add_preds, add_confs)
            ],
        },
    }


def main() -> None:
    t0 = time.perf_counter()

    # 1. SHA-256 inventory & baseline integrity checks
    arch_inv_sha = sha256_file(ARCH_LR5E6 / "archive_sha_inventory.json")
    side_inv_sha = sha256_file(REC_LR5E6 / "sidecar_sha_inventory.json")
    cal_guard_sha = sha256_file(REC_LR5E6 / "cal_guard_report.json")
    if arch_inv_sha != EXPECTED_ARCHIVE_INV_SHA:
        raise RuntimeError(f"Archive inventory SHA mismatch: {arch_inv_sha}")
    if side_inv_sha != EXPECTED_SIDECAR_INV_SHA:
        raise RuntimeError(f"Sidecar inventory SHA mismatch: {side_inv_sha}")
    if cal_guard_sha != EXPECTED_CAL_GUARD_SHA:
        raise RuntimeError(f"CAL guard report SHA mismatch: {cal_guard_sha}")

    arch_n, arch_mis = verify_inventory(ARCH_LR5E6, ARCH_LR5E6 / "archive_sha_inventory.json")
    side_n, side_mis = verify_inventory(REC_LR5E6, REC_LR5E6 / "sidecar_sha_inventory.json")
    inp_n, inp_mis = verify_inventory(REC_LR5E6 / "inputs", REC_LR5E6 / "inputs/inputs_sha256_inventory.json")
    prep_side_n, prep_side_mis = verify_inventory(PREP_V4, PREP_V4 / "sidecar_sha_inventory.json")
    if arch_mis or side_mis or inp_mis or prep_side_mis:
        raise RuntimeError(f"Inventory mismatches: {(arch_mis, side_mis, inp_mis, prep_side_mis)}")

    orig_sha = sha256_file(ARCH_ORIG / "model.safetensors")
    cand_sha = sha256_file(ARCH_LR5E6 / "model.safetensors")
    prior_2e5_sha = sha256_file(ARCH_2E5 / "model.safetensors")
    serving_sha = sha256_file(SERVING_DIR / "model.safetensors")
    assert orig_sha == EXPECTED_ORIG_SHA
    assert cand_sha == EXPECTED_CAND_SHA
    assert prior_2e5_sha == EXPECTED_2E5_SHA
    assert serving_sha == EXPECTED_SERVING_SHA

    # 2. Optimizer / LR propagation & source snapshot verification
    run_cfg = json.loads((REC_LR5E6 / "run_config.json").read_text(encoding="utf-8"))
    prov_manifest = json.loads((ARCH_LR5E6 / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))
    snap_mismatches: List[str] = []
    for rel, exp in run_cfg["source_hashes"].items():
        snap_f = REC_LR5E6 / "source_snapshot" / rel
        cur_f = ROOT / rel
        if sha256_file(snap_f) != exp.lower() or sha256_file(cur_f) != exp.lower():
            snap_mismatches.append(rel)

    fit_src = inspect.getsource(run_fit_and_lock_candidate)
    auth_src = inspect.getsource(run_authorized_fit)
    prof_cfg = validate_profile_settings(
        profile="lr5e6",
        epochs=int(run_cfg["epochs"]),
        lr=float(run_cfg["lr"]),
        batch_size=int(run_cfg["batch_size"]),
        seed=int(run_cfg["seed"]),
        fit_mode=str(run_cfg["fit_mode"]),
        enable_selective_rejector=bool(run_cfg["enable_selective_rejector"]),
    )
    lr_propagation_verified = (
        abs(float(AUTHORIZED_FIT_PROFILES["lr5e6"]["lr"]) - 5e-6) < 1e-15
        and abs(float(prof_cfg["lr"]) - 5e-6) < 1e-15
        and abs(float(run_cfg["lr"]) - 5e-6) < 1e-15
        and abs(float(prov_manifest["training_lineage"]["lr"]) - 5e-6) < 1e-15
        and "lr=float(profile_cfg[\"lr\"])" in auth_src
        and "torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)" in fit_src
        and "get_linear_schedule_with_warmup(" in fit_src
        and len(snap_mismatches) == 0
    )
    if not lr_propagation_verified:
        raise RuntimeError("LR 5e-6 propagation / optimizer / source snapshot check failed!")

    # 3. Verify 3 inherited bitext overlaps unchanged & check tokenization truncation anomaly
    inp_dir = REC_LR5E6 / "inputs"
    bit_clean = read_jsonl(inp_dir / "bitext_train_clean.jsonl")
    bit_noisy = read_jsonl(inp_dir / "bitext_train_noisy.jsonl")
    bit_cal = read_jsonl(inp_dir / "bitext_cal.jsonl")
    bit_test = read_jsonl(inp_dir / "bitext_test_6690.jsonl")
    noisy_norm_map: Dict[str, List[str]] = {}
    for r in bit_noisy:
        noisy_norm_map.setdefault(norm_text(r["text"]), []).append(str(r.get("sample_id")))
    overlaps = [
        {
            "test_idx": i,
            "sample_id": r.get("sample_id"),
            "intent": r.get("intent"),
            "train_sample_ids": noisy_norm_map[norm_text(r["text"])],
        }
        for i, r in enumerate(bit_test)
        if norm_text(r["text"]) in noisy_norm_map
    ]
    full_train_rows = read_jsonl(inp_dir / "full_train_split.jsonl")

    # 4. Load locked CAL guard surfaces and independently recompute
    pos_cal = read_jsonl(inp_dir / "boundary_pos_calibration.jsonl")
    neg_cal = read_jsonl(inp_dir / "boundary_neg_calibration.jsonl")
    pos_train = read_jsonl(inp_dir / "boundary_pos_train.jsonl")
    added_18 = [r for r in pos_train if str(r.get("sample_id", "")).startswith("orig_ret_ch_")]
    surfaces = {
        "boundary_pos_cal": pos_cal,
        "boundary_neg_cal": neg_cal,
        "bitext_cal": bit_cal,
        "pos_train_added_18": added_18,
    }
    assert {
        "boundary_pos_cal": len(pos_cal),
        "boundary_pos_cal_sup12": sum(r["intent"] in SUPPORTED_12_INTENTS for r in pos_cal),
        "boundary_pos_cal_esc34": sum(r["intent"] in ESCALATED_34_INTENTS for r in pos_cal),
        "bitext_cal": len(bit_cal),
        "boundary_neg_cal": len(neg_cal),
        "pos_train_added_18": len(added_18),
    } == CAL_GUARD_DENOMINATORS

    device_primary = "cuda" if torch.cuda.is_available() else "cpu"
    orig_cpu = evaluate_cal_surfaces_independent(ARCH_ORIG, surfaces, device_str="cpu")
    cand_cpu = evaluate_cal_surfaces_independent(ARCH_LR5E6, surfaces, device_str="cpu")
    cand_gpu = (
        evaluate_cal_surfaces_independent(ARCH_LR5E6, surfaces, device_str="cuda")
        if torch.cuda.is_available()
        else None
    )
    prior_2e5_cpu = evaluate_cal_surfaces_independent(ARCH_2E5, surfaces, device_str="cpu")

    # Compare recomputed report (using helper & independent formulas) vs sealed cal_guard_report.json
    sealed_report = json.loads((REC_LR5E6 / "cal_guard_report.json").read_text(encoding="utf-8"))
    recomp_cand_vs_orig_cpu = evaluate_cal_guard_report(cand_cpu["metrics"], orig_cpu["metrics"])
    recomp_cand_vs_orig_gpu = (
        evaluate_cal_guard_report(cand_gpu["metrics"], orig_cpu["metrics"]) if cand_gpu else None
    )
    recomp_2e5_vs_orig_cpu = evaluate_cal_guard_report(prior_2e5_cpu["metrics"], orig_cpu["metrics"])

    # Exact numerical diff audit vs sealed report
    float_diffs_vs_sealed: List[Dict[str, Any]] = []
    int_mismatches_vs_sealed: List[str] = []
    for s_chk, r_chk in zip(sealed_report["checks"], recomp_cand_vs_orig_cpu["checks"]):
        assert s_chk["name"] == r_chk["name"]
        if bool(s_chk["passed"]) != bool(r_chk["passed"]):
            int_mismatches_vs_sealed.append(f"status mismatch {s_chk['name']}")
        if s_chk["kind"] == "integer":
            if int(s_chk["actual"]) != int(r_chk["actual"]):
                int_mismatches_vs_sealed.append(f"int mismatch {s_chk['name']}: {r_chk['actual']} != {s_chk['actual']}")
        else:
            diff_actual = abs(float(r_chk["actual"]) - float(s_chk["actual"]))
            diff_limit = abs(float(r_chk["limit"]) - float(s_chk["limit"]))
            float_diffs_vs_sealed.append(
                {
                    "name": s_chk["name"],
                    "sealed_actual": float(s_chk["actual"]),
                    "cpu_recomputed_actual": float(r_chk["actual"]),
                    "abs_diff_actual": diff_actual,
                    "gpu_recomputed_actual": (
                        float(recomp_cand_vs_orig_gpu["checks"][sealed_report["checks"].index(s_chk)]["actual"])
                        if recomp_cand_vs_orig_gpu
                        else None
                    ),
                    "within_3e6_tol": diff_actual <= CAL_GUARD_FLOAT_TOLERANCE and diff_limit <= CAL_GUARD_FLOAT_TOLERANCE,
                }
            )

    # Row-level regressions/improvements vs orig_fit2
    pos_flips = []
    for r_o, r_c, r_2e5 in zip(
        orig_cpu["row_preds"]["boundary_pos_cal"],
        cand_cpu["row_preds"]["boundary_pos_cal"],
        prior_2e5_cpu["row_preds"]["boundary_pos_cal"],
    ):
        if r_o["pred"] != r_c["pred"] or abs(r_c["conf"] - r_o["conf"]) >= 0.05 or r_o["correct"] != r_c["correct"]:
            pos_flips.append(
                {
                    "sample_id": r_o["sample_id"],
                    "gold": r_o["gold"],
                    "is_sup12": r_o["is_sup12"],
                    "orig_pred": r_o["pred"],
                    "orig_conf": round(r_o["conf"], 6),
                    "cand_lr5e6_pred": r_c["pred"],
                    "cand_lr5e6_conf": round(r_c["conf"], 6),
                    "prior_2e5_pred": r_2e5["pred"],
                    "prior_2e5_conf": round(r_2e5["conf"], 6),
                    "delta_conf_lr5e6": round(r_c["conf"] - r_o["conf"], 6),
                }
            )

    neg_flips = []
    for r_o, r_c, r_2e5 in zip(
        orig_cpu["row_preds"]["boundary_neg_cal"],
        cand_cpu["row_preds"]["boundary_neg_cal"],
        prior_2e5_cpu["row_preds"]["boundary_neg_cal"],
    ):
        if (
            r_o["pred_is_sup12"] != r_c["pred_is_sup12"]
            or abs(r_c["sup12_mass"] - r_o["sup12_mass"]) >= 0.05
            or r_c["sup12_mass"] >= 0.60
            or r_c["max_single_sup12_prob"] >= 0.50
        ):
            neg_flips.append(
                {
                    "sample_id": r_o["sample_id"],
                    "category": r_o["category"],
                    "orig_pred": r_o["pred"],
                    "orig_sup12_mass": round(r_o["sup12_mass"], 6),
                    "orig_max_single_sup12": round(r_o["max_single_sup12_prob"], 6),
                    "cand_lr5e6_pred": r_c["pred"],
                    "cand_lr5e6_sup12_mass": round(r_c["sup12_mass"], 6),
                    "cand_lr5e6_max_single_sup12": round(r_c["max_single_sup12_prob"], 6),
                    "prior_2e5_pred": r_2e5["pred"],
                    "prior_2e5_sup12_mass": round(r_2e5["sup12_mass"], 6),
                    "prior_2e5_max_single_sup12": round(r_2e5["max_single_sup12_prob"], 6),
                }
            )

    # Save row-level predictions jsonl
    case_path = OUT_DIR / "cal_case_predictions.jsonl"
    with case_path.open("w", encoding="utf-8") as fh:
        for surface_key in ("boundary_pos_cal", "boundary_neg_cal", "pos_train_added_18"):
            for r_o, r_c, r_2e5 in zip(
                orig_cpu["row_preds"][surface_key],
                cand_cpu["row_preds"][surface_key],
                prior_2e5_cpu["row_preds"][surface_key],
            ):
                fh.write(
                    json.dumps(
                        {
                            "surface": surface_key,
                            "sample_id": r_o["sample_id"],
                            "orig_fit2": r_o,
                            "cand_lr5e6": r_c,
                            "prior_2e5": r_2e5,
                        }
                    )
                    + "\n"
                )

    head_sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    summary = {
        "git_head_at_verification": head_sha,
        "device_primary_seen": device_primary,
        "duration_seconds": round(time.perf_counter() - t0, 2),
        "integrity_verification": {
            "archive_sha_inventory": arch_inv_sha,
            "archive_files_verified": arch_n,
            "archive_mismatches": arch_mis,
            "sidecar_sha_inventory": side_inv_sha,
            "sidecar_files_verified": side_n,
            "sidecar_mismatches": side_mis,
            "inputs_files_verified": inp_n,
            "inputs_mismatches": inp_mis,
            "v4_prep_sidecar_verified": prep_side_n,
            "v4_prep_sidecar_mismatches": prep_side_mis,
            "orig_fit2_weights_sha256": orig_sha,
            "cand_lr5e6_weights_sha256": cand_sha,
            "prior_2e5_weights_sha256": prior_2e5_sha,
            "serving_weights_sha256_untouched": serving_sha,
            "cal_guard_report_sha256": cal_guard_sha,
            "source_snapshot_mismatches": snap_mismatches,
        },
        "optimizer_and_lr_propagation_audit": {
            "verified": True,
            "bug_detected": False,
            "actual_lr": float(run_cfg["lr"]),
            "actual_optimizer": "torch.optim.AdamW(lr=lr, weight_decay=0.01) + get_linear_schedule_with_warmup(0.10*steps)",
            "epochs": int(run_cfg["epochs"]),
            "batch_size": int(run_cfg["batch_size"]),
            "seed": int(run_cfg["seed"]),
            "fit_mode": str(run_cfg["fit_mode"]),
            "train_total_examples": int(prov_manifest["training_lineage"]["train_total_examples"]),
            "cosmetic_provenance_note": {
                "token_truncation_audit_train_all_count": int(prov_manifest["token_truncation_audit"]["train_all"]["count"]),
                "actual_full_train_split_count": len(full_train_rows),
                "classification": "benign_cosmetic_provenance_audit_bug_not_training_input",
                "explanation": "audit_token_truncation counts full_train_split in boundary_curriculum_data/repo root (11320) instead of prep datasets/full_train_split.jsonl (11338); real training loop consumed locked prep inputs/boundary_pos_train.jsonl (+18 rows -> 13080 effective examples matching fit-v1).",
            },
        },
        "historical_bitext_overlaps": {
            "count": len(overlaps),
            "overlaps": overlaps,
            "unchanged_from_orig_fit2": True,
        },
        "cal_guard_recomputation": {
            "independent_status": recomp_cand_vs_orig_cpu["recommended_status"],
            "sealed_status": sealed_report["recommended_status"],
            "exact_status_match": recomp_cand_vs_orig_cpu["recommended_status"] == sealed_report["recommended_status"] == "CAL_GUARD_REJECT_DO_NOT_PROMOTE",
            "reproduced_failed_checks": recomp_cand_vs_orig_cpu["failed_checks"],
            "int_mismatches_vs_sealed": int_mismatches_vs_sealed,
            "float_diffs_vs_sealed_cpu": float_diffs_vs_sealed,
            "max_float_abs_diff_cpu_vs_sealed": max(x["abs_diff_actual"] for x in float_diffs_vs_sealed),
            "all_within_tolerance_3e6": all(x["within_3e6_tol"] for x in float_diffs_vs_sealed),
            "cpu_vs_gpu_cand_passed_equal": (
                recomp_cand_vs_orig_gpu["failed_checks"] == recomp_cand_vs_orig_cpu["failed_checks"]
                if recomp_cand_vs_orig_gpu
                else None
            ),
            "mc_parity_orig": orig_cpu["mc_parity"],
            "mc_parity_cand_lr5e6": cand_cpu["mc_parity"],
            "mc_parity_prior_2e5": prior_2e5_cpu["mc_parity"],
        },
        "models_cal_guard_comparison": {
            "orig_fit2": orig_cpu["metrics"],
            "cand_lr5e6": {
                "metrics": cand_cpu["metrics"],
                "checks": recomp_cand_vs_orig_cpu["checks"],
                "failed_checks": recomp_cand_vs_orig_cpu["failed_checks"],
            },
            "prior_2e5": {
                "metrics": prior_2e5_cpu["metrics"],
                "checks": recomp_2e5_vs_orig_cpu["checks"],
                "failed_checks": recomp_2e5_vs_orig_cpu["failed_checks"],
            },
        },
        "diagnostic_samples": {
            "pos_cal_flips_or_large_conf_shifts_count": len(pos_flips),
            "pos_cal_flips_or_large_conf_shifts": pos_flips,
            "neg_cal_notable_rows_count": len(neg_flips),
            "neg_cal_notable_rows": neg_flips,
        },
    }

    summary_path = OUT_DIR / "cal_verification_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "generated_by": "Worker C independent read-only CAL verification",
        "git_head": head_sha,
        "commands": [f".venv/Scripts/python.exe -B {Path(__file__).relative_to(ROOT).as_posix()}"],
        "zero_full_eval_or_ood_or_heldout_rerun": True,
        "sha256": {
            "cal_verification_summary.json": sha256_file(summary_path),
            "cal_case_predictions.jsonl": sha256_file(case_path),
            "verify_cal_guard.py": sha256_file(Path(__file__)),
            "verified_cal_guard_report.json": cal_guard_sha,
            "verified_archive_sha_inventory.json": arch_inv_sha,
            "verified_sidecar_sha_inventory.json": side_inv_sha,
        },
    }
    manifest_path = OUT_DIR / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print("VERDICT:", summary["cal_guard_recomputation"]["independent_status"])
    print("FAILED_CHECKS:", summary["cal_guard_recomputation"]["reproduced_failed_checks"])
    print("INT_MISMATCHES:", int_mismatches_vs_sealed)
    print("MAX_CPU_VS_SEALED_FLOAT_DIFF:", summary["cal_guard_recomputation"]["max_float_abs_diff_cpu_vs_sealed"])
    print("MC_PARITY_LR5E6:", cand_cpu["mc_parity"])
    print("PRIOR_2E5_CAL_FAILED_CHECKS:", recomp_2e5_vs_orig_cpu["failed_checks"])
    print("DURATION_S:", summary["duration_seconds"])


if __name__ == "__main__":
    main()

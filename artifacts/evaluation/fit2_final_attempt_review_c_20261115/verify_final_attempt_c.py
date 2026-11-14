"""Worker C FINAL bounded read-only verification for Attempt 2/2 (fit2-orig-pre-classifier-head-v1).

Strictly read-only: ZERO optimizer steps, ZERO backward passes, ZERO new fits/calibrators,
ZERO paid LLM calls, ZERO holdout/OOD/full eval inference, ZERO cleanup/config/runtime edits.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.request
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
from pipeline.training.train_boundary_candidate import _snapshot_frozen_component_hashes
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_FLOAT_TOLERANCE,
    evaluate_cal_guard_report,
)

OUT_DIR = Path(__file__).resolve().parent

ARCH_PCH = ROOT / "artifacts/models/candidates/fit2-orig-pre-classifier-head-v1"
REC_PCH = ROOT / "artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1"
PREP_PCH = ROOT / "artifacts/models/candidates/run-records-fit2-orig-pre-classifier-head-v1-prep"
PREP_V4 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep"

ARCH_ORIG = ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
ARCH_FIT1 = ROOT / "artifacts/models/candidates/reconstructed-closure-fit1-20261113"
SERVING_DIR = ROOT / "artifacts/models/trained/distilbert-supportiq"
ARCH_CTRL = ROOT / "artifacts/models/candidates/fit2-orig-zero-delta-control-v1"
ARCH_2E5 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
ARCH_LR5E6 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1"
ARCH_TKL = ROOT / "artifacts/models/candidates/fit2-orig-teacher-kl-v1"
ARCH_DKL = ROOT / "artifacts/models/candidates/fit2-orig-deterministic-kl-v1"
ARCH_HO = ROOT / "artifacts/models/candidates/fit2-orig-classifier-head-only-v1"

PRIOR_HO_FINAL_JSON = ROOT / "artifacts/evaluation/fit2_head_only_final_review_c_20261114/head_only_cal_verification.json"

TRAINING_CAP_PATH = ROOT / ".local/training-cap-20261114.json"
AI_ENV_PATH = ROOT / ".local/ai.env"
TEMPLATE_PPTX_PATH = ROOT / "docs/report.template.pptx"
CODEGRAPH_DIR = ROOT / ".codegraph"

EXPECTED_HASHES = {
    "pch_weights": "374afde7977434ac0aae19efd2ac55bcfb6c04127531a355098dfe62a7490369",
    "pch_cal": "9d7fc0b79a52d5760c803c67e9ffab1355021bf570f3ae809d4aeb814cbac6c5",
    "pch_prov": "69cfb56ebe15422725baff634bf5a3167322337c0d9044747fe39a33073de1bc",
    "pch_archive_inv": "87587acc935067d43f0002d1918eed91463360fb8676a1785f3954d474d8b27e",
    "pch_cal_guard": "9b3ec85c1f3f9aa5dd48607da814c1a8b82ef43cc340761cea66343fecfd4b9b",
    "pch_sidecar_inv": "db4e56df14992bbefb6a0bdb59656739dd242f22fe2b5927b090618869d5cf9b",
    "pch_prep_manifest": "23b82dfe9a17d384fd85ad7f24d9a8c9cb61f2f05f7a95c4290e1cab6971d3dc",
    "frozen_tensors_sha256": "d16052a208919dfd2fa09f8bb4330ddbc37fab58fa7c8573dd31a686083a0151",
    "orig_weights": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "fit1_weights": "95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6",
    "serving_weights": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "ctrl_weights": "904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee",
    "prior_2e5_weights": "dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d",
    "lr5e6_weights": "b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2",
    "tkl_weights": "3994af2c461cd029f4d03dbec38a75b2bb103a78d8550f4f3a20078b354bca06",
    "dkl_weights": "e63d1ea963e165aaabdd8b619f2e1bf26914fff746bc9f1b7f888c3acf0191f1",
    "ho_weights": "c0908ffb9794a4c9450959534c694e64dd1c296a2dc65831334a17e7c5409afb",
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


def verify_inventory(base: Path, inv_path: Path, *, exclude_name: str | None = None) -> Tuple[int, List[str]]:
    payload = json.loads(inv_path.read_text(encoding="utf-8"))
    files = payload.get("files", payload)
    mismatches: List[str] = []
    if exclude_name is not None:
        actual_rel = {
            str(p.relative_to(base)).replace("\\", "/")
            for p in sorted(base.rglob("*"))
            if p.is_file() and p.name != exclude_name
        }
        if actual_rel != set(files.keys()):
            mismatches.append(
                f"file_set_mismatch: missing={sorted(set(files.keys()) - actual_rel)} extra={sorted(actual_rel - set(files.keys()))}"
            )
    for rel, meta in files.items():
        fp = base / rel
        exp = (meta["sha256"] if isinstance(meta, dict) else str(meta)).lower()
        act = sha256_file(fp) if fp.is_file() else "MISSING"
        if act != exp:
            mismatches.append(f"{rel}: {act} != {exp}")
    return len(files), mismatches


def pure_softmax_float64(logits: np.ndarray, temperature: float) -> np.ndarray:
    scaled = np.asarray(logits, dtype=np.float64) / float(temperature)
    shifted = scaled - np.max(scaled, axis=1, keepdims=True)
    exps = np.exp(shifted)
    return exps / np.sum(exps, axis=1, keepdims=True)


def kl_p_teacher_student_float64(p_teacher: np.ndarray, p_student: np.ndarray) -> np.ndarray:
    pt = np.clip(p_teacher, 1e-12, 1.0)
    ps = np.clip(p_student, 1e-12, 1.0)
    return np.sum(pt * (np.log(pt) - np.log(ps)), axis=1)


def probe_readonly_runtime_health() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for url in ("http://127.0.0.1:8002/health/ready", "http://127.0.0.1:8000/health/ready"):
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                out[url] = {"status": int(resp.status), "body": resp.read().decode("utf-8", errors="replace")[:500]}
        except Exception as exc:
            out[url] = {"error": f"{type(exc).__name__}: {exc}"}
    return out


def verify_frozen_tensors_and_subhead_deltas(prov_man: Dict[str, Any]) -> Dict[str, Any]:
    """Verify bit-identity of all 100 frozen param tensors + 1 buffer vs orig_fit2 and quantify 4 subhead tensor updates."""
    orig_model = AutoModelForSequenceClassification.from_pretrained(str(ARCH_ORIG), local_files_only=True)
    pch_model = AutoModelForSequenceClassification.from_pretrained(str(ARCH_PCH), local_files_only=True)

    trainable_set = {"pre_classifier.weight", "pre_classifier.bias", "classifier.weight", "classifier.bias"}
    for m in (orig_model, pch_model):
        for name, p in m.named_parameters():
            p.requires_grad_(name in trainable_set)

    orig_snap = _snapshot_frozen_component_hashes(orig_model)
    pch_snap = _snapshot_frozen_component_hashes(pch_model)

    assert orig_snap["all_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert pch_snap["all_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert orig_snap["component_hashes"] == pch_snap["component_hashes"]
    assert orig_snap["frozen_tensor_hashes"] == pch_snap["frozen_tensor_hashes"]
    assert orig_snap["buffer_hashes"] == pch_snap["buffer_hashes"]

    lineage = prov_man["training_lineage"]
    assert lineage["initial_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert lineage["post_fit_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert lineage["post_fit_freeze_verified"] is True
    assert lineage["initial_freeze_component_hashes"] == pch_snap["component_hashes"]
    assert lineage["post_fit_freeze_component_hashes"] == pch_snap["component_hashes"]

    orig_params = dict(orig_model.named_parameters())
    pch_params = dict(pch_model.named_parameters())
    orig_buffers = dict(orig_model.named_buffers())
    pch_buffers = dict(pch_model.named_buffers())

    total_params = sum(int(p.numel()) for p in pch_params.values())
    frozen_param_count = sum(int(p.numel()) for p in pch_params.values() if not p.requires_grad)
    trainable_param_count = sum(int(p.numel()) for p in pch_params.values() if p.requires_grad)
    assert len(pch_snap["frozen_tensor_hashes"]) == 100
    assert len(pch_snap["buffer_hashes"]) == 1
    assert frozen_param_count == 66362880
    assert trainable_param_count == 625966
    assert total_params == 66988846

    max_frozen_param_abs_diff = 0.0
    for k in pch_snap["frozen_tensor_hashes"]:
        d = float(torch.max(torch.abs(pch_params[k].detach() - orig_params[k].detach())).item())
        max_frozen_param_abs_diff = max(max_frozen_param_abs_diff, d)

    max_buffer_abs_diff = 0.0
    for k in pch_snap["buffer_hashes"]:
        d = float(torch.max(torch.abs((pch_buffers[k].detach() - orig_buffers[k].detach()).to(torch.float64))).item())
        max_buffer_abs_diff = max(max_buffer_abs_diff, d)

    assert max_frozen_param_abs_diff == 0.0
    assert max_buffer_abs_diff == 0.0

    trainable_deltas: Dict[str, Dict[str, float]] = {}
    for name in sorted(trainable_set):
        t0 = orig_params[name].detach()
        t1 = pch_params[name].detach()
        max_abs_f32 = float(torch.max(torch.abs(t1 - t0)).item())
        diff_f64 = (t1 - t0).to(torch.float64)
        base_f64 = t0.to(torch.float64)
        l2_d = float(torch.linalg.norm(diff_f64).item())
        l2_b = float(torch.linalg.norm(base_f64).item())
        assert l2_d > 0.0, f"Expected non-zero update in {name}"
        rec_max = float(lineage["trainable_max_abs_delta"][name])
        assert abs(max_abs_f32 - rec_max) <= 1e-7, f"{name}: {max_abs_f32} != {rec_max}"
        trainable_deltas[name] = {
            "numel": int(t1.numel()),
            "l2_delta": l2_d,
            "rel_l2_delta": float(l2_d / l2_b),
            "orig_frob": l2_b,
            "cand_frob": float(torch.linalg.norm(t1.to(torch.float64)).item()),
            "max_abs_delta": max_abs_f32,
        }

    dw_cls = (pch_params["classifier.weight"].detach() - orig_params["classifier.weight"].detach()).to(torch.float64)
    row_l2 = torch.linalg.vector_norm(dw_cls, dim=1)
    top_idx = torch.argsort(row_l2, descending=True)[:8]
    top_shifted_cls_rows = [
        {
            "intent": STANDARD_INTENTS_46[int(i)],
            "weight_row_l2_delta": float(row_l2[int(i)].item()),
            "orig_row_norm": float(torch.linalg.vector_norm(orig_params["classifier.weight"].detach().to(torch.float64)[int(i)]).item()),
            "cand_row_norm": float(torch.linalg.vector_norm(pch_params["classifier.weight"].detach().to(torch.float64)[int(i)]).item()),
        }
        for i in top_idx
    ]

    return {
        "total_params": total_params,
        "frozen_param_tensors_count": len(pch_snap["frozen_tensor_hashes"]),
        "frozen_params": frozen_param_count,
        "buffer_count": len(pch_snap["buffer_hashes"]),
        "buffer_names": sorted(pch_snap["buffer_hashes"].keys()),
        "trainable_params": trainable_param_count,
        "trainable_names": sorted(k for k, p in pch_params.items() if p.requires_grad),
        "all_frozen_tensors_sha256": pch_snap["all_frozen_tensors_sha256"],
        "component_hashes_count": len(pch_snap["component_hashes"]),
        "component_hashes_match": True,
        "max_frozen_param_abs_diff": max_frozen_param_abs_diff,
        "max_buffer_abs_diff": max_buffer_abs_diff,
        "trainable_tensor_deltas": trainable_deltas,
        "top_shifted_classifier_rows": top_shifted_cls_rows,
    }


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
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device)
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
            chunks.append(model(**enc).logits.detach().cpu().numpy().astype(np.float64))
    return np.vstack(chunks)


def summarize_positive_with_breakdown(
    probs: np.ndarray,
    rows: Sequence[Dict[str, Any]],
    *,
    idx_by_label: Dict[str, int],
    sup12_indices: np.ndarray,
    sup12_set: set[str],
    teacher_probs: np.ndarray | None = None,
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
        "mean_kl_vs_orig_fit2": float(np.mean(kl_p_teacher_student_float64(teacher_probs, probs)))
        if teacher_probs is not None
        else 0.0,
    }
    return summary, breakdown, preds, max_probs


def evaluate_model_surfaces(
    model_dir: Path,
    surfaces: Dict[str, List[Dict[str, Any]]],
    *,
    device_str: str,
    orig_probs_by_surface: Dict[str, np.ndarray] | None = None,
    check_mc_parity: bool = False,
) -> Dict[str, Any]:
    cal_manifest = json.loads((model_dir / "calibration_manifest.json").read_text(encoding="utf-8"))
    temp = float(cal_manifest["calibration"]["temperature"])
    min_temp = float(cal_manifest["calibration"]["min_temperature"])
    if abs(temp - 1.0) > 1e-12 or abs(min_temp - 1.0) > 1e-12:
        raise ValueError(f"Expected T=1.0 in {model_dir}; got {temp}, {min_temp}")
    if cal_manifest.get("selective_rejector", {}).get("enabled", False):
        raise ValueError(f"Expected selective_rejector.enabled=false in {model_dir}")
    max_len = int(cal_manifest["tokenization"]["max_length"])

    idx_by_label = {lbl: i for i, lbl in enumerate(STANDARD_INTENTS_46)}
    sup12_indices = np.array([idx_by_label[l] for l in SUPPORTED_12_INTENTS], dtype=np.int64)
    sup12_set = set(SUPPORTED_12_INTENTS)
    esc34_set = set(ESCALATED_34_INTENTS)

    probs_by_surface: Dict[str, np.ndarray] = {}
    for name, rows in surfaces.items():
        logits = forward_logits(model_dir, [str(r["text"]) for r in rows], device_str=device_str, max_length=max_len)
        probs_by_surface[name] = pure_softmax_float64(logits, temp)

    def _op(name: str) -> np.ndarray | None:
        return None if orig_probs_by_surface is None else orig_probs_by_surface[name]

    pos_cal_rows = surfaces["boundary_pos_cal"]
    pos_cal_probs = probs_by_surface["boundary_pos_cal"]
    cal_sup12_mask = np.array([r["intent"] in sup12_set for r in pos_cal_rows], dtype=bool)
    cal_esc34_mask = np.array([r["intent"] in esc34_set for r in pos_cal_rows], dtype=bool)

    pos_sum, pos_bd, pos_preds, pos_confs = summarize_positive_with_breakdown(
        pos_cal_probs, pos_cal_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set, teacher_probs=_op("boundary_pos_cal")
    )
    sup_sum, sup_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_sup12_mask],
        [r for r, f in zip(pos_cal_rows, cal_sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=(_op("boundary_pos_cal")[cal_sup12_mask] if _op("boundary_pos_cal") is not None else None),
    )
    esc_sum, esc_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_esc34_mask],
        [r for r, f in zip(pos_cal_rows, cal_esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=(_op("boundary_pos_cal")[cal_esc34_mask] if _op("boundary_pos_cal") is not None else None),
    )
    bit_sum, bit_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["bitext_cal"],
        surfaces["bitext_cal"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("bitext_cal"),
    )
    add18_sum, add18_bd, add18_preds, add18_confs = summarize_positive_with_breakdown(
        probs_by_surface["pos_train_added_18"],
        surfaces["pos_train_added_18"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("pos_train_added_18"),
    )
    _, trn_pos_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["boundary_pos_train"],
        surfaces["boundary_pos_train"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("boundary_pos_train"),
    )
    _, trn_canon_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["canonical_pos_train"],
        surfaces["canonical_pos_train"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("canonical_pos_train"),
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
    neg_trn_pred_sup12_mask = np.array([STANDARD_INTENTS_46[int(p)] in sup12_set for p in neg_trn_preds], dtype=bool)

    cal_guard_metrics = {
        "temperature": float(temp),
        "boundary_pos_cal": {k: pos_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "boundary_pos_cal_sup12": {
            k: sup_sum[k]
            for k in ("count", "correct_count", "accuracy", "mean_max_prob", "conf_ge_070_count", "conf_ge_080_count")
        },
        "boundary_pos_cal_esc34": {
            k: esc_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob", "max_sup12_mass")
        },
        "bitext_cal": {k: bit_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "pos_train_added_18": {k: add18_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "boundary_neg_cal": {
            "count": len(surfaces["boundary_neg_cal"]),
            "pred_sup12_count": int(np.sum(neg_cal_pred_sup12_mask)),
            "max_sup12_mass": float(np.max(neg_cal_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_cal_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_cal_max_single)),
            "mean_kl_vs_orig_fit2": float(np.mean(kl_p_teacher_student_float64(_op("boundary_neg_cal"), neg_cal_probs)))
            if _op("boundary_neg_cal") is not None
            else 0.0,
        },
        "attribution_breakdown": {
            "boundary_pos_cal": pos_bd,
            "boundary_pos_cal_sup12": sup_bd,
            "boundary_pos_cal_esc34": esc_bd,
            "bitext_cal": bit_bd,
        },
    }

    train_metrics = {
        "boundary_pos_train_199": trn_pos_bd,
        "canonical_pos_train_181": trn_canon_bd,
        "boundary_neg_train_99": {
            "count": len(surfaces["boundary_neg_train"]),
            "pred_sup12_count": int(np.sum(neg_trn_pred_sup12_mask)),
            "max_sup12_mass": float(np.max(neg_trn_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_trn_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_trn_sup12_probs)),
            "mean_kl_vs_orig_fit2": float(np.mean(kl_p_teacher_student_float64(_op("boundary_neg_train"), neg_trn_probs)))
            if _op("boundary_neg_train") is not None
            else 0.0,
        },
        "pos_train_added_18": add18_bd,
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
        "pos_train_added_18": [
            {
                "sample_id": r.get("sample_id"),
                "gold": r["intent"],
                "pred": STANDARD_INTENTS_46[int(p)],
                "correct": bool(STANDARD_INTENTS_46[int(p)] == r["intent"]),
                "conf": float(c),
                "text": r["text"],
            }
            for r, p, c in zip(surfaces["pos_train_added_18"], add18_preds, add18_confs)
        ],
    }

    return {
        "probs_by_surface": probs_by_surface,
        "cal_guard_metrics": cal_guard_metrics,
        "train_metrics": train_metrics,
        "mc_parity": mc_parity,
        "row_preds": row_preds,
    }


def main() -> None:
    t0 = time.perf_counter()

    # 1. Verify top-level hashes and all preserved checkpoints
    actual_hashes = {
        "pch_weights": sha256_file(ARCH_PCH / "model.safetensors"),
        "pch_cal": sha256_file(ARCH_PCH / "calibration_manifest.json"),
        "pch_prov": sha256_file(ARCH_PCH / "candidate_provenance_manifest.json"),
        "pch_archive_inv": sha256_file(ARCH_PCH / "archive_sha_inventory.json"),
        "pch_cal_guard": sha256_file(REC_PCH / "cal_guard_report.json"),
        "pch_sidecar_inv": sha256_file(REC_PCH / "sidecar_sha_inventory.json"),
        "pch_prep_manifest": sha256_file(PREP_PCH / "prep_manifest.json"),
        "orig_weights": sha256_file(ARCH_ORIG / "model.safetensors"),
        "fit1_weights": sha256_file(ARCH_FIT1 / "model.safetensors"),
        "serving_weights": sha256_file(SERVING_DIR / "model.safetensors"),
        "ctrl_weights": sha256_file(ARCH_CTRL / "model.safetensors"),
        "prior_2e5_weights": sha256_file(ARCH_2E5 / "model.safetensors"),
        "lr5e6_weights": sha256_file(ARCH_LR5E6 / "model.safetensors"),
        "tkl_weights": sha256_file(ARCH_TKL / "model.safetensors"),
        "dkl_weights": sha256_file(ARCH_DKL / "model.safetensors"),
        "ho_weights": sha256_file(ARCH_HO / "model.safetensors"),
    }
    bad = {k: (v, EXPECTED_HASHES[k]) for k, v in actual_hashes.items() if v != EXPECTED_HASHES[k]}
    if bad:
        raise RuntimeError(f"Hash mismatches: {bad}")

    arch_n, arch_mis = verify_inventory(ARCH_PCH, ARCH_PCH / "archive_sha_inventory.json", exclude_name="archive_sha_inventory.json")
    side_n, side_mis = verify_inventory(REC_PCH, REC_PCH / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    prep_n, prep_mis = verify_inventory(PREP_PCH, PREP_PCH / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    if arch_mis or side_mis or prep_mis:
        raise RuntimeError(f"Inventory mismatches: arch={arch_mis}, side={side_mis}, prep={prep_mis}")

    # 2. Budget exhaustion (2/2 STOPPED), runtime env, and preserved repository assets
    training_cap = json.loads(TRAINING_CAP_PATH.read_text(encoding="utf-8"))
    assert training_cap["additional_attempt_limit"] == 2
    assert training_cap["additional_attempts_started"] == 2
    assert training_cap["training_stopped"] is True
    assert training_cap["stop_reason"] == "budget_exhausted"
    assert training_cap["final_attempt"] is True
    assert training_cap["no_more_training_authorized"] is True
    assert len(training_cap["attempts"]) == 2
    assert training_cap["attempts"][1]["weights_sha256"] == EXPECTED_HASHES["pch_weights"]
    assert training_cap["attempts"][1]["calibration_manifest_sha256"] == EXPECTED_HASHES["pch_cal"]

    ai_env_kv: Dict[str, str] = {}
    if AI_ENV_PATH.is_file():
        for raw in AI_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                ai_env_kv[k.strip()] = v.strip()

    runtime_health = probe_readonly_runtime_health()
    git_status_short = subprocess.check_output(["git", "-C", str(ROOT), "status", "--short"], text=True).splitlines()

    preserved_assets = {
        "training_cap": training_cap,
        "training_cap_sha256": sha256_file(TRAINING_CAP_PATH),
        "ai_env_exists": AI_ENV_PATH.is_file(),
        "ai_env_sha256": sha256_file(AI_ENV_PATH) if AI_ENV_PATH.is_file() else None,
        "ai_env_model_dir": ai_env_kv.get("SUPPORTIQ_MODEL_DIR"),
        "ai_env_cal_manifest": ai_env_kv.get("SUPPORTIQ_CALIBRATION_MANIFEST_PATH"),
        "readonly_health_check": runtime_health,
        "report_template_pptx_exists": TEMPLATE_PPTX_PATH.is_file(),
        "report_template_pptx_bytes": TEMPLATE_PPTX_PATH.stat().st_size if TEMPLATE_PPTX_PATH.is_file() else None,
        "report_template_pptx_sha256": sha256_file(TEMPLATE_PPTX_PATH) if TEMPLATE_PPTX_PATH.is_file() else None,
        "codegraph_dir_exists": CODEGRAPH_DIR.is_dir(),
        "codegraph_files": sorted(p.name for p in CODEGRAPH_DIR.iterdir() if p.is_file()) if CODEGRAPH_DIR.is_dir() else [],
        "artifacts_models_gitkeep_exists": (ROOT / "artifacts/models/.gitkeep").exists(),
        "git_status_before_bundle": git_status_short,
    }

    # 3. Input parity, profile config, and source snapshot
    rec_in = REC_PCH / "inputs"
    prep_ds = PREP_PCH / "datasets"
    v4_ds = PREP_V4 / "datasets"
    input_files = sorted(p.name for p in prep_ds.iterdir() if p.is_file())
    rec_vs_prep_diffs = [f for f in input_files if sha256_file(rec_in / f) != sha256_file(prep_ds / f)]
    data_files = [f for f in input_files if f.endswith(".jsonl") or f == "split_manifest.json"]
    v4_diffs = [f for f in data_files if sha256_file(prep_ds / f) != sha256_file(v4_ds / f)]
    assert not rec_vs_prep_diffs and not v4_diffs

    run_cfg = json.loads((REC_PCH / "run_config.json").read_text(encoding="utf-8"))
    prep_man = json.loads((PREP_PCH / "prep_manifest.json").read_text(encoding="utf-8"))
    fit_res = json.loads((REC_PCH / "fit_result.json").read_text(encoding="utf-8"))
    status_rec = json.loads((REC_PCH / "status.json").read_text(encoding="utf-8"))
    recorded_guard = json.loads((REC_PCH / "cal_guard_report.json").read_text(encoding="utf-8"))
    prov_man = json.loads((ARCH_PCH / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))

    prof = AUTHORIZED_FIT_PROFILES["option_a_pre_classifier_head_v1"]
    sub_cfg = run_cfg["subhead_scope_config"]
    assert run_cfg["authorized_fit_profile"] == "option_a_pre_classifier_head_v1"
    assert abs(float(run_cfg["lr"]) - float(prof["lr"])) < 1e-12
    assert int(run_cfg["epochs"]) == int(prof["epochs"])
    assert int(run_cfg["batch_size"]) == int(prof["batch_size"])
    assert int(run_cfg["seed"]) == int(prof["seed"])
    assert run_cfg["fit_mode"] == prof["fit_mode"]
    assert sub_cfg["trainable_scope"] == "pre_classifier_and_classifier"
    assert sub_cfg["feature_dropout_eval_mode"] is True
    assert abs(float(sub_cfg["weight_decay"]) - 0.01) < 1e-12
    assert sub_cfg["expected_trainable_param_count"] == 625966
    assert sub_cfg["expected_frozen_param_count"] == 66362880
    assert sub_cfg["teacher_used"] is False
    assert run_cfg["enable_selective_rejector"] is False
    assert float(run_cfg["min_temperature"]) == 1.0
    assert prov_man["base_model"]["unfrozen_transformer_layers"] == 0
    assert status_rec["fits_started"] == 1 and status_rec["fits_completed"] == 1

    snap_dir = REC_PCH / "source_snapshot"
    snap_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(snap_dir / rel) != h.lower()]
    disk_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(ROOT / rel) != h.lower()]
    prep_src_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if prep_man["source_hashes"].get(rel, "").lower() != h.lower()]
    assert not snap_diffs and not disk_diffs and not prep_src_diffs

    # 4. Frozen tensor & subhead delta proof
    freeze_verification = verify_frozen_tensors_and_subhead_deltas(prov_man)

    # 5. Sealed overlaps count (metadata-only, zero holdout inference)
    pos_train = read_jsonl(rec_in / "boundary_pos_train.jsonl")
    canon_pos_train = [r for r in pos_train if not str(r.get("sample_id", "")).startswith("orig_ret_ch_")]
    neg_train = read_jsonl(rec_in / "boundary_neg_train.jsonl")
    bitext_clean = read_jsonl(rec_in / "bitext_train_clean.jsonl")
    bitext_noisy = read_jsonl(rec_in / "bitext_train_noisy.jsonl")
    pos_cal = read_jsonl(rec_in / "boundary_pos_calibration.jsonl")
    neg_cal = read_jsonl(rec_in / "boundary_neg_calibration.jsonl")
    pos_eval = read_jsonl(rec_in / "boundary_pos_evaluation.jsonl")
    neg_eval = read_jsonl(rec_in / "boundary_neg_evaluation.jsonl")
    bitext_cal = read_jsonl(rec_in / "bitext_cal.jsonl")
    bitext_test = read_jsonl(rec_in / "bitext_test_6690.jsonl")
    full_cal = read_jsonl(rec_in / "full_cal_split.jsonl")
    added_18 = read_jsonl(rec_in / "orig_fit2_return_contrast_extension.jsonl")

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

    # 6. Fresh CAL + canonical TRAIN inference for orig_fit2 and pre_classifier_head + ModelContainer parity
    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    surfaces = {
        "boundary_pos_cal": pos_cal,
        "boundary_neg_cal": neg_cal,
        "bitext_cal": bitext_cal,
        "boundary_pos_train": pos_train,
        "canonical_pos_train": canon_pos_train,
        "boundary_neg_train": neg_train,
        "pos_train_added_18": added_18,
    }
    eval_orig = evaluate_model_surfaces(ARCH_ORIG, surfaces, device_str=device_str, orig_probs_by_surface=None, check_mc_parity=False)
    eval_pch = evaluate_model_surfaces(
        ARCH_PCH,
        surfaces,
        device_str=device_str,
        orig_probs_by_surface=eval_orig["probs_by_surface"],
        check_mc_parity=True,
    )

    recomputed_guard = evaluate_cal_guard_report(
        eval_pch["cal_guard_metrics"],
        eval_orig["cal_guard_metrics"],
        float_tolerance=CAL_GUARD_FLOAT_TOLERANCE,
        cal_guard_mode="candidate",
    )
    assert recomputed_guard["cal_guard_mode"] == "candidate_12_checks"
    assert len(recomputed_guard["checks"]) == 12
    assert recomputed_guard["passed"] is False
    assert recomputed_guard["recommended_status"] == "CAL_GUARD_REJECT_DO_NOT_PROMOTE"
    assert recomputed_guard["failed_checks"] == recorded_guard["failed_checks"]

    max_guard_float_diff = 0.0
    for rc, ac in zip(recomputed_guard["checks"], recorded_guard["checks"]):
        assert rc["name"] == ac["name"] and rc["passed"] == ac["passed"]
        if rc["kind"] == "integer":
            assert rc["actual"] == ac["actual"], f"{rc['name']} int mismatch: {rc['actual']} != {ac['actual']}"
        else:
            diff = abs(float(rc["actual"]) - float(ac["actual"]))
            max_guard_float_diff = max(max_guard_float_diff, diff)
            assert diff <= CAL_GUARD_FLOAT_TOLERANCE, f"{rc['name']} float diff {diff}"
            if "limit" in ac:
                lim_diff = abs(float(rc["limit"]) - float(ac["limit"]))
                max_guard_float_diff = max(max_guard_float_diff, lim_diff)
                assert lim_diff <= CAL_GUARD_FLOAT_TOLERANCE

    def flip_details(other_rows: Sequence[Dict[str, Any]], base_rows: Sequence[Dict[str, Any]], is_pos: bool) -> Dict[str, Any]:
        if is_pos:
            gained = [
                {
                    "sample_id": o["sample_id"],
                    "gold": o["gold"],
                    "is_sup12": o["is_sup12"],
                    "orig_pred": b["pred"],
                    "orig_conf": b["conf"],
                    "pch_pred": o["pred"],
                    "pch_conf": o["conf"],
                }
                for b, o in zip(base_rows, other_rows)
                if (not b["correct"]) and o["correct"]
            ]
            lost = [
                {
                    "sample_id": o["sample_id"],
                    "gold": o["gold"],
                    "is_sup12": o["is_sup12"],
                    "orig_pred": b["pred"],
                    "orig_conf": b["conf"],
                    "pch_pred": o["pred"],
                    "pch_conf": o["conf"],
                }
                for b, o in zip(base_rows, other_rows)
                if b["correct"] and (not o["correct"])
            ]
            return {
                "gained": gained,
                "lost": lost,
                "gained_ids": [x["sample_id"] for x in gained],
                "lost_ids": [x["sample_id"] for x in lost],
                "net": len(gained) - len(lost),
            }
        entered = [
            {
                "sample_id": o["sample_id"],
                "orig_pred": b["pred"],
                "orig_sup12_mass": b["sup12_mass"],
                "pch_pred": o["pred"],
                "pch_sup12_mass": o["sup12_mass"],
            }
            for b, o in zip(base_rows, other_rows)
            if (not b["pred_is_sup12"]) and o["pred_is_sup12"]
        ]
        exited = [
            {
                "sample_id": o["sample_id"],
                "orig_pred": b["pred"],
                "orig_sup12_mass": b["sup12_mass"],
                "pch_pred": o["pred"],
                "pch_sup12_mass": o["sup12_mass"],
            }
            for b, o in zip(base_rows, other_rows)
            if b["pred_is_sup12"] and (not o["pred_is_sup12"])
        ]
        return {
            "entered_sup12": entered,
            "exited_sup12": exited,
            "entered_ids": [x["sample_id"] for x in entered],
            "exited_ids": [x["sample_id"] for x in exited],
            "net": len(entered) - len(exited),
        }

    pch_flips = {
        "pos_cal": flip_details(eval_pch["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
        "neg_cal": flip_details(eval_pch["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
    }

    # 7. Reference existing Attempt 1/2 (head-only c0908ffb) + 5 earlier historical runs without re-running them
    prior_ho = json.loads(PRIOR_HO_FINAL_JSON.read_text(encoding="utf-8"))

    git_branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    git_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

    report = {
        "schema_version": "worker_c_final_attempt_review.v1",
        "device_used": device_str,
        "git_branch": git_branch,
        "git_head": git_head,
        "top_level_hashes": actual_hashes,
        "inventories_verified": {
            "archive_files_checked": arch_n,
            "archive_mismatches": arch_mis,
            "sidecar_files_checked": side_n,
            "sidecar_mismatches": side_mis,
            "prep_files_checked": prep_n,
            "prep_mismatches": prep_mis,
        },
        "input_parity": {
            "rec_vs_prep_diffs": rec_vs_prep_diffs,
            "prep_vs_v4_shared_data_diffs": v4_diffs,
        },
        "source_snapshot": {
            "snapshot_vs_run_config_diffs": snap_diffs,
            "snapshot_vs_prep_diffs": prep_src_diffs,
            "snapshot_vs_disk_diffs": disk_diffs,
        },
        "preserved_assets": preserved_assets,
        "freeze_and_delta_verification": freeze_verification,
        "overlap_audit": overlap_audit,
        "fit_metadata": {
            "train_seconds": fit_res["train_seconds"],
            "epoch_stats": fit_res["epoch_stats"],
            "lr": run_cfg["lr"],
            "epochs": run_cfg["epochs"],
            "batch_size": run_cfg["batch_size"],
            "weight_decay": sub_cfg["weight_decay"],
            "seed": run_cfg["seed"],
            "trainable_scope": sub_cfg["trainable_scope"],
            "feature_dropout_eval_mode": sub_cfg["feature_dropout_eval_mode"],
            "teacher_used": sub_cfg["teacher_used"],
            "train_total_examples": prov_man["training_lineage"]["train_total_examples"],
            "fits_started": status_rec["fits_started"],
            "fits_completed": status_rec["fits_completed"],
        },
        "mc_parity_pre_classifier_head": eval_pch["mc_parity"],
        "max_guard_float_diff_vs_recorded": max_guard_float_diff,
        "recomputed_pre_classifier_head_cal_guard": recomputed_guard,
        "orig_fit2_metrics": {
            "cal_guard_metrics": eval_orig["cal_guard_metrics"],
            "train_metrics": eval_orig["train_metrics"],
        },
        "pre_classifier_head_metrics": {
            "cal_guard_metrics": eval_pch["cal_guard_metrics"],
            "train_metrics": eval_pch["train_metrics"],
            "flips_vs_orig_fit2": pch_flips,
        },
        "attempt_1_head_only_reference": {
            "weights_sha256": actual_hashes["ho_weights"],
            "cal_guard": prior_ho["recomputed_head_only_cal_guard"],
            "cal_guard_metrics": prior_ho["head_only_metrics"]["cal_guard_metrics"],
            "train_metrics": prior_ho["head_only_metrics"]["train_metrics"],
            "mc_parity": prior_ho["mc_parity_head_only"],
        },
        "historical_pre_cap_reference": prior_ho["prior_verified_models_summary"],
    }

    out_json = OUT_DIR / "final_attempt_cal_verification.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "worker_c_final_attempt_manifest.v1",
        "reviewer": "Worker C",
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "device_used": device_str,
        "git_branch": git_branch,
        "git_head": git_head,
        "script_sha256": sha256_file(Path(__file__)),
        "final_attempt_cal_verification_sha256": sha256_file(out_json),
        "scope_confirmations": {
            "new_fits": 0,
            "optimizer_steps": 0,
            "backward_passes": 0,
            "calibrators_fitted": 0,
            "paid_llm_calls": 0,
            "holdout_or_ood_inferences": 0,
            "cleanup_executed": False,
            "next_fit_proposals": 0,
        },
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "OK",
        "device": device_str,
        "elapsed_seconds": manifest["elapsed_seconds"],
        "guard_passed": recomputed_guard["passed"],
        "failed_checks": recomputed_guard["failed_checks"],
        "max_guard_float_diff": max_guard_float_diff,
        "mc_parity": eval_pch["mc_parity"],
        "training_stopped": training_cap["training_stopped"],
        "stop_reason": training_cap["stop_reason"],
        "attempts": f"{training_cap['additional_attempts_started']}/{training_cap['additional_attempt_limit']}",
        "pos_cal_flips": {"gained": pch_flips["pos_cal"]["gained_ids"], "lost": pch_flips["pos_cal"]["lost_ids"]},
        "neg_cal_flips": {"entered": pch_flips["neg_cal"]["entered_ids"], "exited": pch_flips["neg_cal"]["exited_ids"]},
    }, indent=2))


if __name__ == "__main__":
    main()

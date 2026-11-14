"""Worker C independent read-only verification and final consolidation for fit2-orig-classifier-head-only-v1.

Strictly read-only: ZERO optimizer steps, ZERO backward passes, ZERO new fits/calibrators,
ZERO paid LLM calls, ZERO holdout/OOD/full eval inference, ZERO file mutations outside OUT_DIR.
"""

from __future__ import annotations

import hashlib
import json
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
from pipeline.training.train_boundary_candidate import _snapshot_frozen_component_hashes
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_FLOAT_TOLERANCE,
    evaluate_cal_guard_report,
)

OUT_DIR = Path(__file__).resolve().parent

ARCH_HO = ROOT / "artifacts/models/candidates/fit2-orig-classifier-head-only-v1"
REC_HO = ROOT / "artifacts/models/candidates/run-records-fit2-orig-classifier-head-only-v1"
PREP_HO = ROOT / "artifacts/models/candidates/run-records-fit2-orig-classifier-head-only-v1-prep"
PREP_V4 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep"

ARCH_ORIG = ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
ARCH_FIT1 = ROOT / "artifacts/models/candidates/reconstructed-closure-fit1-20261113"
SERVING_DIR = ROOT / "artifacts/models/trained/distilbert-supportiq"
ARCH_CTRL = ROOT / "artifacts/models/candidates/fit2-orig-zero-delta-control-v1"
ARCH_2E5 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
ARCH_LR5E6 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1"
ARCH_TKL = ROOT / "artifacts/models/candidates/fit2-orig-teacher-kl-v1"
ARCH_DKL = ROOT / "artifacts/models/candidates/fit2-orig-deterministic-kl-v1"

PRIOR_CTRL_JSON = ROOT / "artifacts/evaluation/fit2_zero_delta_control_review_c_20261114/control_cal_comparison.json"
PRIOR_TKL_JSON = ROOT / "artifacts/evaluation/fit2_teacher_kl_cal_review_c_20261114/teacher_kl_cal_and_probe_comparison.json"
PRIOR_DKL_JSON = ROOT / "artifacts/evaluation/fit2_det_kl_cal_review_c_20261114/det_kl_cal_and_head_feasibility.json"

TRAINING_CAP_PATH = ROOT / ".local/training-cap-20261114.json"
AI_ENV_PATH = ROOT / ".local/ai.env"
TEMPLATE_PPTX_PATH = ROOT / "docs/report.template.pptx"
CODEGRAPH_DIR = ROOT / ".codegraph"

EXPECTED_HASHES = {
    "ho_weights": "c0908ffb9794a4c9450959534c694e64dd1c296a2dc65831334a17e7c5409afb",
    "ho_cal": "09720c1367fcd236d239e91499b1b62be70d447c81137629640d82611a1b1fe8",
    "ho_prov": "962b8c80258e42425fdfdb6f6f47f3b7e31d7e68d2c9e02b85fd5d1b70622eb9",
    "ho_archive_inv": "f7c00a763cd36dbd31307234b97ce2506ebc750deb07eff0e49c032218c9e4fd",
    "ho_cal_guard": "6420a920eb3fcf4012ab4f56001a6a38a9c48014781e3ae57de2c5e68aaee39b",
    "ho_sidecar_inv": "9a7fa92f892282a5a4c52f32a55afd60a4b00d1d10c1e7481fbb501ddd66f5e8",
    "ho_prep_manifest": "44432c82091c823f9df0a23a3c9038ac3fdd7068ff2f2f8229d77b15c4695fc6",
    "ho_prep_inv": "787d0b7c4b3b672775f159f3a0a321494731067bc1f18382cb511bbaadaf6672",
    "frozen_tensors_sha256": "3b8b48f556d4f2f0c99dad938e470d6caa2184650f09f3af7c0bfb164364d31d",
    "orig_weights": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "fit1_weights": "95a940b630f44bf8d11882a26062c857839baa2d80d188f5451d52cecc2158a6",
    "serving_weights": "dc7af8cffb19fe7711ed5a5d0137ffff3d7d1a1f43bad5a35edff8c8de4c1302",
    "ctrl_weights": "904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee",
    "prior_2e5_weights": "dc3e88e713c71fe0e521a1dc5bec5831d9a0a91a83d4c3d1b413d3b1cd68e44d",
    "lr5e6_weights": "b7a285479b853b5bed9ad1c67caaeed1b45107bd78bf8e53e23f6ec4f332feb2",
    "tkl_weights": "3994af2c461cd029f4d03dbec38a75b2bb103a78d8550f4f3a20078b354bca06",
    "dkl_weights": "e63d1ea963e165aaabdd8b619f2e1bf26914fff746bc9f1b7f888c3acf0191f1",
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


def verify_frozen_tensors_and_head_delta(prov_man: Dict[str, Any], run_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Verify exact bit-identity of all 102 frozen param tensors + 1 buffer vs orig_fit2 and quantify head-only delta."""
    orig_model = AutoModelForSequenceClassification.from_pretrained(str(ARCH_ORIG), local_files_only=True)
    ho_model = AutoModelForSequenceClassification.from_pretrained(str(ARCH_HO), local_files_only=True)

    for m in (orig_model, ho_model):
        for name, p in m.named_parameters():
            p.requires_grad_(name.startswith("classifier."))

    orig_snap = _snapshot_frozen_component_hashes(orig_model)
    ho_snap = _snapshot_frozen_component_hashes(ho_model)

    assert orig_snap["all_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert ho_snap["all_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert orig_snap["component_hashes"] == ho_snap["component_hashes"]
    assert orig_snap["frozen_tensor_hashes"] == ho_snap["frozen_tensor_hashes"]
    assert orig_snap["buffer_hashes"] == ho_snap["buffer_hashes"]

    lineage = prov_man["training_lineage"]
    assert lineage["initial_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert lineage["post_fit_frozen_tensors_sha256"] == EXPECTED_HASHES["frozen_tensors_sha256"]
    assert lineage["post_fit_freeze_verified"] is True
    assert lineage["initial_freeze_component_hashes"] == ho_snap["component_hashes"]
    assert lineage["post_fit_freeze_component_hashes"] == ho_snap["component_hashes"]

    orig_params = dict(orig_model.named_parameters())
    ho_params = dict(ho_model.named_parameters())
    orig_buffers = dict(orig_model.named_buffers())
    ho_buffers = dict(ho_model.named_buffers())

    total_params = sum(int(p.numel()) for p in ho_params.values())
    frozen_param_count = sum(int(p.numel()) for p in ho_params.values() if not p.requires_grad)
    trainable_param_count = sum(int(p.numel()) for p in ho_params.values() if p.requires_grad)
    assert len(ho_snap["frozen_tensor_hashes"]) == 102
    assert len(ho_snap["buffer_hashes"]) == 1
    assert frozen_param_count == 66953472
    assert trainable_param_count == 35374
    assert total_params == 66988846

    max_frozen_param_abs_diff = 0.0
    for k in ho_snap["frozen_tensor_hashes"]:
        d = float(torch.max(torch.abs(ho_params[k].detach() - orig_params[k].detach())).item())
        max_frozen_param_abs_diff = max(max_frozen_param_abs_diff, d)

    max_buffer_abs_diff = 0.0
    for k in ho_snap["buffer_hashes"]:
        d = float(torch.max(torch.abs((ho_buffers[k].detach() - orig_buffers[k].detach()).to(torch.float64))).item())
        max_buffer_abs_diff = max(max_buffer_abs_diff, d)

    assert max_frozen_param_abs_diff == 0.0
    assert max_buffer_abs_diff == 0.0

    dw = (ho_params["classifier.weight"].detach() - orig_params["classifier.weight"].detach()).to(torch.float64)
    db = (ho_params["classifier.bias"].detach() - orig_params["classifier.bias"].detach()).to(torch.float64)
    w0 = orig_params["classifier.weight"].detach().to(torch.float64)
    w1 = ho_params["classifier.weight"].detach().to(torch.float64)

    row_l2 = torch.linalg.vector_norm(dw, dim=1)
    top_idx = torch.argsort(row_l2, descending=True)[:8]
    top_shifted_classes = [
        {
            "intent": STANDARD_INTENTS_46[int(i)],
            "weight_row_l2_delta": float(row_l2[int(i)].item()),
            "bias_delta": float(db[int(i)].item()),
            "orig_row_norm": float(torch.linalg.vector_norm(w0[int(i)]).item()),
            "cand_row_norm": float(torch.linalg.vector_norm(w1[int(i)]).item()),
        }
        for i in top_idx
    ]

    return {
        "total_params": total_params,
        "frozen_param_tensors_count": len(ho_snap["frozen_tensor_hashes"]),
        "frozen_params": frozen_param_count,
        "buffer_count": len(ho_snap["buffer_hashes"]),
        "buffer_names": sorted(ho_snap["buffer_hashes"].keys()),
        "trainable_params": trainable_param_count,
        "trainable_names": sorted(k for k, p in ho_params.items() if p.requires_grad),
        "all_frozen_tensors_sha256": ho_snap["all_frozen_tensors_sha256"],
        "component_hashes_count": len(ho_snap["component_hashes"]),
        "component_hashes_match": True,
        "max_frozen_param_abs_diff": max_frozen_param_abs_diff,
        "max_buffer_abs_diff": max_buffer_abs_diff,
        "classifier_weight_l2_delta": float(torch.linalg.norm(dw).item()),
        "classifier_weight_rel_delta": float((torch.linalg.norm(dw) / torch.linalg.norm(w0)).item()),
        "classifier_bias_l2_delta": float(torch.linalg.vector_norm(db).item()),
        "orig_classifier_weight_frob": float(torch.linalg.norm(w0).item()),
        "cand_classifier_weight_frob": float(torch.linalg.norm(w1).item()),
        "top_shifted_classifier_rows": top_shifted_classes,
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

    pos_train_rows = surfaces["boundary_pos_train"]
    pos_train_probs = probs_by_surface["boundary_pos_train"]
    canon_trn_rows = surfaces["canonical_pos_train"]
    canon_trn_probs = probs_by_surface["canonical_pos_train"]

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
        pos_train_probs, pos_train_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set, teacher_probs=_op("boundary_pos_train")
    )
    _, trn_canon_bd, _, _ = summarize_positive_with_breakdown(
        canon_trn_probs, canon_trn_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set, teacher_probs=_op("canonical_pos_train")
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

    add18_by_intent: Dict[str, Dict[str, Any]] = {}
    for intent_name in sorted({str(r["intent"]) for r in surfaces["pos_train_added_18"]}):
        sub_mask = np.array([str(r["intent"]) == intent_name for r in surfaces["pos_train_added_18"]], dtype=bool)
        sub_probs = probs_by_surface["pos_train_added_18"][sub_mask]
        sub_rows = [r for r, f in zip(surfaces["pos_train_added_18"], sub_mask) if f]
        _, sub_bd, _, _ = summarize_positive_with_breakdown(
            sub_probs,
            sub_rows,
            idx_by_label=idx_by_label,
            sup12_indices=sup12_indices,
            sup12_set=sup12_set,
            teacher_probs=(_op("pos_train_added_18")[sub_mask] if _op("pos_train_added_18") is not None else None),
        )
        add18_by_intent[intent_name] = sub_bd

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
        "pos_train_added_18_by_intent": add18_by_intent,
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

    # 1. Verify hashes across head-only artifacts + all preserved checkpoints
    actual_hashes = {
        "ho_weights": sha256_file(ARCH_HO / "model.safetensors"),
        "ho_cal": sha256_file(ARCH_HO / "calibration_manifest.json"),
        "ho_prov": sha256_file(ARCH_HO / "candidate_provenance_manifest.json"),
        "ho_archive_inv": sha256_file(ARCH_HO / "archive_sha_inventory.json"),
        "ho_cal_guard": sha256_file(REC_HO / "cal_guard_report.json"),
        "ho_sidecar_inv": sha256_file(REC_HO / "sidecar_sha_inventory.json"),
        "ho_prep_manifest": sha256_file(PREP_HO / "prep_manifest.json"),
        "ho_prep_inv": sha256_file(PREP_HO / "sidecar_sha_inventory.json"),
        "orig_weights": sha256_file(ARCH_ORIG / "model.safetensors"),
        "fit1_weights": sha256_file(ARCH_FIT1 / "model.safetensors"),
        "serving_weights": sha256_file(SERVING_DIR / "model.safetensors"),
        "ctrl_weights": sha256_file(ARCH_CTRL / "model.safetensors"),
        "prior_2e5_weights": sha256_file(ARCH_2E5 / "model.safetensors"),
        "lr5e6_weights": sha256_file(ARCH_LR5E6 / "model.safetensors"),
        "tkl_weights": sha256_file(ARCH_TKL / "model.safetensors"),
        "dkl_weights": sha256_file(ARCH_DKL / "model.safetensors"),
    }
    bad = {k: (v, EXPECTED_HASHES[k]) for k, v in actual_hashes.items() if v != EXPECTED_HASHES[k]}
    if bad:
        raise RuntimeError(f"Hash mismatches detected: {bad}")

    arch_n, arch_mis = verify_inventory(ARCH_HO, ARCH_HO / "archive_sha_inventory.json", exclude_name="archive_sha_inventory.json")
    side_n, side_mis = verify_inventory(REC_HO, REC_HO / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    prep_n, prep_mis = verify_inventory(PREP_HO, PREP_HO / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    if arch_mis or side_mis or prep_mis:
        raise RuntimeError(f"Inventory mismatches: arch={arch_mis}, side={side_mis}, prep={prep_mis}")

    # 2. Governance, runtime env, and preserved asset checks (strictly read-only)
    training_cap = json.loads(TRAINING_CAP_PATH.read_text(encoding="utf-8"))
    assert training_cap["additional_attempt_limit"] == 2
    assert training_cap["additional_attempts_started"] == 1
    assert training_cap["training_stopped"] is True

    ai_env_kv: Dict[str, str] = {}
    if AI_ENV_PATH.is_file():
        for raw in AI_ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                ai_env_kv[k.strip()] = v.strip()

    preserved_assets = {
        "training_cap": training_cap,
        "training_cap_sha256": sha256_file(TRAINING_CAP_PATH),
        "ai_env_exists": AI_ENV_PATH.is_file(),
        "ai_env_sha256": sha256_file(AI_ENV_PATH) if AI_ENV_PATH.is_file() else None,
        "ai_env_model_dir": ai_env_kv.get("SUPPORTIQ_MODEL_DIR"),
        "ai_env_cal_manifest": ai_env_kv.get("SUPPORTIQ_CALIBRATION_MANIFEST_PATH"),
        "report_template_pptx_exists": TEMPLATE_PPTX_PATH.is_file(),
        "report_template_pptx_bytes": TEMPLATE_PPTX_PATH.stat().st_size if TEMPLATE_PPTX_PATH.is_file() else None,
        "report_template_pptx_sha256": sha256_file(TEMPLATE_PPTX_PATH) if TEMPLATE_PPTX_PATH.is_file() else None,
        "codegraph_dir_exists": CODEGRAPH_DIR.is_dir(),
        "codegraph_files": sorted(p.name for p in CODEGRAPH_DIR.iterdir() if p.is_file()) if CODEGRAPH_DIR.is_dir() else [],
        "artifacts_models_gitkeep_exists": (ROOT / "artifacts/models/.gitkeep").exists(),
    }

    # 3. Input parity, profile config, source snapshot
    rec_in = REC_HO / "inputs"
    prep_ds = PREP_HO / "datasets"
    v4_ds = PREP_V4 / "datasets"
    input_files = sorted(p.name for p in prep_ds.iterdir() if p.is_file())
    rec_vs_prep_diffs = [f for f in input_files if sha256_file(rec_in / f) != sha256_file(prep_ds / f)]
    data_files = [f for f in input_files if f.endswith(".jsonl") or f == "split_manifest.json"]
    v4_diffs = [f for f in data_files if sha256_file(prep_ds / f) != sha256_file(v4_ds / f)]
    assert not rec_vs_prep_diffs and not v4_diffs

    run_cfg = json.loads((REC_HO / "run_config.json").read_text(encoding="utf-8"))
    prep_man = json.loads((PREP_HO / "prep_manifest.json").read_text(encoding="utf-8"))
    fit_res = json.loads((REC_HO / "fit_result.json").read_text(encoding="utf-8"))
    recorded_guard = json.loads((REC_HO / "cal_guard_report.json").read_text(encoding="utf-8"))
    prov_man = json.loads((ARCH_HO / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))

    prof = AUTHORIZED_FIT_PROFILES["option_a_classifier_head_only_v1"]
    cho_cfg = run_cfg["classifier_head_only_config"]
    assert run_cfg["authorized_fit_profile"] == "option_a_classifier_head_only_v1"
    assert abs(float(run_cfg["lr"]) - float(prof["lr"])) < 1e-12
    assert int(run_cfg["epochs"]) == int(prof["epochs"])
    assert int(run_cfg["batch_size"]) == int(prof["batch_size"])
    assert int(run_cfg["seed"]) == int(prof["seed"])
    assert run_cfg["fit_mode"] == prof["fit_mode"]
    assert cho_cfg["trainable_scope"] == "classifier_head_only"
    assert cho_cfg["feature_dropout_eval_mode"] is True
    assert abs(float(cho_cfg["weight_decay"]) - 0.01) < 1e-12
    assert cho_cfg["expected_trainable_param_count"] == 35374
    assert cho_cfg["expected_frozen_param_count"] == 66953472
    assert cho_cfg["teacher_used"] is False
    assert run_cfg["enable_selective_rejector"] is False
    assert float(run_cfg["min_temperature"]) == 1.0
    assert prov_man["base_model"]["unfrozen_transformer_layers"] == 0

    snap_dir = REC_HO / "source_snapshot"
    snap_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(snap_dir / rel) != h.lower()]
    disk_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(ROOT / rel) != h.lower()]
    prep_src_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if prep_man["source_hashes"].get(rel, "").lower() != h.lower()]
    assert not snap_diffs and not disk_diffs and not prep_src_diffs

    # 4. Frozen tensor & head delta verification
    freeze_verification = verify_frozen_tensors_and_head_delta(prov_man, run_cfg)

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

    # 6. Fresh CAL + canonical TRAIN inference for orig_fit2 and head_only + ModelContainer parity
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
    eval_ho = evaluate_model_surfaces(
        ARCH_HO,
        surfaces,
        device_str=device_str,
        orig_probs_by_surface=eval_orig["probs_by_surface"],
        check_mc_parity=True,
    )

    recomputed_guard = evaluate_cal_guard_report(
        eval_ho["cal_guard_metrics"],
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

    def flip_summary(other_rows: Sequence[Dict[str, Any]], base_rows: Sequence[Dict[str, Any]], is_pos: bool) -> Dict[str, Any]:
        if is_pos:
            gained = [o["sample_id"] for b, o in zip(base_rows, other_rows) if (not b["correct"]) and o["correct"]]
            lost = [o["sample_id"] for b, o in zip(base_rows, other_rows) if b["correct"] and (not o["correct"])]
            return {"gained": gained, "lost": lost, "net": len(gained) - len(lost)}
        entered = [o["sample_id"] for b, o in zip(base_rows, other_rows) if (not b["pred_is_sup12"]) and o["pred_is_sup12"]]
        exited = [o["sample_id"] for b, o in zip(base_rows, other_rows) if b["pred_is_sup12"] and (not o["pred_is_sup12"])]
        return {"entered_sup12": entered, "exited_sup12": exited, "net": len(entered) - len(exited)}

    ho_flips = {
        "pos_cal": flip_summary(eval_ho["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
        "neg_cal": flip_summary(eval_ho["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
        "added_18_details": [
            {
                "sample_id": o["sample_id"],
                "gold": o["gold"],
                "orig_pred": b["pred"],
                "orig_conf": b["conf"],
                "ho_pred": o["pred"],
                "ho_conf": o["conf"],
                "ho_correct": o["correct"],
            }
            for b, o in zip(eval_orig["row_preds"]["pos_train_added_18"], eval_ho["row_preds"]["pos_train_added_18"])
        ],
    }

    # 7. Consolidate prior Worker C verified CAL evidence across all prior models
    prior_ctrl = json.loads(PRIOR_CTRL_JSON.read_text(encoding="utf-8"))
    prior_tkl = json.loads(PRIOR_TKL_JSON.read_text(encoding="utf-8"))
    prior_dkl = json.loads(PRIOR_DKL_JSON.read_text(encoding="utf-8"))

    git_branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    git_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

    report = {
        "schema_version": "worker_c_head_only_final_review.v1",
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
            "weight_decay": cho_cfg["weight_decay"],
            "seed": run_cfg["seed"],
            "trainable_scope": cho_cfg["trainable_scope"],
            "feature_dropout_eval_mode": cho_cfg["feature_dropout_eval_mode"],
            "teacher_used": cho_cfg["teacher_used"],
            "train_total_examples": prov_man["training_lineage"]["train_total_examples"],
        },
        "mc_parity_head_only": eval_ho["mc_parity"],
        "max_guard_float_diff_vs_recorded": max_guard_float_diff,
        "recomputed_head_only_cal_guard": recomputed_guard,
        "orig_fit2_metrics": {
            "cal_guard_metrics": eval_orig["cal_guard_metrics"],
            "train_metrics": eval_orig["train_metrics"],
        },
        "head_only_metrics": {
            "cal_guard_metrics": eval_ho["cal_guard_metrics"],
            "train_metrics": eval_ho["train_metrics"],
            "flips_vs_orig_fit2": ho_flips,
        },
        "prior_verified_models_summary": {
            "zero_delta_control": {
                "weights_sha256": actual_hashes["ctrl_weights"],
                "cal_guard": prior_ctrl["recomputed_control_cal_guard"],
                "metrics": prior_ctrl["models"]["zero_delta_control"],
            },
            "prior_2e5": {
                "weights_sha256": actual_hashes["prior_2e5_weights"],
                "metrics": prior_dkl["models"]["prior_2e5"],
            },
            "cand_lr5e6": {
                "weights_sha256": actual_hashes["lr5e6_weights"],
                "metrics": prior_ctrl["models"]["cand_lr5e6"],
            },
            "teacher_kl": {
                "weights_sha256": actual_hashes["tkl_weights"],
                "cal_guard": prior_tkl["recomputed_teacher_kl_cal_guard"],
                "metrics": prior_tkl["models"]["teacher_kl"],
            },
            "deterministic_kl": {
                "weights_sha256": actual_hashes["dkl_weights"],
                "cal_guard": prior_dkl["recomputed_det_kl_cal_guard"],
                "metrics": prior_dkl["models"]["deterministic_kl"],
                "weight_deltas_vs_orig": prior_dkl["weight_deltas_vs_orig"],
            },
        },
    }

    out_json = OUT_DIR / "head_only_cal_verification.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "worker_c_head_only_final_manifest.v1",
        "reviewer": "Worker C",
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "device_used": device_str,
        "git_branch": git_branch,
        "git_head": git_head,
        "script_sha256": sha256_file(Path(__file__)),
        "head_only_cal_verification_sha256": sha256_file(out_json),
        "scope_confirmations": {
            "new_fits": 0,
            "optimizer_steps": 0,
            "backward_passes": 0,
            "calibrators_fitted": 0,
            "paid_llm_calls": 0,
            "holdout_or_ood_inferences": 0,
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
        "mc_parity": eval_ho["mc_parity"],
        "training_stopped": training_cap["training_stopped"],
        "attempts": f"{training_cap['additional_attempts_started']}/{training_cap['additional_attempt_limit']}",
    }, indent=2))


if __name__ == "__main__":
    main()

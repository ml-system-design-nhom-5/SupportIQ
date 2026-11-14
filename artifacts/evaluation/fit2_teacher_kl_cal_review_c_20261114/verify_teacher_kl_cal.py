"""Worker C independent read-only CAL & objective verification for fit2-orig-teacher-kl-v1.

Strictly read-only: verifies lineage/hashes/inputs/source snapshot, reproduces exact 12-check
raw post-T=1.0 CAL guard + ModelContainer parity + 4-way right/wrong decomposition, and executes
in-memory read-only forward/backward gradient probes (ZERO optimizer.step(), ZERO file mutations,
ZERO holdout/OOD/full eval inference).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
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
from pipeline.training.boundary_curriculum_data import apply_realistic_noise
from pipeline.training.train_boundary_candidate import (
    _BoundaryDataset,
    _supcon_loss,
    build_teacher_anchor_mask,
    compute_masked_teacher_kl_loss,
    resolve_neg_repeat,
)
from scripts.run_orig_fit2_return_contrast_prep import (
    AUTHORIZED_FIT_PROFILES,
    CAL_GUARD_FLOAT_TOLERANCE,
    evaluate_cal_guard_report,
)

OUT_DIR = Path(__file__).resolve().parent

ARCH_TKL = ROOT / "artifacts/models/candidates/fit2-orig-teacher-kl-v1"
REC_TKL = ROOT / "artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1"
PREP_TKL = ROOT / "artifacts/models/candidates/run-records-fit2-orig-teacher-kl-v1-prep"
PREP_V4 = ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v4-prep"

ARCH_ORIG = ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
ARCH_CTRL = ROOT / "artifacts/models/candidates/fit2-orig-zero-delta-control-v1"
ARCH_2E5 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
ARCH_LR5E6 = ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-lr5e6-v1"
SERVING_DIR = ROOT / "artifacts/models/trained/distilbert-supportiq"
FIT1_DIR = ROOT / "artifacts/models/candidates/reconstructed-closure-fit1-20261113"

EXPECTED_HASHES = {
    "tkl_weights": "3994af2c461cd029f4d03dbec38a75b2bb103a78d8550f4f3a20078b354bca06",
    "tkl_cal": "4e06df8f2ecd11fb72d9e8163525eafe06ca0feebba87310e808cdfbd7b88db8",
    "tkl_prov": "ceacdb9f00f8f1d3e5a588080cdb747543db0d71446fa4b89b99d0c9ef592bcc",
    "tkl_cal_guard": "34967831ff85a4d8a1da611f3c49cd5bda8d4d916a6428adc2448a4cd2eaeb8e",
    "tkl_prep_manifest": "3234e31bea47402b4d6ef2da1ceb0fe3434e470c707c848dbc538918b2049286",
    "orig_weights": "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa",
    "ctrl_weights": "904188aab6cb45d1150cbd5f0890ee06a1732177d0c7b2c62e43d54a05ffc0ee",
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
            mismatches.append(f"file_set_mismatch: missing={sorted(set(files.keys())-actual_rel)} extra={sorted(actual_rel-set(files.keys()))}")
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
            chunks.append(model(**enc).logits.detach().cpu().numpy().astype(np.float64))
    return np.vstack(chunks)


def kl_p_teacher_student_float64(p_teacher: np.ndarray, p_student: np.ndarray) -> np.ndarray:
    pt = np.clip(p_teacher, 1e-12, 1.0)
    ps = np.clip(p_student, 1e-12, 1.0)
    return np.sum(pt * (np.log(pt) - np.log(ps)), axis=1)


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

    def _op(name: str) -> np.ndarray | None:
        return None if orig_probs_by_surface is None else orig_probs_by_surface[name]

    pos_cal_rows = surfaces["boundary_pos_cal"]
    pos_cal_probs = probs_by_surface["boundary_pos_cal"]
    cal_sup12_mask = np.array([r["intent"] in sup12_set for r in pos_cal_rows], dtype=bool)
    cal_esc34_mask = np.array([r["intent"] in esc34_set for r in pos_cal_rows], dtype=bool)

    pos_train_rows = surfaces["boundary_pos_train"]
    pos_train_probs = probs_by_surface["boundary_pos_train"]
    trn_sup12_mask = np.array([r["intent"] in sup12_set for r in pos_train_rows], dtype=bool)
    trn_esc34_mask = np.array([r["intent"] in esc34_set for r in pos_train_rows], dtype=bool)

    pos_sum, pos_bd, pos_preds, pos_confs = summarize_positive_with_breakdown(
        pos_cal_probs, pos_cal_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set, teacher_probs=_op("boundary_pos_cal")
    )
    sup_sum, sup_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_sup12_mask],
        [r for r, f in zip(pos_cal_rows, cal_sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=None if _op("boundary_pos_cal") is None else _op("boundary_pos_cal")[cal_sup12_mask],
    )
    esc_sum, esc_bd, _, _ = summarize_positive_with_breakdown(
        pos_cal_probs[cal_esc34_mask],
        [r for r, f in zip(pos_cal_rows, cal_esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=None if _op("boundary_pos_cal") is None else _op("boundary_pos_cal")[cal_esc34_mask],
    )
    bit_sum, bit_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["bitext_cal"],
        surfaces["bitext_cal"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("bitext_cal"),
    )
    add18_sum, add18_bd, _, _ = summarize_positive_with_breakdown(
        probs_by_surface["pos_train_added_18"],
        surfaces["pos_train_added_18"],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=_op("pos_train_added_18"),
    )
    trn_pos_sum, trn_pos_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs, pos_train_rows, idx_by_label=idx_by_label, sup12_indices=sup12_indices, sup12_set=sup12_set, teacher_probs=_op("boundary_pos_train")
    )
    _, trn_sup_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs[trn_sup12_mask],
        [r for r, f in zip(pos_train_rows, trn_sup12_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=None if _op("boundary_pos_train") is None else _op("boundary_pos_train")[trn_sup12_mask],
    )
    _, trn_esc_bd, _, _ = summarize_positive_with_breakdown(
        pos_train_probs[trn_esc34_mask],
        [r for r, f in zip(pos_train_rows, trn_esc34_mask) if f],
        idx_by_label=idx_by_label,
        sup12_indices=sup12_indices,
        sup12_set=sup12_set,
        teacher_probs=None if _op("boundary_pos_train") is None else _op("boundary_pos_train")[trn_esc34_mask],
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
        "pos_train_added_18": {k: add18_sum[k] for k in ("count", "correct_count", "accuracy", "mean_max_prob")},
        "boundary_neg_cal": {
            "count": len(surfaces["boundary_neg_cal"]),
            "pred_sup12_count": int(np.sum(neg_cal_pred_sup12_mask)),
            "max_sup12_mass": float(np.max(neg_cal_sup12_mass)),
            "mean_sup12_mass": float(np.mean(neg_cal_sup12_mass)),
            "max_single_sup12_prob": float(np.max(neg_cal_sup12_probs)),
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
        "boundary_pos_train": trn_pos_bd,
        "boundary_pos_train_sup12": trn_sup_bd,
        "boundary_pos_train_esc34": trn_esc_bd,
        "boundary_neg_train": {
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
    }

    return {
        "probs_by_surface": probs_by_surface,
        "weights_sha256": sha256_file(model_dir / "model.safetensors"),
        "calibration_manifest_sha256": sha256_file(model_dir / "calibration_manifest.json"),
        "rejector_enabled": bool(cal_manifest["selective_rejector"]["enabled"]),
        "cal_guard_metrics": cal_guard_metrics,
        "train_metrics": train_metrics,
        "mc_parity": mc_parity,
        "row_preds": row_preds,
    }


def _flat_grad(params: Sequence[torch.nn.Parameter]) -> torch.Tensor:
    return torch.cat([
        (p.grad.detach().reshape(-1) if p.grad is not None else torch.zeros_like(p.detach().reshape(-1)))
        for p in params
    ])


def run_readonly_objective_probes(
    *,
    inputs_dir: Path,
    device_str: str,
) -> Dict[str, Any]:
    """Read-only forward & gradient probes (ZERO optimizer.step())."""
    pos_train = read_jsonl(inputs_dir / "boundary_pos_train.jsonl")
    neg_train = read_jsonl(inputs_dir / "boundary_neg_train.jsonl")
    bitext_clean = read_jsonl(inputs_dir / "bitext_train_clean.jsonl")
    bitext_noisy = read_jsonl(inputs_dir / "bitext_train_noisy.jsonl")
    ext_rows = read_jsonl(inputs_dir / "orig_fit2_return_contrast_extension.jsonl")

    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}
    sup12_indices = [label2id[lbl] for lbl in SUPPORTED_12_INTENTS]
    device = torch.device(device_str)
    sup12_idx_t = torch.tensor(sup12_indices, dtype=torch.long, device=device)
    uniform_target = torch.full((1, len(STANDARD_INTENTS_46)), 1.0 / len(STANDARD_INTENTS_46), device=device)

    train_texts: List[str] = []
    train_labels: List[int] = []
    train_is_neg: List[int] = []
    for r in pos_train:
        rep = 5 if r["intent"] in ESCALATED_34_INTENTS else 4
        for _ in range(rep):
            train_texts.append(r["text"])
            train_labels.append(label2id[r["intent"]])
            train_is_neg.append(0)
    for r in bitext_clean + bitext_noisy:
        train_texts.append(r["text"])
        train_labels.append(label2id[r["intent"]])
        train_is_neg.append(0)
    resolved_neg_reps = [resolve_neg_repeat(r, 12) for r in neg_train]
    neg_rng = random.Random(42 + 99)
    for r, row_rep in zip(neg_train, resolved_neg_reps):
        for rep_i in range(row_rep):
            txt = apply_realistic_noise(r["text"], neg_rng) if (rep_i % 4 == 3) else r["text"]
            train_texts.append(txt)
            train_labels.append(0)
            train_is_neg.append(1)

    anchor_mask, mask_summary = build_teacher_anchor_mask(
        pos_train=pos_train,
        bitext_rows=bitext_clean + bitext_noisy,
        neg_train=neg_train,
        neg_repeat_counts=resolved_neg_reps,
        extension_rows=ext_rows,
    )
    assert len(anchor_mask) == len(train_texts) == 13080
    assert mask_summary["anchor_effective_total"] == 13000
    assert mask_summary["excluded_effective_total"] == 80

    tokenizer = AutoTokenizer.from_pretrained(str(ARCH_ORIG), local_files_only=True)
    enc = tokenizer(train_texts, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
    ds = _BoundaryDataset(enc, train_labels, train_is_neg, teacher_anchor_mask=anchor_mask)

    teacher = AutoModelForSequenceClassification.from_pretrained(str(ARCH_ORIG), local_files_only=True).to(device)
    for p in teacher.parameters():
        p.requires_grad_(False)
    teacher.eval()

    def probe_checkpoint(student_dir: Path, label: str, num_batches: int = 16) -> Dict[str, Any]:
        student = AutoModelForSequenceClassification.from_pretrained(str(student_dir), local_files_only=True).to(device)
        torch.manual_seed(42)
        loader = DataLoader(ds, batch_size=32, shuffle=True, generator=torch.Generator().manual_seed(42))

        eval_kls: List[float] = []
        train_kls: List[float] = []
        pos_losses_train: List[float] = []
        sc_losses_train: List[float] = []
        neg_losses_train: List[float] = []
        teacher_entropies: List[float] = []
        student_eval_entropies: List[float] = []
        student_train_entropies: List[float] = []
        kl_grad_norms: List[float] = []
        base_grad_norms: List[float] = []
        cos_sims: List[float] = []

        params = [p for p in student.parameters() if p.requires_grad]

        for b_idx, batch in enumerate(loader):
            if b_idx >= num_batches:
                break
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            is_neg = batch["is_neg"].to(device)
            t_mask = batch["teacher_anchor_mask"].to(device)
            pos_mask = is_neg == 0
            neg_mask = is_neg == 1

            with torch.no_grad():
                t_logits = teacher(input_ids=input_ids, attention_mask=attention_mask).logits
                t_probs = F.softmax(t_logits, dim=-1)
                t_ent = -(t_probs * torch.log(t_probs.clamp(min=1e-12))).sum(dim=-1)
                teacher_entropies.append(float(t_ent[t_mask > 0].mean().item()))

                student.eval()
                s_eval_logits = student(input_ids=input_ids, attention_mask=attention_mask).logits
                kl_eval, _ = compute_masked_teacher_kl_loss(s_eval_logits, t_logits, t_mask, teacher_temperature=1.0)
                eval_kls.append(float(kl_eval.item()))
                se_probs = F.softmax(s_eval_logits, dim=-1)
                se_ent = -(se_probs * torch.log(se_probs.clamp(min=1e-12))).sum(dim=-1)
                student_eval_entropies.append(float(se_ent[t_mask > 0].mean().item()))

            student.train()
            student.zero_grad(set_to_none=True)
            out = student(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=True)
            s_logits = out.logits
            st_probs = F.softmax(s_logits.detach(), dim=-1)
            st_ent = -(st_probs * torch.log(st_probs.clamp(min=1e-12))).sum(dim=-1)
            student_train_entropies.append(float(st_ent[t_mask > 0].mean().item()))

            l_base = torch.tensor(0.0, device=device)
            if pos_mask.any():
                l_pos = F.cross_entropy(s_logits[pos_mask], labels[pos_mask], label_smoothing=0.03)
                l_base = l_base + l_pos
                pos_losses_train.append(float(l_pos.item()))
            cls_norm = F.normalize(out.hidden_states[-1][:, 0, :], dim=-1)
            sc_targets = torch.where(neg_mask, torch.full_like(labels, -1), labels)
            l_sc = 0.25 * _supcon_loss(cls_norm, sc_targets, temperature=0.12)
            l_base = l_base + l_sc
            sc_losses_train.append(float(l_sc.item()))
            if neg_mask.any():
                neg_logits = s_logits[neg_mask]
                log_probs = F.log_softmax(neg_logits, dim=-1)
                l_kl = F.kl_div(log_probs, uniform_target.expand_as(log_probs), reduction="batchmean")
                sup12_mass = torch.softmax(neg_logits, dim=-1)[:, sup12_idx_t].sum(dim=-1)
                l_ceil = torch.relu(sup12_mass - 0.18).pow(2).mean()
                l_neg = 0.80 * l_kl + 3.0 * l_ceil
                if pos_mask.any():
                    pos_energy_mean = (-torch.logsumexp(s_logits[pos_mask], dim=-1)).mean().detach()
                    neg_energy = -torch.logsumexp(neg_logits, dim=-1)
                    l_neg = l_neg + 0.25 * torch.relu((pos_energy_mean + 2.0) - neg_energy).pow(2).mean()
                l_base = l_base + l_neg
                neg_losses_train.append(float(l_neg.item()))

            l_tkl, _ = compute_masked_teacher_kl_loss(s_logits, t_logits, t_mask, teacher_temperature=1.0)
            train_kls.append(float(l_tkl.item()))

            l_base.backward(retain_graph=True)
            g_base = _flat_grad(params)
            student.zero_grad(set_to_none=True)
            l_tkl.backward()
            g_tkl = _flat_grad(params)

            nb = float(torch.linalg.vector_norm(g_base).item())
            nk = float(torch.linalg.vector_norm(g_tkl).item())
            base_grad_norms.append(nb)
            kl_grad_norms.append(nk)
            if nb > 0.0 and nk > 0.0:
                cos_sims.append(float(F.cosine_similarity(g_base.unsqueeze(0), g_tkl.unsqueeze(0)).item()))

        return {
            "checkpoint": label,
            "batches_probed": num_batches,
            "mean_eval_kl": float(np.mean(eval_kls)),
            "mean_train_dropout_kl": float(np.mean(train_kls)),
            "dropout_kl_share": float(np.mean(train_kls) - np.mean(eval_kls)),
            "mean_l_pos_train": float(np.mean(pos_losses_train)),
            "mean_l_sc_train": float(np.mean(sc_losses_train)),
            "mean_l_neg_train": float(np.mean(neg_losses_train)) if neg_losses_train else 0.0,
            "mean_teacher_entropy_eval": float(np.mean(teacher_entropies)),
            "mean_student_entropy_eval": float(np.mean(student_eval_entropies)),
            "mean_student_entropy_train": float(np.mean(student_train_entropies)),
            "mean_grad_norm_base": float(np.mean(base_grad_norms)),
            "mean_grad_norm_tkl": float(np.mean(kl_grad_norms)),
            "grad_norm_ratio_tkl_over_base": float(np.mean(kl_grad_norms) / np.mean(base_grad_norms)),
            "mean_grad_cosine_base_vs_tkl": float(np.mean(cos_sims)) if cos_sims else None,
        }

    return {
        "anchor_mask_summary": mask_summary,
        "step0_orig_fit2_probe": probe_checkpoint(ARCH_ORIG, "orig_fit2_step0"),
        "final_teacher_kl_probe": probe_checkpoint(ARCH_TKL, "fit2_orig_teacher_kl_v1"),
    }


def main() -> None:
    t0 = time.perf_counter()

    # 1. Verify top-level hashes and inventories (no artifact mutation)
    actual_top = {
        "tkl_weights": sha256_file(ARCH_TKL / "model.safetensors"),
        "tkl_cal": sha256_file(ARCH_TKL / "calibration_manifest.json"),
        "tkl_prov": sha256_file(ARCH_TKL / "candidate_provenance_manifest.json"),
        "tkl_cal_guard": sha256_file(REC_TKL / "cal_guard_report.json"),
        "tkl_prep_manifest": sha256_file(PREP_TKL / "prep_manifest.json"),
        "orig_weights": sha256_file(ARCH_ORIG / "model.safetensors"),
        "ctrl_weights": sha256_file(ARCH_CTRL / "model.safetensors"),
        "prior_2e5_weights": sha256_file(ARCH_2E5 / "model.safetensors"),
        "lr5e6_weights": sha256_file(ARCH_LR5E6 / "model.safetensors"),
        "serving_weights": sha256_file(SERVING_DIR / "model.safetensors"),
        "fit1_weights": sha256_file(FIT1_DIR / "model.safetensors"),
    }
    bad_hashes = {k: (v, EXPECTED_HASHES[k]) for k, v in actual_top.items() if v != EXPECTED_HASHES[k]}
    if bad_hashes:
        raise RuntimeError(f"Hash mismatch: {bad_hashes}")

    arch_n, arch_mis = verify_inventory(ARCH_TKL, ARCH_TKL / "archive_sha_inventory.json", exclude_name="archive_sha_inventory.json")
    side_n, side_mis = verify_inventory(REC_TKL, REC_TKL / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    prep_n, prep_mis = verify_inventory(PREP_TKL, PREP_TKL / "sidecar_sha_inventory.json", exclude_name="sidecar_sha_inventory.json")
    if arch_mis or side_mis or prep_mis:
        raise RuntimeError(f"Inventory mismatches: arch={arch_mis}, side={side_mis}, prep={prep_mis}")

    # 2. Verify input parity (records/inputs vs prep/datasets vs prep_v4/datasets) + source snapshot
    rec_in = REC_TKL / "inputs"
    prep_ds = PREP_TKL / "datasets"
    v4_ds = PREP_V4 / "datasets"
    input_files = sorted(p.name for p in prep_ds.iterdir() if p.is_file())
    rec_vs_prep_diffs = [f for f in input_files if sha256_file(rec_in / f) != sha256_file(prep_ds / f)]
    # Compare non-manifest shared data JSONLs vs v4 prep
    data_files = [f for f in input_files if f.endswith(".jsonl") or f == "split_manifest.json"]
    v4_diffs = [f for f in data_files if sha256_file(prep_ds / f) != sha256_file(v4_ds / f)]
    assert not rec_vs_prep_diffs and not v4_diffs, f"Input parity failed: {rec_vs_prep_diffs}, {v4_diffs}"

    run_cfg = json.loads((REC_TKL / "run_config.json").read_text(encoding="utf-8"))
    prep_man = json.loads((PREP_TKL / "prep_manifest.json").read_text(encoding="utf-8"))
    fit_res = json.loads((REC_TKL / "fit_result.json").read_text(encoding="utf-8"))
    recorded_guard = json.loads((REC_TKL / "cal_guard_report.json").read_text(encoding="utf-8"))
    prov_man = json.loads((ARCH_TKL / "candidate_provenance_manifest.json").read_text(encoding="utf-8"))

    # Verify coefficient propagation vs AUTHORIZED_FIT_PROFILES["option_a_teacher_kl"]
    prof = AUTHORIZED_FIT_PROFILES["option_a_teacher_kl"]
    assert run_cfg["authorized_fit_profile"] == "option_a_teacher_kl"
    assert abs(float(run_cfg["lr"]) - float(prof["lr"])) < 1e-12
    assert int(run_cfg["epochs"]) == int(prof["epochs"])
    assert int(run_cfg["batch_size"]) == int(prof["batch_size"])
    assert int(run_cfg["seed"]) == int(prof["seed"])
    assert run_cfg["fit_mode"] == prof["fit_mode"]
    assert run_cfg["enable_selective_rejector"] is False
    assert float(run_cfg["min_temperature"]) == 1.0
    assert abs(float(run_cfg["teacher_anchor_config"]["teacher_kl_weight"]) - 1.0) < 1e-12
    assert abs(float(run_cfg["teacher_anchor_config"]["teacher_temperature"]) - 1.0) < 1e-12
    assert run_cfg["teacher_anchor_config"]["teacher_weights_sha256"] == EXPECTED_HASHES["orig_weights"]
    assert prov_man["training_lineage"]["teacher_kl_weight"] == 1.0
    assert prov_man["training_lineage"]["teacher_temperature"] == 1.0
    assert fit_res["teacher_kl"]["teacher_anchor_summary"]["anchor_effective_total"] == 13000
    assert fit_res["teacher_kl"]["teacher_anchor_summary"]["excluded_effective_total"] == 80

    # Check source_snapshot vs run_config, prep_manifest, and disk
    snap_dir = REC_TKL / "source_snapshot"
    snap_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(snap_dir / rel) != h.lower()]
    disk_vs_snap_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if sha256_file(ROOT / rel) != h.lower()]
    prep_src_diffs = [rel for rel, h in run_cfg["source_hashes"].items() if prep_man["source_hashes"].get(rel, "").lower() != h.lower()]
    assert not snap_diffs and not prep_src_diffs, f"Source snapshot mismatch: {snap_diffs}, {prep_src_diffs}"

    # 3. Load locked CAL + canonical TRAIN surfaces + historical overlap audit
    pos_train = read_jsonl(rec_in / "boundary_pos_train.jsonl")
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

    # 4. Evaluate Original Fit2, Zero-Delta Control, Unanchored 2e-5, and Teacher-KL on CAL & TRAIN
    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    surfaces = {
        "boundary_pos_cal": pos_cal,
        "boundary_neg_cal": neg_cal,
        "bitext_cal": bitext_cal,
        "boundary_pos_train": pos_train,
        "boundary_neg_train": neg_train,
        "pos_train_added_18": added_18,
    }
    eval_orig = evaluate_model_surfaces(ARCH_ORIG, surfaces, device_str=device_str, orig_probs_by_surface=None, check_mc_parity=False)
    orig_probs = eval_orig["probs_by_surface"]
    eval_ctrl = evaluate_model_surfaces(ARCH_CTRL, surfaces, device_str=device_str, orig_probs_by_surface=orig_probs, check_mc_parity=False)
    eval_2e5 = evaluate_model_surfaces(ARCH_2E5, surfaces, device_str=device_str, orig_probs_by_surface=orig_probs, check_mc_parity=False)
    eval_tkl = evaluate_model_surfaces(ARCH_TKL, surfaces, device_str=device_str, orig_probs_by_surface=orig_probs, check_mc_parity=True)

    # 5. Reproduce exact 12-check CAL guard on Teacher-KL vs Original Fit2
    recomputed_guard = evaluate_cal_guard_report(
        eval_tkl["cal_guard_metrics"],
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

    # 6. Row-level flips vs Original Fit2
    def flip_summary(other_rows: Sequence[Dict[str, Any]], base_rows: Sequence[Dict[str, Any]], is_pos: bool) -> Dict[str, Any]:
        if is_pos:
            gained = [o["sample_id"] for b, o in zip(base_rows, other_rows) if (not b["correct"]) and o["correct"]]
            lost = [o["sample_id"] for b, o in zip(base_rows, other_rows) if b["correct"] and (not o["correct"])]
            return {"gained": gained, "lost": lost, "net": len(gained) - len(lost)}
        entered = [o["sample_id"] for b, o in zip(base_rows, other_rows) if (not b["pred_is_sup12"]) and o["pred_is_sup12"]]
        exited = [o["sample_id"] for b, o in zip(base_rows, other_rows) if b["pred_is_sup12"] and (not o["pred_is_sup12"])]
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
        "teacher_kl": {
            "pos_cal": flip_summary(eval_tkl["row_preds"]["boundary_pos_cal"], eval_orig["row_preds"]["boundary_pos_cal"], True),
            "neg_cal": flip_summary(eval_tkl["row_preds"]["boundary_neg_cal"], eval_orig["row_preds"]["boundary_neg_cal"], False),
        },
    }

    # 7. Read-only in-memory gradient & dropout probes (ZERO optimizer steps)
    objective_probes = run_readonly_objective_probes(inputs_dir=rec_in, device_str=device_str)

    git_branch = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    git_head = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()

    comparison = {
        "schema_version": "worker_c_teacher_kl_review.v1",
        "device_used": device_str,
        "git_branch": git_branch,
        "git_head": git_head,
        "top_level_hashes": actual_top,
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
            "snapshot_vs_disk_diffs": disk_vs_snap_diffs,
        },
        "overlap_audit": overlap_audit,
        "mc_parity_teacher_kl": eval_tkl["mc_parity"],
        "max_guard_float_diff_vs_recorded": max_guard_float_diff,
        "recomputed_teacher_kl_cal_guard": recomputed_guard,
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
                ("teacher_kl", eval_tkl),
            ]
        },
        "flips_vs_orig_fit2": flips,
        "objective_probes": objective_probes,
    }
    comp_path = OUT_DIR / "teacher_kl_cal_and_probe_comparison.json"
    comp_path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "worker_c_review_manifest.v1",
        "task_id": "task_9c485423b6d9",
        "dispatch_id": "ctx_e9086816936c",
        "git_branch": git_branch,
        "git_head": git_head,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
        "outputs": {
            "teacher_kl_cal_and_probe_comparison.json": sha256_file(comp_path),
            "verify_teacher_kl_cal.py": sha256_file(Path(__file__)),
        },
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "device": device_str,
                "max_guard_diff": max_guard_float_diff,
                "mc_parity": eval_tkl["mc_parity"],
                "step0_probe": objective_probes["step0_orig_fit2_probe"],
                "final_probe": objective_probes["final_teacher_kl_probe"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

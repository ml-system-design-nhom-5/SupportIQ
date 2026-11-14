"""Read-only diagnostic analysis for fit2-orig-ret-channel-fit-v1 vs Original Fit2.

Strictly zero training fits, zero optimizer/calibrator execution, zero holdout tuning:
1. Computes exact effective training exposure and negative-batch dilution on locked v3-prep splits.
2. Measures logit/probability/energy/entropy/margin distributions on locked TRAIN & CAL splits.
3. Summarizes paired aggregate confidence shifts across Worker C's frozen prediction records.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from apps.core_backend.intent.routing import ESCALATED_34_INTENTS, STANDARD_INTENTS_46, SUPPORTED_12_INTENTS
from pipeline.training.train_boundary_candidate import resolve_neg_repeat

REPO_ROOT = Path(__file__).resolve().parents[3]
ORIG_FIT2_DIR = REPO_ROOT / "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
CAND_FIT_V1_DIR = REPO_ROOT / "artifacts/models/candidates/fit2-orig-ret-channel-fit-v1"
V3_PREP_DS_DIR = REPO_ROOT / "artifacts/models/candidates/run-records-fit2-orig-ret-channel-v3-prep/datasets"
STAGE2_REF_DIR = REPO_ROOT / "artifacts/models/candidates/run-records-faithful-fit2-20261113/stage2_inputs"
EVAL_C_DIR = REPO_ROOT / "artifacts/evaluation/fit2_orig_ret_channel_fit_v1_independent_c_20261114"
OUT_PATH = Path(__file__).resolve().parent / "diagnosis_summary.json"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@torch.no_grad()
def _forward_metrics(
    model_dir: Path,
    splits: Dict[str, List[Dict[str, Any]]],
    *,
    device: torch.device,
    batch_size: int = 128,
) -> Dict[str, Any]:
    tok = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device)
    model.eval()
    id2label = {int(k): v for k, v in model.config.id2label.items()}
    label2id = {v: k for k, v in id2label.items()}
    sup12_idx = torch.tensor([label2id[x] for x in SUPPORTED_12_INTENTS], dtype=torch.long, device=device)

    results: Dict[str, Any] = {}
    raw_cache: Dict[str, Tuple[np.ndarray, List[str]]] = {}

    for name, rows in splits.items():
        texts = [r["text"] for r in rows]
        intents = [str(r["intent"]) for r in rows]
        logits_chunks: List[np.ndarray] = []
        max_probs: List[float] = []
        margins: List[float] = []
        entropies: List[float] = []
        max_logits: List[float] = []
        logit_l2: List[float] = []
        energies: List[float] = []
        sup12_masses: List[float] = []
        preds: List[str] = []

        for i in range(0, len(texts), batch_size):
            enc = tok(
                texts[i : i + batch_size],
                max_length=64,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            ).to(device)
            logits = model(**enc).logits
            probs = F.softmax(logits, dim=-1)
            log_probs = F.log_softmax(logits, dim=-1)
            ent = -(probs * log_probs).sum(dim=-1)
            top2_vals, top2_idx = torch.topk(probs, k=2, dim=-1)
            energy = -torch.logsumexp(logits, dim=-1)
            sup12_mass = probs[:, sup12_idx].sum(dim=-1)

            logits_np = logits.cpu().numpy()
            logits_chunks.append(logits_np)
            max_probs.extend(top2_vals[:, 0].cpu().tolist())
            margins.extend((top2_vals[:, 0] - top2_vals[:, 1]).cpu().tolist())
            entropies.extend(ent.cpu().tolist())
            max_logits.extend(logits.max(dim=-1).values.cpu().tolist())
            logit_l2.extend(torch.linalg.vector_norm(logits, dim=-1).cpu().tolist())
            energies.extend(energy.cpu().tolist())
            sup12_masses.extend(sup12_mass.cpu().tolist())
            preds.extend(id2label[int(idx)] for idx in top2_idx[:, 0].cpu().tolist())

        all_logits = np.concatenate(logits_chunks, axis=0) if logits_chunks else np.empty((0, 46), dtype=np.float32)
        raw_cache[name] = (all_logits, intents)

        mp = np.array(max_probs, dtype=np.float64)
        mg = np.array(margins, dtype=np.float64)
        en = np.array(entropies, dtype=np.float64)
        ml = np.array(max_logits, dtype=np.float64)
        ll2 = np.array(logit_l2, dtype=np.float64)
        eg = np.array(energies, dtype=np.float64)
        s12 = np.array(sup12_masses, dtype=np.float64)
        acc = float(np.mean([p == g for p, g in zip(preds, intents)])) if intents else None
        pred_sup12_rate = float(np.mean([p in SUPPORTED_12_INTENTS for p in preds])) if preds else None
        results[name] = {
            "n": len(rows),
            "acc": round(acc, 6) if acc is not None else None,
            "pred_sup12_rate": round(pred_sup12_rate, 6) if pred_sup12_rate is not None else None,
            "mean_max_prob": round(float(mp.mean()), 6),
            "median_max_prob": round(float(np.median(mp)), 6),
            "p90_max_prob": round(float(np.percentile(mp, 90)), 6),
            "frac_ge_070": round(float((mp >= 0.70).mean()), 6),
            "frac_ge_080": round(float((mp >= 0.80).mean()), 6),
            "frac_ge_085": round(float((mp >= 0.85).mean()), 6),
            "mean_margin": round(float(mg.mean()), 6),
            "mean_entropy": round(float(en.mean()), 6),
            "mean_max_logit": round(float(ml.mean()), 6),
            "mean_logit_l2": round(float(ll2.mean()), 6),
            "mean_energy": round(float(eg.mean()), 6),
            "mean_sup12_mass": round(float(s12.mean()), 6),
            "max_sup12_mass": round(float(s12.max()), 6),
        }

    # Analyze T scaling sweep on CAL (positive CAL NLL vs boundary_neg_cal sup12_mass / max_prob).
    pos_cal_logits = np.concatenate(
        [raw_cache["boundary_pos_cal"][0], raw_cache["bitext_cal"][0]],
        axis=0,
    )
    pos_cal_y = np.array(
        [label2id[y] for y in (raw_cache["boundary_pos_cal"][1] + raw_cache["bitext_cal"][1])],
        dtype=np.int64,
    )
    neg_cal_logits = raw_cache["boundary_neg_cal"][0]
    sup12_np = sup12_idx.cpu().numpy()

    t_sweep = []
    logits_t = torch.tensor(pos_cal_logits, dtype=torch.float32)
    labels_t = torch.tensor(pos_cal_y, dtype=torch.long)
    neg_t = torch.tensor(neg_cal_logits, dtype=torch.float32)
    for t_val in (1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.35, 1.5):
        pos_nll = float(F.cross_entropy(logits_t / t_val, labels_t).item())
        pos_probs = F.softmax(logits_t / t_val, dim=-1).numpy()
        neg_probs = F.softmax(neg_t / t_val, dim=-1).numpy()
        neg_s12 = neg_probs[:, sup12_np].sum(axis=1)
        neg_mp = neg_probs.max(axis=1)
        neg_ent = -(neg_probs * np.log(np.clip(neg_probs, 1e-12, 1.0))).sum(axis=1)
        t_sweep.append(
            {
                "T": t_val,
                "cal_pos_nll": round(pos_nll, 6),
                "cal_pos_mean_max_prob": round(float(pos_probs.max(axis=1).mean()), 6),
                "neg_cal_mean_sup12_mass": round(float(neg_s12.mean()), 6),
                "neg_cal_max_sup12_mass": round(float(neg_s12.max()), 6),
                "neg_cal_mean_max_prob": round(float(neg_mp.mean()), 6),
                "neg_cal_mean_entropy": round(float(neg_ent.mean()), 6),
            }
        )

    return {"splits": results, "cal_temperature_sweep": t_sweep}


def _exposure_breakdown(ds_dir: Path) -> Dict[str, Any]:
    pos_train = _read_jsonl(ds_dir / "boundary_pos_train.jsonl")
    neg_train = _read_jsonl(ds_dir / "boundary_neg_train.jsonl")
    bitext_clean = _read_jsonl(ds_dir / "bitext_train_clean.jsonl")
    bitext_noisy = _read_jsonl(ds_dir / "bitext_train_noisy.jsonl")

    pos_dom_eff = sum(5 if r["intent"] in ESCALATED_34_INTENTS else 4 for r in pos_train)
    bitext_eff = len(bitext_clean) + len(bitext_noisy)
    neg_eff = sum(resolve_neg_repeat(r, 12) for r in neg_train)
    total_eff = pos_dom_eff + bitext_eff + neg_eff
    batches_per_epoch = math.ceil(total_eff / 32)
    return {
        "boundary_pos_train_rows": len(pos_train),
        "boundary_pos_train_eff": pos_dom_eff,
        "bitext_clean_rows": len(bitext_clean),
        "bitext_noisy_rows": len(bitext_noisy),
        "boundary_neg_train_rows": len(neg_train),
        "boundary_neg_train_eff": neg_eff,
        "total_eff_per_epoch": total_eff,
        "batches_per_epoch_bs32": batches_per_epoch,
        "neg_fraction_of_examples": round(neg_eff / total_eff, 6),
        "expected_neg_per_32_batch": round(32 * neg_eff / total_eff, 4),
    }


def _summarize_c_predictions() -> Dict[str, Any]:
    orig_rows = _read_jsonl(EVAL_C_DIR / "predictions_orig_fit2.jsonl")
    cand_rows = _read_jsonl(EVAL_C_DIR / "predictions_cand_fit_v1.jsonl")
    orig_by_key = {(r["suite"], r["id"]): r for r in orig_rows}
    cand_by_key = {(r["suite"], r["id"]): r for r in cand_rows}

    def _bucket(row: Dict[str, Any]) -> str:
        gold = row.get("gold")
        if gold in SUPPORTED_12_INTENTS:
            return "supported_12"
        if gold in ESCALATED_34_INTENTS:
            return "escalated_34"
        return "ood_or_negative"

    by_bucket: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = defaultdict(list)
    by_suite: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = defaultdict(list)
    for k, o in orig_by_key.items():
        c = cand_by_key[k]
        # Exclude bitext6690 only from cross-suite bucket average or summarize both? Keep bitext separate!
        suite = o["suite"]
        by_suite[f"{suite}::{_bucket(o)}"].append((o, c))
        if suite != "bitext6690":
            by_bucket[f"non_bitext::{_bucket(o)}"].append((o, c))
        else:
            by_bucket[f"bitext6690::{_bucket(o)}"].append((o, c))

    def _stats(pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> Dict[str, Any]:
        oc = np.array([o["raw_conf"] for o, _ in pairs], dtype=np.float64)
        cc = np.array([c["raw_conf"] for _, c in pairs], dtype=np.float64)
        om = np.array([o["raw_margin"] for o, _ in pairs], dtype=np.float64)
        cm = np.array([c["raw_margin"] for _, c in pairs], dtype=np.float64)
        diff = cc - oc
        pred_sup_o = sum(1 for o, _ in pairs if o["raw_intent"] in SUPPORTED_12_INTENTS)
        pred_sup_c = sum(1 for _, c in pairs if c["raw_intent"] in SUPPORTED_12_INTENTS)
        draft_o = sum(1 for o, _ in pairs if o["runner_action"] == "retrieve_draft")
        draft_c = sum(1 for _, c in pairs if c["runner_action"] == "retrieve_draft")
        raw_draft_o = sum(1 for o, _ in pairs if o["raw_post_action"] == "retrieve_draft")
        raw_draft_c = sum(1 for _, c in pairs if c["raw_post_action"] == "retrieve_draft")
        return {
            "n": len(pairs),
            "orig_mean_conf": round(float(oc.mean()), 6),
            "cand_mean_conf": round(float(cc.mean()), 6),
            "mean_conf_delta": round(float(diff.mean()), 6),
            "median_conf_delta": round(float(np.median(diff)), 6),
            "frac_conf_increased": round(float((diff > 0).mean()), 6),
            "orig_mean_margin": round(float(om.mean()), 6),
            "cand_mean_margin": round(float(cm.mean()), 6),
            "orig_ge_070": round(float((oc >= 0.70).mean()), 6),
            "cand_ge_070": round(float((cc >= 0.70).mean()), 6),
            "orig_ge_080": round(float((oc >= 0.80).mean()), 6),
            "cand_ge_080": round(float((cc >= 0.80).mean()), 6),
            "pred_sup12_count_orig": pred_sup_o,
            "pred_sup12_count_cand": pred_sup_c,
            "raw_post_draft_orig": raw_draft_o,
            "raw_post_draft_cand": raw_draft_c,
            "runner_draft_orig": draft_o,
            "runner_draft_cand": draft_c,
        }

    return {
        "by_bucket": {k: _stats(v) for k, v in sorted(by_bucket.items())},
        "by_suite_bucket": {k: _stats(v) for k, v in sorted(by_suite.items())},
    }


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pos_train = _read_jsonl(V3_PREP_DS_DIR / "boundary_pos_train.jsonl")
    pos_cal = _read_jsonl(V3_PREP_DS_DIR / "boundary_pos_calibration.jsonl")
    bitext_cal = _read_jsonl(V3_PREP_DS_DIR / "bitext_cal.jsonl")

    splits = {
        "pos_train_baseline_181": [r for r in pos_train if not str(r.get("sample_id", "")).startswith("orig_ret_ch_")],
        "pos_train_added_18": [r for r in pos_train if str(r.get("sample_id", "")).startswith("orig_ret_ch_")],
        "neg_train_99": _read_jsonl(V3_PREP_DS_DIR / "boundary_neg_train.jsonl"),
        "bitext_train_clean": _read_jsonl(V3_PREP_DS_DIR / "bitext_train_clean.jsonl"),
        "bitext_train_noisy": _read_jsonl(V3_PREP_DS_DIR / "bitext_train_noisy.jsonl"),
        "boundary_pos_cal": pos_cal,
        "boundary_pos_cal_sup12": [r for r in pos_cal if r["intent"] in SUPPORTED_12_INTENTS],
        "boundary_pos_cal_esc34": [r for r in pos_cal if r["intent"] in ESCALATED_34_INTENTS],
        "bitext_cal": bitext_cal,
        "bitext_cal_sup12": [r for r in bitext_cal if r["intent"] in SUPPORTED_12_INTENTS],
        "bitext_cal_esc34": [r for r in bitext_cal if r["intent"] in ESCALATED_34_INTENTS],
        "boundary_neg_cal": _read_jsonl(V3_PREP_DS_DIR / "boundary_neg_calibration.jsonl"),
    }

    summary = {
        "exposure": {
            "baseline_stage2": _exposure_breakdown(STAGE2_REF_DIR),
            "v3_prep": _exposure_breakdown(V3_PREP_DS_DIR),
        },
        "orig_fit2_train_cal": _forward_metrics(ORIG_FIT2_DIR, splits, device=device),
        "cand_fit_v1_train_cal": _forward_metrics(CAND_FIT_V1_DIR, splits, device=device),
        "worker_c_paired_aggregate_shifts": _summarize_c_predictions(),
    }
    OUT_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE_DIAGNOSIS_SUMMARY: {OUT_PATH}")


if __name__ == "__main__":
    main()

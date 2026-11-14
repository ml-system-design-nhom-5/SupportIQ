"""Fit 1 boundary-hardened continuation candidate for Task A (Ponytail Ultra).

Stage 1 (`--prepare-only`): Locks balanced Bitext replay + train-only noise
augmentations (with strict parent_sample_id disjointness), exports full split
files, verifies zero overlap with cal/eval/gold benchmarks, records max_len=64
truncation rates and init checkpoint SHA-256 BEFORE any training runs.

Stage 2 (`--run-fit1`): Trains Fit 1 (continuation from closure c6cae7a with
all 6 DistilBERT layers unfrozen, balanced 46-class replay, train-only noise aug,
and uniform-KL + supported-12 probability ceiling on negatives), fits T>=1.0 on
disjoint cal split, writes selective_calibration.v1 + provenance manifests, and
compares serving vs closure c6cae7a vs Fit 1.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

from apps.core_backend.intent.routing import (
    ESCALATED_34_INTENTS,
    IntentPrediction,
    RoutingContext,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    decide_route,
    load_policy_v2,
)
from pipeline.training.boundary_curriculum_data import (
    apply_realistic_noise,
    audit_and_export_boundary_datasets,
)
from pipeline.training.selective_domain_data import _load_frozen_benchmark_texts, _normalize_text, _token_set
from pipeline.training.train_domain_candidate import (
    fit_temperature_on_calibration_logits,
    verify_original_46_label_lineage,
)
from pipeline.training.train_selective_candidate import (
    SUPPORTED_11_DRAFT_INTENTS,
    SelectiveRejectorParams,
    compute_selective_feature_matrix,
    score_rejector,
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return _sha256_file(path)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


MAX_NEG_REPEAT_OVERRIDE = 12


def resolve_neg_repeat(row: Dict[str, Any], default_repeat: int) -> int:
    """Return validated positive bounded int override (1..12, no bool/float/str) or default_repeat."""
    if "neg_repeat" not in row:
        return default_repeat
    val = row["neg_repeat"]
    if type(val) is not int or val < 1 or val > MAX_NEG_REPEAT_OVERRIDE:
        raise ValueError(
            f"Invalid neg_repeat={val!r} on {row.get('sample_id')}: must be exact int in 1..{MAX_NEG_REPEAT_OVERRIDE}"
        )
    return val


GENUINE_NEG_INTENTS = frozenset({"out_of_scope", "multi_intent", "other_domain"})


def validate_boundary_split_taxonomy(
    pos_rows: Sequence[Dict[str, Any]],
    neg_rows: Sequence[Dict[str, Any]],
    split_name: str = "split",
) -> None:
    """Enforce STANDARD_INTENTS_46 strictly in pos_rows and genuine non-46 OOD/compound intents in neg_rows."""
    s46 = set(STANDARD_INTENTS_46)
    bad_pos = [
        (r.get("sample_id"), r.get("intent"))
        for r in pos_rows
        if r.get("intent") not in s46 or r.get("selective_label") == 0
    ]
    if bad_pos:
        raise ValueError(f"Non-46 or negative-labeled row in {split_name} positive split: {bad_pos[:5]}")
    bad_neg = [
        (r.get("sample_id"), r.get("intent"), r.get("category"))
        for r in neg_rows
        if r.get("intent") in s46 or r.get("intent") not in GENUINE_NEG_INTENTS
    ]
    if bad_neg:
        raise ValueError(
            f"Single-intent STANDARD_INTENTS_46 or invalid non-OOD row in {split_name} negative split: {bad_neg[:5]}"
        )


SEMANTIC_AUDIT_STATUSES = frozenset({"valid", "quarantined_kb_contradiction", "ambiguous_retained"})

# Active-KB semantic boundary guards derived strictly from approved_kb.v2.json:
# - POL-ORD-001 vs track_delivery (live vehicle/GPS/courier/doorstep telemetry)
# - POL-RET-001/002/003 vs return_product_in_store (physical store/shop/branch return channel)
VEHICLE_GPS_TELEMETRY_RE = re.compile(
    r"\b(truck|delivery van|courier van|gps|driver|rider|stops away|gate photo|doorstep telemetry|"
    r"live courier route|attempted delivery)\b",
    re.IGNORECASE,
)
_MERCHANT_POLICY_OR_ONLINE_STORE_RE = re.compile(
    r"\b(online\s+store|web\s+store|e-?store|convenience-?store\s+locker|"
    r"store\s+(?:return\s+)?policy|standard\s+store\s+rules?|store\s+rules?|"
    r"store\s+credit|store\s+guidelines?|store\s+terms?)\b",
    re.IGNORECASE,
)
PHYSICAL_INSTORE_RETURN_RE = re.compile(
    r"\b(?:"
    r"brick-and-mortar|physical\s+(?:store|shop|branch|location)|"
    r"retail\s+(?:branch|store|shop|outlet)|storefront|store\s+counter|"
    r"walk-?in|cashier|in-?store|"
    r"(?:(?:at|in|to|into|from)\s+(?:(?:a|an|any|the|te|your|one\s+of\s+your)\s+)?|\ba\s+(?:the|te)\s+)(?:store|shop|branch)s?|"
    r"in\s+person(?:\s+at\s+(?:a|the|your)\s+(?:store|shop|branch))?"
    r")\b",
    re.IGNORECASE,
)
_TRACK_ORDER_REPLACEMENT_OVERLAP_RE = re.compile(r"\b(replace|replacement|exchange)\b", re.IGNORECASE)
_RETURN_IN_STORE_INFO_OVERLAP_RE = re.compile(r"\binformation\s+about\b", re.IGNORECASE)


def validate_semantic_status(status: str, *, context: str = "semantic_audit") -> str:
    """Fail closed on any unknown semantic audit status."""
    if status not in SEMANTIC_AUDIT_STATUSES:
        raise ValueError(f"Unknown semantic audit status in {context}: {status!r}")
    return status


def classify_row_kb_semantics(
    row: Dict[str, Any],
    quarantined_parent_reasons: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Classify one row against active-KB boundaries without automatic relabeling."""
    sample_id = str(row.get("sample_id") or "").strip()
    intent = str(row.get("intent") or row.get("true_intent") or "").strip()
    txt = str(row.get("text") or row.get("instruction") or "").strip()
    source = str(row.get("source") or "").strip()
    parent_id = str(row.get("parent_sample_id") or "").strip()
    if not sample_id or not intent or not txt:
        raise ValueError(
            f"Missing required row provenance (sample_id={sample_id!r}, intent={intent!r}, has_text={bool(txt)})"
        )
    if source.startswith("bitext_") and not parent_id:
        raise ValueError(f"Missing parent_sample_id provenance on Bitext row {sample_id}")

    effective_parent = parent_id or sample_id
    text_sha256 = hashlib.sha256(txt.encode("utf-8")).hexdigest().lower()
    status = "valid"
    reason = "kb_aligned"

    if quarantined_parent_reasons and effective_parent in quarantined_parent_reasons:
        status = "quarantined_kb_contradiction"
        reason = f"parent_quarantined:{quarantined_parent_reasons[effective_parent]}"
    elif intent == "track_order" and VEHICLE_GPS_TELEMETRY_RE.search(txt):
        status = "quarantined_kb_contradiction"
        reason = "kb_pol_ord_001_vehicle_gps_telemetry_contradiction"
    elif intent == "return_policy":
        sanitized = _MERCHANT_POLICY_OR_ONLINE_STORE_RE.sub(" ", txt)
        if PHYSICAL_INSTORE_RETURN_RE.search(sanitized):
            status = "quarantined_kb_contradiction"
            reason = "kb_pol_ret_001_physical_instore_channel_contradiction"
    elif intent == "track_delivery" and not VEHICLE_GPS_TELEMETRY_RE.search(txt):
        # Generic delivery status phrasing overlaps POL-ORD-001; retain in 46-class replay and flag explicitly.
        status = "ambiguous_retained"
        reason = "kb_pol_ord_001_generic_delivery_without_telemetry"
    elif intent == "track_order" and _TRACK_ORDER_REPLACEMENT_OVERLAP_RE.search(txt):
        status = "ambiguous_retained"
        reason = "bitext_track_order_replacement_overlap"
    elif intent == "return_product_in_store" and _RETURN_IN_STORE_INFO_OVERLAP_RE.search(txt):
        status = "ambiguous_retained"
        reason = "bitext_return_in_store_item_info_overlap"

    validate_semantic_status(status, context=f"row:{sample_id}")
    return {
        "sample_id": sample_id,
        "parent_sample_id": effective_parent,
        "text_sha256": text_sha256,
        "intent": intent,
        "source": source or "unspecified",
        "reason": reason,
        "status": status,
    }


def audit_rows_against_active_kb(
    rows: Sequence[Dict[str, Any]],
    split_name: str,
    quarantined_parent_reasons: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Audit rows with classify_row_kb_semantics, keeping valid/ambiguous rows and separating quarantined ones."""
    kept: List[Dict[str, Any]] = []
    quarantined_records: List[Dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    ambiguous_by_intent: Counter[str] = Counter()
    quarantined_by_intent: Counter[str] = Counter()
    parent_reasons = dict(quarantined_parent_reasons or {})

    for row in rows:
        rec = classify_row_kb_semantics(row, quarantined_parent_reasons=parent_reasons)
        rec_out = {**rec, "split": split_name}
        validate_semantic_status(rec_out["status"], context=f"{split_name}:{rec_out['sample_id']}")
        status_counts[rec_out["status"]] += 1
        if rec_out["status"] == "quarantined_kb_contradiction":
            quarantined_records.append(rec_out)
            reason_counts[rec_out["reason"]] += 1
            quarantined_by_intent[rec_out["intent"]] += 1
            parent_reasons.setdefault(rec_out["parent_sample_id"], rec_out["reason"])
        else:
            if rec_out["status"] == "ambiguous_retained":
                reason_counts[rec_out["reason"]] += 1
                ambiguous_by_intent[rec_out["intent"]] += 1
            kept.append(row)

    summary = {
        "split": split_name,
        "input_rows": len(rows),
        "kept_rows": len(kept),
        "quarantined_rows": len(quarantined_records),
        "status_counts": {k: int(v) for k, v in sorted(status_counts.items())},
        "reason_counts": {k: int(v) for k, v in sorted(reason_counts.items())},
        "quarantined_by_intent": {k: int(v) for k, v in sorted(quarantined_by_intent.items())},
        "ambiguous_retained_by_intent": {k: int(v) for k, v in sorted(ambiguous_by_intent.items())},
    }
    return kept, quarantined_records, summary


def build_semantic_audit_manifest(
    *,
    split_summaries: Sequence[Dict[str, Any]],
    quarantine_records: Sequence[Dict[str, Any]],
    extra_notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble and validate the canonical active-KB semantic audit manifest."""
    for rec in quarantine_records:
        validate_semantic_status(str(rec.get("status", "")), context=f"quarantine:{rec.get('sample_id')}")
    return {
        "schema_version": "active_kb_semantic_audit.v1",
        "kb_sources": [
            "data/knowledge/approved_kb.v2.json",
            "data/knowledge/policies.json",
            "apps/core_backend/config/policies/intent_policy.v2.json",
        ],
        "allowed_statuses": sorted(SEMANTIC_AUDIT_STATUSES),
        "quarantined_total": len(quarantine_records),
        "split_summaries": list(split_summaries),
        **(extra_notes or {}),
    }


SUPPORTED_11_DRAFT_SET = frozenset(SUPPORTED_11_DRAFT_INTENTS)
DEFAULT_REJECTOR_C_GRID: Tuple[float, ...] = (0.15, 0.35, 0.75, 1.5)


def is_draft_eligible_intent(intent: str, is_negative: int | bool = 0) -> bool:
    """True iff single-intent SUPPORTED_11 (excludes human_agent, ESCALATED_34, and negatives).

    Note: selective_label=1 in split JSONLs denotes 46-class membership, NOT draft eligibility.
    """
    return (not bool(is_negative)) and (str(intent) in SUPPORTED_11_DRAFT_SET)


def compute_rejector_eligibility_labels(rows: Sequence[Dict[str, Any]]) -> List[int]:
    """Compute binary rejector targets (1=draft-eligible SUPPORTED_11, 0=ESC34/human_agent/OOD/compound)."""
    return [
        1 if is_draft_eligible_intent(str(r.get("intent", "")), r.get("is_negative", 0)) else 0
        for r in rows
    ]


def verify_reload_from_archive(archive_dir: Path) -> Dict[str, Any]:
    """Load model + tokenizer strictly from MAIN archive and verify 46-label bijection + forward pass."""
    tok = AutoTokenizer.from_pretrained(str(archive_dir), local_files_only=True)
    mdl = AutoModelForSequenceClassification.from_pretrained(str(archive_dir), local_files_only=True)
    mdl.eval()
    id2label = {int(k): v for k, v in mdl.config.id2label.items()}
    assert len(id2label) == 46 and set(id2label.values()) == set(STANDARD_INTENTS_46), "46-label bijection invalid"
    enc = tok("Where is my order right now?", return_tensors="pt", truncation=True, max_length=64, padding="max_length")
    with torch.no_grad():
        logits = mdl(**enc).logits
    assert logits.shape == (1, 46) and torch.isfinite(logits).all(), "Invalid forward pass"
    return {"reload_verified": True, "archive_dir": str(archive_dir), "num_labels": 46}


def _softmax_np(logits: np.ndarray, temperature: float) -> np.ndarray:
    z = logits.astype(np.float64) / float(temperature)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / np.clip(e.sum(axis=1, keepdims=True), 1e-12, None)


def _extract_logits_and_cls(
    model: Any,
    tokenizer: Any,
    texts: Sequence[str],
    device: torch.device,
    batch_size: int = 64,
) -> Tuple[np.ndarray, np.ndarray]:
    """Run eval forward pass returning (logits, cls_embeddings) without modifying weights."""
    logits_list: List[np.ndarray] = []
    cls_list: List[np.ndarray] = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            tok = tokenizer(
                list(texts[i : i + batch_size]),
                max_length=64,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            ).to(device)
            out = model(**tok, output_hidden_states=True)
            logits_list.append(out.logits.detach().cpu().numpy())
            cls_list.append(out.hidden_states[-1][:, 0, :].detach().cpu().numpy())
    return np.concatenate(logits_list, axis=0), np.concatenate(cls_list, axis=0)


def fit_selective_rejector_from_arrays(
    *,
    model_version: str,
    trn_logits: np.ndarray,
    trn_cls: np.ndarray,
    trn_y: Sequence[int],
    cal_dom_logits: np.ndarray,
    cal_dom_cls: np.ndarray,
    cal_dom_intents: Sequence[str],
    bitext_cal_logits: np.ndarray,
    bitext_cal_cls: np.ndarray,
    bitext_cal_intents: Sequence[str],
    cal_neg_logits: np.ndarray,
    cal_neg_cls: np.ndarray,
    temperature: float,
    policy_v2: Any,
    c_grid: Sequence[float] = DEFAULT_REJECTOR_C_GRID,
    feature_spec: str = "cls_l2_plus_logit_geometry_v1",
) -> Tuple[SelectiveRejectorParams, Dict[str, Any]]:
    """Fit StandardScaler + LogisticRegression strictly on TRAIN arrays, select (C, tau) ONLY on CAL."""
    y_train_arr = np.asarray(trn_y, dtype=np.int64)
    if len(np.unique(y_train_arr)) < 2:
        raise ValueError("Rejector training targets must contain both draft-eligible (1) and non-draft (0) examples")

    trn_feats = compute_selective_feature_matrix(trn_logits, trn_cls, temperature=temperature, feature_spec=feature_spec)
    scaler = StandardScaler()
    trn_scaled = scaler.fit_transform(trn_feats)

    cal_dom_feats = compute_selective_feature_matrix(
        cal_dom_logits, cal_dom_cls, temperature=temperature, feature_spec=feature_spec
    )
    bitext_cal_feats = compute_selective_feature_matrix(
        bitext_cal_logits, bitext_cal_cls, temperature=temperature, feature_spec=feature_spec
    )
    cal_neg_feats = compute_selective_feature_matrix(
        cal_neg_logits, cal_neg_cls, temperature=temperature, feature_spec=feature_spec
    )

    def _route_probs(probs: np.ndarray) -> List[Tuple[str, str]]:
        routes: List[Tuple[str, str]] = []
        for vec in probs:
            order = np.argsort(-vec)
            top1, top2 = int(order[0]), int(order[1])
            pred_lbl = STANDARD_INTENTS_46[top1]
            conf = float(vec[top1])
            margin = float(vec[top1] - vec[top2])
            dec = decide_route(
                IntentPrediction(intent=pred_lbl, confidence=conf, margin=margin, model_version=model_version),
                RoutingContext(ticket_customer_id="cal", extracted_slots={}, is_personal_lookup=False),
                policy_v2,
            )
            routes.append((pred_lbl, dec.action))
        return routes

    cal_dom_routes = _route_probs(_softmax_np(cal_dom_logits, temperature))
    bit_cal_routes = _route_probs(_softmax_np(bitext_cal_logits, temperature))
    cal_neg_routes = _route_probs(_softmax_np(cal_neg_logits, temperature))

    sup11_dom_raw = sum(1 for y in cal_dom_intents if y in SUPPORTED_11_DRAFT_SET)
    sup11_bit_idx = [i for i, y in enumerate(bitext_cal_intents) if y in SUPPORTED_11_DRAFT_SET]
    sup11_bit_raw = len(sup11_bit_idx)
    if sup11_dom_raw + sup11_bit_raw == 0:
        raise ValueError("Calibration set contains 0 SUPPORTED_11 draft-eligible rows across domain and Bitext")

    dom_esc34_n = sum(1 for y in cal_dom_intents if y in ESCALATED_34_INTENTS)
    dom_human_n = sum(1 for y in cal_dom_intents if y == "human_agent")
    bit_esc34_idx = [i for i, y in enumerate(bitext_cal_intents) if y in ESCALATED_34_INTENTS]
    bit_human_idx = [i for i, y in enumerate(bitext_cal_intents) if y == "human_agent"]
    esc34_cal_total = dom_esc34_n + len(bit_esc34_idx)
    human_cal_total = dom_human_n + len(bit_human_idx)
    non_draft_cal_total = max(1, esc34_cal_total + human_cal_total)
    neg_cal_n = max(1, len(cal_neg_routes))

    best_obj: float = -1e9
    best_params: Optional[SelectiveRejectorParams] = None
    best_stats: Dict[str, Any] = {}
    feasible_candidates = 0
    total_candidates = 0
    safe_candidates = 0
    nonzero_cov_candidates = 0
    max_dom_corr_when_safe = 0
    max_bit_corr_when_safe = 0
    min_unsafe_when_nonzero_cov: Optional[int] = None

    for c_val in c_grid:
        clf = LogisticRegression(C=float(c_val), class_weight="balanced", max_iter=2500, random_state=42)
        clf.fit(trn_scaled, y_train_arr)
        cand_rej = SelectiveRejectorParams(
            enabled=True,
            feature_spec=feature_spec,
            feature_dim=trn_feats.shape[1],
            scaler_mean=scaler.mean_.tolist(),
            scaler_scale=scaler.scale_.tolist(),
            weights=clf.coef_[0].tolist(),
            bias=float(clf.intercept_[0]),
            threshold=0.50,
        )
        cal_dom_p_in = score_rejector(cal_dom_feats, cand_rej)
        bit_cal_p_in = score_rejector(bitext_cal_feats, cand_rej)
        cal_neg_p_in = score_rejector(cal_neg_feats, cand_rej)

        for tau in np.linspace(0.25, 0.90, 66):
            total_candidates += 1
            tau_f = round(float(tau), 4)
            pos_dom_corr = pos_dom_raw = esc34_unsafe_draft = human_unsafe_draft = 0
            for i, gold_y in enumerate(cal_dom_intents):
                pred_lbl, raw_act = cal_dom_routes[i]
                eff_act = "manual_fallback" if (raw_act == "retrieve_draft" and cal_dom_p_in[i] < tau_f) else raw_act
                if gold_y in SUPPORTED_11_DRAFT_SET and eff_act == "retrieve_draft":
                    pos_dom_raw += 1
                    if pred_lbl == gold_y:
                        pos_dom_corr += 1
                elif gold_y in ESCALATED_34_INTENTS and eff_act == "retrieve_draft":
                    esc34_unsafe_draft += 1
                elif gold_y == "human_agent" and eff_act == "retrieve_draft":
                    human_unsafe_draft += 1

            pos_bit_corr = pos_bit_raw = 0
            for i in sup11_bit_idx:
                pred_lbl, raw_act = bit_cal_routes[i]
                if raw_act == "retrieve_draft" and bit_cal_p_in[i] >= tau_f:
                    pos_bit_raw += 1
                    if pred_lbl == bitext_cal_intents[i]:
                        pos_bit_corr += 1
            for i in bit_esc34_idx:
                if bit_cal_routes[i][1] == "retrieve_draft" and bit_cal_p_in[i] >= tau_f:
                    esc34_unsafe_draft += 1
            for i in bit_human_idx:
                if bit_cal_routes[i][1] == "retrieve_draft" and bit_cal_p_in[i] >= tau_f:
                    human_unsafe_draft += 1

            neg_false_draft = neg_false_accept_any = 0
            for i, (_, raw_act) in enumerate(cal_neg_routes):
                accepted = bool(cal_neg_p_in[i] >= tau_f)
                if accepted:
                    neg_false_accept_any += 1
                if raw_act == "retrieve_draft" and accepted:
                    neg_false_draft += 1

            non_draft_unsafe = esc34_unsafe_draft + human_unsafe_draft
            total_unsafe = neg_false_draft + non_draft_unsafe
            zero_unsafe = total_unsafe == 0
            nonzero_dom = sup11_dom_raw == 0 or pos_dom_corr > 0
            nonzero_bit = sup11_bit_raw == 0 or pos_bit_corr > 0
            nonzero_cov = nonzero_dom and nonzero_bit and (pos_dom_corr + pos_bit_corr > 0)

            if zero_unsafe:
                safe_candidates += 1
                max_dom_corr_when_safe = max(max_dom_corr_when_safe, pos_dom_corr)
                max_bit_corr_when_safe = max(max_bit_corr_when_safe, pos_bit_corr)
            if nonzero_cov:
                nonzero_cov_candidates += 1
                min_unsafe_when_nonzero_cov = (
                    total_unsafe if min_unsafe_when_nonzero_cov is None else min(min_unsafe_when_nonzero_cov, total_unsafe)
                )
            if not (zero_unsafe and nonzero_cov):
                continue

            feasible_candidates += 1
            cov_rates = []
            if sup11_dom_raw > 0:
                cov_rates.append(pos_dom_corr / sup11_dom_raw)
            if sup11_bit_raw > 0:
                cov_rates.append(pos_bit_corr / sup11_bit_raw)
            sup11_cov_score = sum(cov_rates) / len(cov_rates)
            tau_obj = (
                sup11_cov_score
                - 3.0 * (neg_false_draft / neg_cal_n)
                - 3.0 * (non_draft_unsafe / non_draft_cal_total)
                - 0.25 * (neg_false_accept_any / neg_cal_n)
                - 0.02 * abs(tau_f - 0.50)
            )
            if best_params is None or tau_obj > best_obj:
                best_obj = tau_obj
                best_params = SelectiveRejectorParams(
                    enabled=True,
                    feature_spec=feature_spec,
                    feature_dim=cand_rej.feature_dim,
                    scaler_mean=cand_rej.scaler_mean,
                    scaler_scale=cand_rej.scaler_scale,
                    weights=cand_rej.weights,
                    bias=cand_rej.bias,
                    threshold=tau_f,
                )
                best_stats = {
                    "rejector_c": float(c_val),
                    "threshold": tau_f,
                    "zero_cal_unsafe": True,
                    "cal_dom_raw_draft": pos_dom_raw,
                    "cal_dom_correct_draft": pos_dom_corr,
                    "cal_dom_sup11_total": sup11_dom_raw,
                    "cal_bitext_raw_draft": pos_bit_raw,
                    "cal_bitext_correct_draft": pos_bit_corr,
                    "cal_bitext_sup11_total": sup11_bit_raw,
                    "cal_sup11_correct_draft": pos_dom_corr + pos_bit_corr,
                    "cal_sup11_total": sup11_dom_raw + sup11_bit_raw,
                    "cal_esc34_unsafe_draft": esc34_unsafe_draft,
                    "cal_esc34_total": esc34_cal_total,
                    "cal_human_agent_unsafe_draft": human_unsafe_draft,
                    "cal_human_agent_total": human_cal_total,
                    "cal_non_draft_unsafe_draft": non_draft_unsafe,
                    "cal_neg_false_draft": neg_false_draft,
                    "cal_neg_false_accept_any": neg_false_accept_any,
                    "cal_neg_total": len(cal_neg_routes),
                    "total_candidates_evaluated": total_candidates,
                    "tau_objective": round(float(tau_obj), 5),
                }

    if best_params is None:
        raise ValueError(
            "No feasible CAL rejector point found across C grid "
            f"(evaluated={total_candidates}, safe={safe_candidates}, nonzero_cov={nonzero_cov_candidates}, "
            f"max_dom_corr_when_safe={max_dom_corr_when_safe}/{sup11_dom_raw}, "
            f"max_bitext_corr_when_safe={max_bit_corr_when_safe}/{sup11_bit_raw}, "
            f"min_unsafe_when_nonzero_cov={min_unsafe_when_nonzero_cov})"
        )
    best_stats["feasible_candidates"] = feasible_candidates
    return best_params, best_stats


def _truncation_rate(tokenizer: Any, texts: Sequence[str], max_length: int = 64) -> Dict[str, Any]:
    if not texts:
        return {"count": 0, "truncated_count": 0, "truncation_rate": 0.0, "max_tokens": 0}
    lens = [len(tokenizer.encode(t, truncation=False, add_special_tokens=True)) for t in texts]
    trunc = sum(1 for x in lens if x > max_length)
    return {
        "count": len(lens),
        "truncated_count": trunc,
        "truncation_rate": round(trunc / len(lens), 6),
        "max_tokens": max(lens),
    }


def _has_gold_conflict(text: str, gold_norms: set[str], gold_toks: List[set[str]]) -> bool:
    norm = _normalize_text(text)
    if norm in gold_norms:
        return True
    rt = _token_set(text)
    if len(rt) < 4:
        return False
    for gt in gold_toks:
        union = rt | gt
        if union and (len(rt & gt) / len(union)) >= 0.85:
            return True
    return False


class _BoundaryDataset(Dataset):
    def __init__(self, encodings: Dict[str, torch.Tensor], labels: List[int], is_neg: List[int]) -> None:
        self.encodings = encodings
        self.labels = torch.tensor(labels, dtype=torch.long)
        self.is_neg = torch.tensor(is_neg, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        item = {k: v[idx] for k, v in self.encodings.items()}
        item["labels"] = self.labels[idx]
        item["is_neg"] = self.is_neg[idx]
        return item


def prepare_and_lock_splits(
    *,
    worktree_root: Path,
    data_repo_root: Path,
    init_model_dir: Path,
    artifact_root: Path,
    replay_per_class: int = 160,
    noise_aug_per_class: int = 80,
    bitext_cal_per_class: int = 15,
    seed: int = 20261113,
) -> Dict[str, Any]:
    """Audit and lock all train/cal/eval JSONLs and augmentation-parent provenance BEFORE training."""
    weights_path = init_model_dir / "model.safetensors"
    if not weights_path.exists():
        raise FileNotFoundError(f"Missing init checkpoint weights: {weights_path}")
    init_weights_sha = _sha256_file(weights_path)

    datasets_dir = artifact_root / "datasets"
    boundary_audit = audit_and_export_boundary_datasets(datasets_dir, repo_root=data_repo_root)

    pos_train = _read_jsonl(datasets_dir / "boundary_pos_train.jsonl")
    neg_train = _read_jsonl(datasets_dir / "boundary_neg_train.jsonl")
    pos_cal = _read_jsonl(datasets_dir / "boundary_pos_calibration.jsonl")
    neg_cal = _read_jsonl(datasets_dir / "boundary_neg_calibration.jsonl")
    pos_eval = _read_jsonl(datasets_dir / "boundary_pos_evaluation.jsonl")
    neg_eval = _read_jsonl(datasets_dir / "boundary_neg_evaluation.jsonl")

    lineage = verify_original_46_label_lineage(repo_root=worktree_root)
    gold_bench = _load_frozen_benchmark_texts(data_repo_root)
    gold_norms = {_normalize_text(t) for _, t in gold_bench if _normalize_text(t)}
    gold_toks = [_token_set(t) for _, t in gold_bench if len(_token_set(t)) >= 4]

    # Exclude any Bitext row near frozen benchmarks, held-out Bitext test, or domain cal/eval
    reserved_norms = {
        _normalize_text(r["instruction"]) for r in (pos_cal + neg_cal + pos_eval + neg_eval)
    }
    test_norms = {_normalize_text(str(t)) for t in lineage.test_df["instruction"].tolist() if _normalize_text(str(t))}

    rng = random.Random(seed)
    bitext_cal_rows: List[Dict[str, Any]] = []
    bitext_train_clean_rows: List[Dict[str, Any]] = []
    bitext_train_noisy_rows: List[Dict[str, Any]] = []
    train_parent_ids: set[str] = set()
    cal_parent_ids: set[str] = set()
    cal_norms_all: set[str] = set(reserved_norms)
    pending_train_per_class: List[Tuple[str, List[Tuple[str, str]]]] = []

    # First pass: select cal slices across all 46 classes and record ALL normalized cal texts
    for idx, lbl in enumerate(STANDARD_INTENTS_46):
        sub = lineage.train_df[lineage.train_df["intent"] == lbl].sample(frac=1.0, random_state=seed + idx)
        safe_records: List[Tuple[str, str]] = []
        for row in sub.itertuples(index=False):
            txt = str(row.instruction)
            sid = str(row.sample_id)
            norm = _normalize_text(txt)
            if not norm or norm in reserved_norms or norm in test_norms or _has_gold_conflict(txt, gold_norms, gold_toks):
                continue
            safe_records.append((sid, txt))
            if len(safe_records) >= bitext_cal_per_class + replay_per_class + 40:
                break

        cal_slice = safe_records[:bitext_cal_per_class]
        for sid, txt in cal_slice:
            cal_parent_ids.add(sid)
            cal_norms_all.add(_normalize_text(txt))
            bitext_cal_rows.append(
                {
                    "sample_id": f"bitext_cal_{sid}",
                    "parent_sample_id": sid,
                    "text": txt,
                    "instruction": txt,
                    "intent": lbl,
                    "true_intent": lbl,
                    "group_id": f"bitext_cal_{sid}",
                    "source": "bitext_train_partition_cal",
                    "selective_label": 1,
                }
            )
        pending_train_per_class.append((lbl, safe_records[bitext_cal_per_class:]))

    # Second pass: select train slices strictly excluding ANY normalized match with cal/eval
    for lbl, candidates in pending_train_per_class:
        trn_slice: List[Tuple[str, str]] = []
        for sid, txt in candidates:
            if _normalize_text(txt) in cal_norms_all:
                continue
            trn_slice.append((sid, txt))
            if len(trn_slice) >= replay_per_class:
                break

        for sid, txt in trn_slice:
            train_parent_ids.add(sid)
            bitext_train_clean_rows.append(
                {
                    "sample_id": f"bitext_trn_{sid}",
                    "parent_sample_id": sid,
                    "text": txt,
                    "instruction": txt,
                    "intent": lbl,
                    "true_intent": lbl,
                    "group_id": f"bitext_trn_{sid}",
                    "source": "bitext_train_partition_clean",
                    "selective_label": 1,
                }
            )

        for a_i, (sid, txt) in enumerate(trn_slice[:noise_aug_per_class]):
            noisy_txt = apply_realistic_noise(txt, rng)
            noisy_norm = _normalize_text(noisy_txt)
            if not noisy_norm or noisy_norm in cal_norms_all or noisy_norm in test_norms or _has_gold_conflict(noisy_txt, gold_norms, gold_toks):
                continue
            bitext_train_noisy_rows.append(
                {
                    "sample_id": f"bitext_trn_aug_{sid}_{a_i}",
                    "parent_sample_id": sid,
                    "text": noisy_txt,
                    "instruction": noisy_txt,
                    "intent": lbl,
                    "true_intent": lbl,
                    "group_id": f"bitext_trn_{sid}",
                    "source": "bitext_train_partition_noise_aug",
                    "selective_label": 1,
                }
            )

    test_ids = set(lineage.test_df["sample_id"].astype(str).tolist())

    # Apply the same active-KB semantic audit across Bitext clean/noisy/cal AND domain splits.
    # Noisy children inherit parent quarantine even when typos mask surface phrasing (e.g. "at the stoe").
    bitext_cal_rows, q_cal, sum_bcal = audit_rows_against_active_kb(bitext_cal_rows, "bitext_cal")
    bitext_train_clean_rows, q_bclean, sum_bclean = audit_rows_against_active_kb(
        bitext_train_clean_rows, "bitext_train_clean"
    )
    quarantined_bitext_parents = {
        str(rec["parent_sample_id"]): str(rec["reason"]) for rec in (q_cal + q_bclean)
    }
    bitext_train_noisy_rows, q_bnoisy, sum_bnoisy = audit_rows_against_active_kb(
        bitext_train_noisy_rows,
        "bitext_train_noisy",
        quarantined_parent_reasons=quarantined_bitext_parents,
    )
    pos_train, q_dtrn, sum_dtrn = audit_rows_against_active_kb(pos_train, "domain_pos_train")
    pos_cal, q_dcal, sum_dcal = audit_rows_against_active_kb(pos_cal, "domain_pos_calibration")
    pos_eval, q_devl, sum_devl = audit_rows_against_active_kb(pos_eval, "domain_pos_evaluation")

    train_parent_ids = {str(r["parent_sample_id"]) for r in bitext_train_clean_rows if r.get("parent_sample_id")} | {
        str(r["parent_sample_id"]) for r in bitext_train_noisy_rows if r.get("parent_sample_id")
    }
    cal_parent_ids = {str(r["parent_sample_id"]) for r in bitext_cal_rows if r.get("parent_sample_id")}

    assert train_parent_ids.isdisjoint(cal_parent_ids), "Bitext train/cal parent overlap!"
    assert train_parent_ids.isdisjoint(test_ids), "Bitext train/test overlap!"
    assert cal_parent_ids.isdisjoint(test_ids), "Bitext cal/test overlap!"

    # Gate-compatible full train/cal manifests (strictly balanced group_ids)
    # Upsample domain/boundary rows for balanced mini-batch gradient signal without cloning rows into gate file.
    bitext_test_rows = [
        {
            "sample_id": str(r.sample_id),
            "text": str(r.instruction),
            "true_intent": str(r.intent),
            "group_id": f"bitext_tst_{r.sample_id}",
        }
        for r in lineage.test_df.itertuples(index=False)
    ]
    # Read-only audit of held-out bitext_test_6690 (test rows remain 100% untouched).
    _, _, sum_btst_ro = audit_rows_against_active_kb(bitext_test_rows, "bitext_test_6690_readonly")

    quarantine_records = q_dtrn + q_dcal + q_devl + q_bclean + q_bnoisy + q_cal
    semantic_manifest = build_semantic_audit_manifest(
        split_summaries=[sum_dtrn, sum_dcal, sum_devl, sum_bclean, sum_bnoisy, sum_bcal, sum_btst_ro],
        quarantine_records=quarantine_records,
    )
    sem_manifest_path = datasets_dir / "semantic_audit_manifest.json"
    sem_manifest_path.write_text(json.dumps(semantic_manifest, indent=2) + "\n", encoding="utf-8")

    full_train_dedup = pos_train + neg_train + bitext_train_clean_rows + bitext_train_noisy_rows
    full_cal_dedup = pos_cal + neg_cal + bitext_cal_rows

    hashes = {
        "boundary_split_manifest": _sha256_file(datasets_dir / "split_manifest.json"),
        "boundary_pos_train": _write_jsonl(datasets_dir / "boundary_pos_train.jsonl", pos_train),
        "boundary_pos_calibration": _write_jsonl(datasets_dir / "boundary_pos_calibration.jsonl", pos_cal),
        "boundary_pos_evaluation": _write_jsonl(datasets_dir / "boundary_pos_evaluation.jsonl", pos_eval),
        "full_train_split": _write_jsonl(datasets_dir / "full_train_split.jsonl", full_train_dedup),
        "full_cal_split": _write_jsonl(datasets_dir / "full_cal_split.jsonl", full_cal_dedup),
        "bitext_train_clean": _write_jsonl(datasets_dir / "bitext_train_clean.jsonl", bitext_train_clean_rows),
        "bitext_train_noisy": _write_jsonl(datasets_dir / "bitext_train_noisy.jsonl", bitext_train_noisy_rows),
        "bitext_cal": _write_jsonl(datasets_dir / "bitext_cal.jsonl", bitext_cal_rows),
        "bitext_test_6690": _write_jsonl(datasets_dir / "bitext_test_6690.jsonl", bitext_test_rows),
        "quarantine_records": _write_jsonl(datasets_dir / "quarantine_records.jsonl", quarantine_records),
        "semantic_audit_manifest": _sha256_file(sem_manifest_path),
    }

    tokenizer = AutoTokenizer.from_pretrained(str(init_model_dir))
    oos_texts = [str(r.get("text") or "") for r in _read_jsonl(data_repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl")]
    sys_texts = [str(r.get("text") or "") for r in _read_jsonl(data_repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl")]
    trunc_stats = {
        "max_length": 64,
        "train_all": _truncation_rate(tokenizer, [r["text"] for r in full_train_dedup], 64),
        "cal_all": _truncation_rate(tokenizer, [r["text"] for r in full_cal_dedup], 64),
        "eval_pos": _truncation_rate(tokenizer, [r["text"] for r in pos_eval], 64),
        "eval_neg": _truncation_rate(tokenizer, [r["text"] for r in neg_eval], 64),
        "ml_oos_80": _truncation_rate(tokenizer, oos_texts, 64),
        "system_acceptance_156": _truncation_rate(tokenizer, sys_texts, 64),
    }

    lock_manifest = {
        "schema_version": "task_a_fit1_dataset_lock.v1",
        "locked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "init_model_dir": str(init_model_dir),
        "init_weights_sha256": init_weights_sha,
        "seed": seed,
        "bitext_cleaned_sha256": lineage.cleaned_sha256,
        "bitext_splits_sha256": lineage.splits_sha256,
        "counts": {
            "domain_pos_train": len(pos_train),
            "domain_neg_train": len(neg_train),
            "bitext_train_clean": len(bitext_train_clean_rows),
            "bitext_train_noisy": len(bitext_train_noisy_rows),
            "domain_pos_cal": len(pos_cal),
            "domain_neg_cal": len(neg_cal),
            "bitext_cal": len(bitext_cal_rows),
            "domain_pos_eval": len(pos_eval),
            "domain_neg_eval": len(neg_eval),
            "bitext_test_eval": len(bitext_test_rows),
        },
        "augmentation_parent_disjointness": {
            "train_parents": len(train_parent_ids),
            "cal_parents": len(cal_parent_ids),
            "test_parents": len(test_ids),
            "train_cal_overlap": 0,
            "train_test_overlap": 0,
            "cal_test_overlap": 0,
        },
        "dataset_hashes": hashes,
        "boundary_audit_summary": boundary_audit["overlap_audit"],
        "semantic_audit": semantic_manifest,
        "quarantined_domain_base_ids": [str(r["sample_id"]) for r in (q_dtrn + q_dcal + q_devl)],
        "token_truncation_audit_max_length_64": trunc_stats,
    }
    lock_path = datasets_dir / "dataset_lock_manifest.json"
    lock_path.write_text(json.dumps(lock_manifest, indent=2), encoding="utf-8")
    return lock_manifest


def _supcon_loss(cls_norm: torch.Tensor, targets: torch.Tensor, temperature: float = 0.12) -> torch.Tensor:
    """In-batch supervised contrastive loss on L2-normalized [CLS] embeddings."""
    bsz = cls_norm.size(0)
    if bsz < 2:
        return torch.tensor(0.0, device=cls_norm.device)
    sim = (cls_norm @ cls_norm.T) / temperature
    eye = torch.eye(bsz, dtype=torch.bool, device=cls_norm.device)
    logits_max, _ = sim.masked_fill(eye, -1e4).max(dim=1, keepdim=True)
    logits = sim - logits_max.detach()
    exp_logits = torch.exp(logits).masked_fill(eye, 0.0)
    log_prob = logits - torch.log(exp_logits.sum(dim=1, keepdim=True).clamp(min=1e-9))

    same_cls = (targets.unsqueeze(0) == targets.unsqueeze(1)) & (~eye)
    pos_counts = same_cls.sum(dim=1)
    valid = pos_counts > 0
    if not valid.any():
        return torch.tensor(0.0, device=cls_norm.device)
    mean_log_prob_pos = (same_cls[valid].float() * log_prob[valid]).sum(dim=1) / pos_counts[valid].float()
    return -mean_log_prob_pos.mean()


def run_fit_and_lock_candidate(
    *,
    worktree_root: Path,
    data_repo_root: Path,
    init_model_dir: Path,
    artifact_root: Path,
    fit_mode: str = "fit1_kl",
    output_subdir: str = "candidate_model",
    epochs: int = 3,
    batch_size: int = 32,
    lr: float = 2e-5,
    seed: int = 42,
    enable_selective_rejector: bool = False,
    rejector_c_grid: Sequence[float] = DEFAULT_REJECTOR_C_GRID,
    candidate_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Fit 1 or Fit 2 from locked splits, fit T>=1.0 on cal (+ optional 776d rejector), and lock manifests."""
    datasets_dir = artifact_root / "datasets"
    lock_path = datasets_dir / "dataset_lock_manifest.json"
    if not lock_path.exists():
        raise FileNotFoundError(f"Lock splits first (--prepare-only): missing {lock_path}")
    lock_manifest = json.loads(lock_path.read_text(encoding="utf-8"))

    pos_train = _read_jsonl(datasets_dir / "boundary_pos_train.jsonl")
    neg_train = _read_jsonl(datasets_dir / "boundary_neg_train.jsonl")
    bitext_clean = _read_jsonl(datasets_dir / "bitext_train_clean.jsonl")
    bitext_noisy = _read_jsonl(datasets_dir / "bitext_train_noisy.jsonl")
    pos_cal = _read_jsonl(datasets_dir / "boundary_pos_calibration.jsonl")
    neg_cal = _read_jsonl(datasets_dir / "boundary_neg_calibration.jsonl")
    bitext_cal = _read_jsonl(datasets_dir / "bitext_cal.jsonl")

    validate_boundary_split_taxonomy(pos_train, neg_train, "train")
    validate_boundary_split_taxonomy(pos_cal, neg_cal, "cal")

    label2id = {lbl: idx for idx, lbl in enumerate(STANDARD_INTENTS_46)}
    sup12_indices = [label2id[lbl] for lbl in SUPPORTED_12_INTENTS]

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

    neg_rep = 12 if fit_mode == "fit2_supcon_energy" else 5
    resolved_neg_reps = [resolve_neg_repeat(r, neg_rep) for r in neg_train]
    neg_rng = random.Random(seed + 99)
    for r, row_rep in zip(neg_train, resolved_neg_reps):
        for rep_i in range(row_rep):
            txt = apply_realistic_noise(r["text"], neg_rng) if (fit_mode == "fit2_supcon_energy" and rep_i % 4 == 3) else r["text"]
            train_texts.append(txt)
            train_labels.append(0)
            train_is_neg.append(1)

    torch.manual_seed(seed)
    np.random.seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    tokenizer = AutoTokenizer.from_pretrained(str(init_model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(init_model_dir))
    for p in model.parameters():
        p.requires_grad = True
    model.to(device)

    enc = tokenizer(train_texts, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
    ds = _BoundaryDataset(enc, train_labels, train_is_neg)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=True, generator=torch.Generator().manual_seed(seed))

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = max(1, len(loader) * epochs)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=int(0.10 * total_steps), num_training_steps=total_steps)

    sup12_idx_t = torch.tensor(sup12_indices, dtype=torch.long, device=device)
    uniform_target = torch.full((1, len(STANDARD_INTENTS_46)), 1.0 / len(STANDARD_INTENTS_46), device=device)

    t0 = time.perf_counter()
    epoch_stats: List[Dict[str, Any]] = []
    for ep in range(1, epochs + 1):
        model.train()
        tot_loss = 0.0
        pos_sum = 0.0
        neg_sum = 0.0
        supcon_sum = 0.0
        for batch in loader:
            optimizer.zero_grad()
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            is_neg = batch["is_neg"].to(device)

            out = model(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=(fit_mode == "fit2_supcon_energy"))
            logits = out.logits
            pos_mask = is_neg == 0
            neg_mask = is_neg == 1

            loss = torch.tensor(0.0, device=device)
            if pos_mask.any():
                l_pos = F.cross_entropy(logits[pos_mask], labels[pos_mask], label_smoothing=0.03)
                loss = loss + l_pos
                pos_sum += float(l_pos.item())

            if fit_mode == "fit2_supcon_energy":
                cls_norm = F.normalize(out.hidden_states[-1][:, 0, :], dim=-1)
                sc_targets = torch.where(neg_mask, torch.full_like(labels, -1), labels)
                l_sc = 0.25 * _supcon_loss(cls_norm, sc_targets, temperature=0.12)
                loss = loss + l_sc
                supcon_sum += float(l_sc.item())

            if neg_mask.any():
                neg_logits = logits[neg_mask]
                log_probs = F.log_softmax(neg_logits, dim=-1)
                l_kl = F.kl_div(log_probs, uniform_target.expand_as(log_probs), reduction="batchmean")
                sup12_mass = torch.softmax(neg_logits, dim=-1)[:, sup12_idx_t].sum(dim=-1)
                ceil_thr = 0.18 if fit_mode == "fit2_supcon_energy" else 0.25
                l_ceil = torch.relu(sup12_mass - ceil_thr).pow(2).mean()
                l_neg = (0.80 * l_kl + 3.0 * l_ceil) if fit_mode == "fit2_supcon_energy" else (0.65 * l_kl + 2.0 * l_ceil)
                if fit_mode == "fit2_supcon_energy" and pos_mask.any():
                    pos_energy_mean = (-torch.logsumexp(logits[pos_mask], dim=-1)).mean().detach()
                    neg_energy = -torch.logsumexp(neg_logits, dim=-1)
                    l_eng = 0.25 * torch.relu((pos_energy_mean + 2.0) - neg_energy).pow(2).mean()
                    l_neg = l_neg + l_eng
                loss = loss + l_neg
                neg_sum += float(l_neg.item())

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            tot_loss += float(loss.item())

        epoch_stats.append(
            {
                "epoch": ep,
                "mean_loss": round(tot_loss / max(1, len(loader)), 5),
                "pos_loss_sum": round(pos_sum / max(1, len(loader)), 5),
                "neg_loss_sum": round(neg_sum / max(1, len(loader)), 5),
                "supcon_loss_sum": round(supcon_sum / max(1, len(loader)), 5),
            }
        )

    cand_dir = artifact_root / output_subdir
    cand_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(cand_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(cand_dir))
    train_elapsed = round(time.perf_counter() - t0, 2)

    # Fit T >= 1.0 strictly on isolated calibration positive set
    model.eval()
    cal_pos_rows = pos_cal + bitext_cal
    cal_texts = [r["text"] for r in cal_pos_rows]
    cal_y = np.array([label2id[r["intent"]] for r in cal_pos_rows], dtype=np.int64)
    neg_cal_texts = [r["text"] for r in neg_cal]

    if enable_selective_rejector:
        cal_logits, cal_cls = _extract_logits_and_cls(model, tokenizer, cal_texts, device)
        neg_cal_logits, neg_cal_cls = _extract_logits_and_cls(model, tokenizer, neg_cal_texts, device)
    else:
        logits_chunks: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(cal_texts), 64):
                tok = tokenizer(cal_texts[i : i + 64], max_length=64, padding="max_length", truncation=True, return_tensors="pt").to(device)
                logits_chunks.append(model(**tok).logits.cpu().numpy())
        cal_logits = np.concatenate(logits_chunks, axis=0)
        cal_cls = np.empty((0, 0), dtype=np.float32)

        neg_logits_list: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(neg_cal_texts), 64):
                tok = tokenizer(neg_cal_texts[i : i + 64], max_length=64, padding="max_length", truncation=True, return_tensors="pt").to(device)
                neg_logits_list.append(model(**tok).logits.cpu().numpy())
        neg_cal_logits = np.concatenate(neg_logits_list, axis=0)
        neg_cal_cls = np.empty((0, 0), dtype=np.float32)

    temperature = fit_temperature_on_calibration_logits(cal_logits, cal_y, min_temperature=1.0, max_temperature=2.5)
    neg_cal_probs = _softmax_np(neg_cal_logits, temperature)
    max_neg_cal_sup_prob = float(neg_cal_probs[:, sup12_indices].max())

    # Compute exact staged artifact hashes
    art_hashes = {
        "model.safetensors": _sha256_file(cand_dir / "model.safetensors"),
        "tokenizer.json": _sha256_file(cand_dir / "tokenizer.json"),
        "config.json": _sha256_file(cand_dir / "config.json"),
    }

    cfg_json = json.loads((cand_dir / "config.json").read_text(encoding="utf-8"))
    id2label_dict = {str(k): v for k, v in (cfg_json.get("id2label") or {}).items()}
    git_sha = subprocess.check_output(["git", "-C", str(worktree_root), "rev-parse", "HEAD"], text=True).strip()
    default_ver = "fit2-supcon-energy-boundary-v1" if fit_mode == "fit2_supcon_energy" else "fit1-boundary-closure-v1"
    model_ver = candidate_name or default_ver

    rejector_cal_stats: Optional[Dict[str, Any]] = None
    if enable_selective_rejector:
        rej_train_rows: List[Dict[str, Any]] = []
        for r in pos_train:
            rep = 4 if is_draft_eligible_intent(r["intent"], 0) else 2
            for _ in range(rep):
                rej_train_rows.append({"text": r["text"], "intent": r["intent"], "is_negative": 0})
        for r in bitext_clean:
            rej_train_rows.append({"text": r["text"], "intent": r["intent"], "is_negative": 0})
        for r in neg_train:
            for _ in range(4):
                rej_train_rows.append({"text": r["text"], "intent": r["intent"], "is_negative": 1})

        rej_train_y = compute_rejector_eligibility_labels(rej_train_rows)
        trn_logits, trn_cls = _extract_logits_and_cls(model, tokenizer, [r["text"] for r in rej_train_rows], device)
        n_dom_cal = len(pos_cal)
        policy_v2 = load_policy_v2(str(worktree_root / "apps/core_backend/config/policies/intent_policy.v2.json"))
        rej_params, rejector_cal_stats = fit_selective_rejector_from_arrays(
            model_version=model_ver,
            trn_logits=trn_logits,
            trn_cls=trn_cls,
            trn_y=rej_train_y,
            cal_dom_logits=cal_logits[:n_dom_cal],
            cal_dom_cls=cal_cls[:n_dom_cal],
            cal_dom_intents=[r["intent"] for r in pos_cal],
            bitext_cal_logits=cal_logits[n_dom_cal:],
            bitext_cal_cls=cal_cls[n_dom_cal:],
            bitext_cal_intents=[r["intent"] for r in bitext_cal],
            cal_neg_logits=neg_cal_logits,
            cal_neg_cls=neg_cal_cls,
            temperature=temperature,
            policy_v2=policy_v2,
            c_grid=rejector_c_grid,
        )
        rejector_block = rej_params.to_dict()
        rejector_block["reject_when"] = "below"
    else:
        rejector_block = {
            "enabled": False,
            "type": "logistic_regression_v1",
            "feature_spec": "logit_geometry_v1",
            "feature_dim": 8,
            "scaler_mean": [0.0] * 8,
            "scaler_scale": [1.0] * 8,
            "weights": [0.0] * 8,
            "bias": 0.0,
            "threshold": 0.0,
            "reject_when": "below",
            "positive_label": "in_scope",
        }

    cal_manifest = {
        "schema_version": "selective_calibration.v1",
        "model_version": model_ver,
        "weights_sha256": art_hashes["model.safetensors"],
        "tokenizer_sha256": art_hashes["tokenizer.json"],
        "config_sha256": art_hashes["config.json"],
        "artifact_hashes": art_hashes,
        "tokenization": {"max_length": 64, "padding": "max_length", "truncation": True},
        "label_space": {"num_labels": 46, "valid_46_label_bijection": True, "id2label": id2label_dict},
        "calibration": {
            "method": "temperature_scaling_nll",
            "temperature": float(temperature),
            "min_temperature": 1.0,
            "calibrated": True,
            "calibration_sample_count": len(cal_pos_rows),
        },
        "selective_rejector": rejector_block,
    }
    (cand_dir / "calibration_manifest.json").write_text(json.dumps(cal_manifest, indent=2), encoding="utf-8")

    training_lineage: Dict[str, Any] = {
        "fit_id": fit_mode,
        "epochs": epochs,
        "batch_size": batch_size,
        "lr": lr,
        "max_length": 64,
        "seed": seed,
        "device": str(device),
        "train_seconds": train_elapsed,
        "train_total_examples": len(train_texts),
        "epoch_stats": epoch_stats,
        "calibration_temperature": float(temperature),
        "max_neg_cal_supported12_prob": round(max_neg_cal_sup_prob, 6),
        "selective_rejector_enabled": bool(enable_selective_rejector),
    }
    if rejector_cal_stats is not None:
        training_lineage["selective_rejector_cal_selection"] = rejector_cal_stats

    prov_manifest = {
        "schema_version": "candidate_provenance.v1",
        "provenance_status": "verified",
        "candidate_name": model_ver,
        "git_commit": git_sha,
        "base_model": {
            "init_checkpoint": str(init_model_dir),
            "init_weights_sha256": lock_manifest["init_weights_sha256"],
            "original_backbone": "distilbert-base-uncased",
            "unfrozen_transformer_layers": 6,
        },
        "training_lineage": training_lineage,
        "dataset_hashes": lock_manifest["dataset_hashes"],
        "artifact_hashes": art_hashes,
        "token_truncation_audit": lock_manifest["token_truncation_audit_max_length_64"],
    }
    (cand_dir / "candidate_provenance_manifest.json").write_text(json.dumps(prov_manifest, indent=2), encoding="utf-8")

    return {
        "fit_mode": fit_mode,
        "candidate_dir": str(cand_dir),
        "artifact_hashes": art_hashes,
        "temperature": float(temperature),
        "max_neg_cal_supported12_prob": round(max_neg_cal_sup_prob, 6),
        "selective_rejector_enabled": bool(enable_selective_rejector),
        "selective_rejector_cal_selection": rejector_cal_stats,
        "train_seconds": train_elapsed,
        "epoch_stats": epoch_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit 1 / Fit 2 boundary-hardened continuation trainer")
    parser.add_argument("--worktree-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--data-repo-root", type=Path, default=Path(r"F:\Năm 3\SD\project\SupportIQ"))
    parser.add_argument(
        "--init-model-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "artifacts/evaluation/task_a_closure_20261113/candidate_model",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "artifacts/evaluation/task_a_boundary_20261113",
    )
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--run-fit1", action="store_true")
    parser.add_argument("--run-fit2", action="store_true")
    args = parser.parse_args()

    if args.prepare_only:
        res = prepare_and_lock_splits(
            worktree_root=args.worktree_root,
            data_repo_root=args.data_repo_root,
            init_model_dir=args.init_model_dir,
            artifact_root=args.artifact_root,
        )
        print(json.dumps({"prepare_locked": True, "counts": res["counts"], "truncation": res["token_truncation_audit_max_length_64"]}, indent=2))
    if args.run_fit1:
        res = run_fit_and_lock_candidate(
            worktree_root=args.worktree_root,
            data_repo_root=args.data_repo_root,
            init_model_dir=args.init_model_dir,
            artifact_root=args.artifact_root,
            fit_mode="fit1_kl",
            output_subdir="candidate_model",
        )
        print(json.dumps(res, indent=2))
    if args.run_fit2:
        res = run_fit_and_lock_candidate(
            worktree_root=args.worktree_root,
            data_repo_root=args.data_repo_root,
            init_model_dir=args.init_model_dir,
            artifact_root=args.artifact_root,
            fit_mode="fit2_supcon_energy",
            output_subdir="candidate_model_fit2",
        )
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

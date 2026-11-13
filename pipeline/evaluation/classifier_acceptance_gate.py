"""Independent candidate classifier comparison and acceptance gate (Task C).

Consumes an actual staged classifier directory, provenance manifest, and
optional train/calibration/evaluation group splits without touching Worker A's
training code. Enforces fail-closed checks for:
- Artifact SHA-256 identity & explicit training provenance lineage
- Strict 46-label bijection & 34-label escalation non-regression
- Disjoint train/calibration/eval template group isolation & zero gold overlap
- Independent group-isolated holdout evaluation
- OOD safety (0/80 leaks) & noise calibration
- Known acceptance regression suites (explicitly labeled as regression, NOT
  unseen holdout), separating correct-intent draft eligibility from raw count
  and enforcing strict mandatory-action compliance.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import (
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
    SUPPORTED_12_INTENTS,
    decide_route,
    load_policy_v2,
)
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.autoeval import metrics as M


KNOWN_UNINJECTED_ACCEPTANCE_IDS = {"unc-return_policy-04"}
KNOWN_UNINJECTED_FINAL_IDS = {"final-case-21"}
REQUIRED_PROVENANCE_FIELDS = ("training_lineage", "dataset_hashes", "base_model", "git_commit")


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def binary_top_label_brier(confidences: list[float], correctness: list[bool]) -> float:
    if not confidences:
        return 0.0
    return sum((c - (1.0 if y else 0.0)) ** 2 for c, y in zip(confidences, correctness)) / len(confidences)


def _extract_text(row: dict[str, Any]) -> str:
    return str(row.get("text") or row.get("query") or row.get("instruction") or "")


def _extract_intent(row: dict[str, Any]) -> str | None:
    return row.get("true_intent") or row.get("intent") or row.get("label")


def _extract_group(row: dict[str, Any]) -> str | None:
    for key in ("group_id", "template_group_id", "template_group", "family_id", "seed_id", "template_id"):
        if row.get(key) is not None:
            return str(row[key])
    return None


def audit_candidate_provenance(
    candidate_dir: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Verify physical artifact hashes, 46-label bijection, and declared lineage."""
    reasons: list[str] = []
    weights_file = candidate_dir / "model.safetensors"
    tokenizer_file = candidate_dir / "tokenizer.json"
    config_file = candidate_dir / "config.json"

    files_info: dict[str, Any] = {}
    for label, p in (("weights", weights_file), ("tokenizer", tokenizer_file), ("config", config_file)):
        if p.exists():
            files_info[label] = {
                "path": str(p),
                "exists": True,
                "sha256": compute_file_sha256(p),
                "size_bytes": p.stat().st_size,
            }
        else:
            files_info[label] = {"path": str(p), "exists": False, "sha256": None, "size_bytes": None}
            reasons.append(f"missing_artifact_file:{label}")

    bijection_valid = False
    num_labels = 0
    if config_file.exists():
        cfg = json.loads(config_file.read_text(encoding="utf-8"))
        id2label = {int(k): v for k, v in (cfg.get("id2label") or {}).items()}
        num_labels = len(id2label)
        bijection_valid = (
            len(id2label) == 46
            and set(id2label.keys()) == set(range(46))
            and set(id2label.values()) == set(STANDARD_INTENTS_46)
        )
        if not bijection_valid:
            reasons.append("invalid_46_label_bijection")

    manifest_data: dict[str, Any] | None = None
    if manifest_path is None or not manifest_path.exists():
        reasons.append("missing_or_unverified_provenance")
    else:
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            reasons.append("invalid_provenance_manifest_json")
            manifest_data = None

    if manifest_data is not None:
        status = str(manifest_data.get("provenance_status", "")).lower()
        if status in {"unknown", "unverified", "missing"}:
            reasons.append("missing_or_unverified_provenance")
        for req_field in REQUIRED_PROVENANCE_FIELDS:
            val = manifest_data.get(req_field)
            if not val:
                reasons.append(f"missing_provenance_field:{req_field}")
        declared_hashes = manifest_data.get("artifact_hashes")
        if not isinstance(declared_hashes, dict) or not declared_hashes:
            reasons.append("missing_provenance_artifact_hashes")
        else:
            for key, file_key in (("model.safetensors", "weights"), ("tokenizer.json", "tokenizer"), ("config.json", "config")):
                exp_hash = declared_hashes.get(key)
                actual_hash = files_info[file_key].get("sha256")
                if not exp_hash:
                    reasons.append(f"missing_artifact_hash:{key}")
                elif actual_hash and str(exp_hash).lower() != str(actual_hash).lower():
                    reasons.append(f"artifact_hash_mismatch:{key}")

    return {
        "candidate_dir": str(candidate_dir),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "files": files_info,
        "valid_46_label_bijection": bijection_valid,
        "num_labels": num_labels,
        "provenance_passed": len(reasons) == 0,
        "failure_reasons": reasons,
        "manifest": manifest_data,
    }


def _is_finite_number(val: Any) -> bool:
    return type(val) in (int, float) and not isinstance(val, bool) and math.isfinite(float(val))


def _is_valid_positive_temperature(val: Any) -> bool:
    return _is_finite_number(val) and float(val) > 0.0


def _validate_rejector_schema(rejector: Any) -> list[str]:
    """Validate experimental rejector parameters fail-closed at manifest load time."""
    if not isinstance(rejector, dict):
        return ["invalid_rejector_schema"]
    if rejector.get("enabled") is not None and not isinstance(rejector.get("enabled"), bool):
        return ["invalid_rejector_enabled_flag"]

    r_type = str(rejector.get("type") or rejector.get("kind") or "logistic_features").lower()
    reasons: list[str] = []

    if r_type == "logistic_regression_v1":
        spec = str(rejector.get("feature_spec", ""))
        expected_dims = {"cls_l2_plus_logit_geometry_v1": 776, "logit_geometry_v1": 8}
        if spec not in expected_dims:
            reasons.append(f"unsupported_rejector_feature_spec:{spec}")
            return reasons
        exp_dim = expected_dims[spec]
        fdim = rejector.get("feature_dim")
        if type(fdim) is not int or fdim != exp_dim:
            reasons.append("invalid_rejector_feature_dim")
        for vec_name in ("scaler_mean", "scaler_scale", "weights"):
            vec = rejector.get(vec_name)
            if not isinstance(vec, list) or len(vec) != exp_dim or not all(_is_finite_number(x) for x in vec):
                reasons.append(f"invalid_rejector_vector:{vec_name}")
            elif vec_name == "scaler_scale" and any(float(x) <= 0.0 for x in vec):
                reasons.append("invalid_rejector_non_positive_scaler_scale")
        if not _is_finite_number(rejector.get("bias")):
            reasons.append("invalid_rejector_bias")
        thr = rejector.get("threshold")
        if not _is_finite_number(thr) or not (0.0 <= float(thr) <= 1.0):
            reasons.append("invalid_rejector_threshold")
        return reasons

    if r_type in {"logistic_features", "logistic", "linear"} and isinstance(rejector.get("weights"), dict):
        weights = rejector["weights"]
        if not weights or not all(_is_finite_number(v) for v in weights.values()):
            reasons.append("invalid_rejector_weights")
        if "bias" in rejector and not _is_finite_number(rejector.get("bias")):
            reasons.append("invalid_rejector_bias")
        if "threshold" in rejector and not _is_finite_number(rejector.get("threshold")):
            reasons.append("invalid_rejector_threshold")
        return reasons

    if r_type in {"threshold", "metric_threshold"}:
        if "threshold" not in rejector or not _is_finite_number(rejector.get("threshold")):
            reasons.append("invalid_rejector_threshold")
        return reasons

    return [f"unsupported_rejector_type:{r_type}"]


def validate_calibration_manifest(
    candidate_dir: Path,
    calibration_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Fail-closed validation of optional calibration_manifest.json and experimental rejector config."""
    path = calibration_manifest_path or (candidate_dir / "calibration_manifest.json")
    if not path.exists():
        return {
            "present": False,
            "path": str(path),
            "valid": True,
            "failure_reasons": [],
            "temperature": 1.0,
            "calibrated": False,
            "rejector": None,
            "manifest": None,
        }

    reasons: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "present": True,
            "path": str(path),
            "valid": False,
            "failure_reasons": ["invalid_calibration_manifest_json"],
            "temperature": None,
            "calibrated": False,
            "rejector": None,
            "manifest": None,
        }

    if not isinstance(data, dict) or not data.get("schema_version"):
        reasons.append("missing_calibration_schema_version")
    schema_version = str(data.get("schema_version", "")) if isinstance(data, dict) else ""

    temp_val: float | None = None
    calibrated_flag = False
    if isinstance(data, dict) and "calibration" in data:
        cal_block = data.get("calibration")
        if not isinstance(cal_block, dict):
            reasons.append("invalid_calibration_section")
        else:
            temp = cal_block.get("temperature")
            min_temp = cal_block.get("min_temperature", 1.0)
            if not _is_valid_positive_temperature(temp):
                reasons.append("invalid_non_positive_or_non_finite_temperature")
            elif not _is_finite_number(min_temp) or float(temp) < float(min_temp):
                reasons.append("temperature_below_min_temperature")
            else:
                temp_val = float(temp)
            raw_cal_flag = cal_block.get("calibrated", True)
            if not isinstance(raw_cal_flag, bool):
                reasons.append("invalid_calibrated_flag")
            else:
                calibrated_flag = raw_cal_flag
    else:
        temp = data.get("temperature", 1.0) if isinstance(data, dict) else None
        if not _is_valid_positive_temperature(temp):
            reasons.append("invalid_non_positive_or_non_finite_temperature")
        else:
            temp_val = float(temp)
        raw_cal_flag = data.get("calibrated", temp_val is not None and temp_val != 1.0) if isinstance(data, dict) else False
        if not isinstance(raw_cal_flag, bool):
            reasons.append("invalid_calibrated_flag")
        else:
            calibrated_flag = raw_cal_flag

    cfg_file = candidate_dir / "config.json"
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        id2label = {int(k): v for k, v in (cfg.get("id2label") or {}).items()}
        bijection_ok = (
            len(id2label) == 46
            and set(id2label.keys()) == set(range(46))
            and set(id2label.values()) == set(STANDARD_INTENTS_46)
        )
        if not bijection_ok:
            reasons.append("calibration_invalid_46_label_bijection")

    if isinstance(data, dict) and ("label_space" in data or schema_version == "selective_calibration.v1"):
        lspace = data.get("label_space")
        if not isinstance(lspace, dict):
            reasons.append("calibration_invalid_label_space")
        else:
            ls_map = lspace.get("id2label")
            mapped = [ls_map.get(str(i)) for i in range(46)] if isinstance(ls_map, dict) else []
            if (
                lspace.get("num_labels") != 46
                or lspace.get("valid_46_label_bijection") is not True
                or mapped != list(STANDARD_INTENTS_46)
            ):
                reasons.append("calibration_invalid_label_space")

    artifact_hashes = data.get("artifact_hashes") if isinstance(data, dict) else None
    if artifact_hashes is not None and not isinstance(artifact_hashes, dict):
        reasons.append("invalid_artifact_hashes_schema")
        artifact_hashes = None
    if schema_version == "selective_calibration.v1" and not artifact_hashes:
        reasons.append("missing_calibration_artifact_hashes")

    for field, fname in (
        ("weights_sha256", "model.safetensors"),
        ("tokenizer_sha256", "tokenizer.json"),
        ("config_sha256", "config.json"),
    ):
        decl = data.get(field) if isinstance(data, dict) else None
        if decl is None and isinstance(artifact_hashes, dict):
            decl = artifact_hashes.get(fname)
        fpath = candidate_dir / fname
        if decl is not None:
            if not fpath.exists():
                reasons.append(f"calibration_missing_file:{fname}")
            elif compute_file_sha256(fpath) != str(decl).lower():
                reasons.append(f"calibration_hash_mismatch:{field}")
        elif schema_version == "selective_calibration.v1":
            reasons.append(f"missing_calibration_hash:{fname}")

    rejector = (data.get("selective_rejector") or data.get("rejector")) if isinstance(data, dict) else None
    if schema_version == "selective_calibration.v1" and rejector is None:
        reasons.append("missing_selective_rejector")
    elif rejector is not None:
        reasons.extend(_validate_rejector_schema(rejector))

    return {
        "present": True,
        "path": str(path),
        "valid": len(reasons) == 0,
        "failure_reasons": sorted(set(reasons)),
        "temperature": temp_val,
        "calibrated": calibrated_flag,
        "rejector": rejector if (isinstance(rejector, dict) and not any("rejector" in r for r in reasons)) else None,
        "manifest": data,
    }


def compute_selective_coverage_metrics(
    *,
    raw_draft: int,
    correct_draft: int,
    abstain_count: int,
    escalate_count: int,
    total: int,
) -> dict[str, Any]:
    """Recompute denominator, correct-intent draft eligibility, precision among eligible, and abstention coverage."""
    precision = round(correct_draft / raw_draft, 6) if raw_draft > 0 else None
    non_draft = abstain_count + escalate_count
    return {
        "denominator": total,
        "raw_draft_eligible_count": raw_draft,
        "raw_draft_eligible_rate": round(raw_draft / total, 6) if total else 0.0,
        "correct_intent_draft_eligible_count": correct_draft,
        "correct_intent_draft_eligible_rate": round(correct_draft / total, 6) if total else 0.0,
        "wrong_intent_draft_eligible_count": max(0, raw_draft - correct_draft),
        "precision_numerator_correct_intent_draft_eligible": correct_draft,
        "precision_denominator_raw_draft_eligible": raw_draft,
        "precision_among_draft_eligible": precision,
        "abstain_count": abstain_count,
        "escalate_count": escalate_count,
        "abstention_and_escalation_count": non_draft,
        "abstention_coverage": round(non_draft / total, 6) if total else 0.0,
        "no_invented_accuracy_from_abstentions": True,
    }


def check_split_isolation_and_gold_contamination(
    *,
    train_rows: list[dict[str, Any]] | None,
    calibration_rows: list[dict[str, Any]] | None,
    eval_rows: list[dict[str, Any]] | None,
    gold_texts: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """Verify train/calibration/eval group isolation and zero gold benchmark contamination."""
    reasons: list[str] = []

    if not eval_rows:
        reasons.append("missing_group_isolated_holdout")
        return {
            "passed": False,
            "failure_reasons": reasons,
            "counts": {
                "train": len(train_rows or []),
                "calibration": len(calibration_rows or []),
                "eval": 0,
            },
            "group_overlaps": {},
            "text_overlaps": {},
            "gold_exact_matches": [],
            "gold_high_jaccard_matches": [],
        }

    splits = {
        "train": train_rows or [],
        "calibration": calibration_rows or [],
        "eval": eval_rows,
    }

    split_groups: dict[str, set[str]] = {}
    missing_group_splits: list[str] = []
    for name, rows in splits.items():
        if not rows:
            continue
        groups = [_extract_group(r) for r in rows]
        if any(g is None for g in groups):
            missing_group_splits.append(name)
        split_groups[name] = {g for g in groups if g is not None}

    if missing_group_splits:
        reasons.append(f"missing_group_ids:{','.join(missing_group_splits)}")

    group_overlaps: dict[str, list[str]] = {}
    for a, b in (("train", "calibration"), ("train", "eval"), ("calibration", "eval")):
        ov = sorted(split_groups.get(a, set()) & split_groups.get(b, set()))
        group_overlaps[f"{a}_vs_{b}"] = ov
        if ov:
            reasons.append(f"template_group_overlap:{a}_vs_{b}")

    split_norms: dict[str, set[str]] = {
        name: {normalize_text(_extract_text(r)) for r in rows if normalize_text(_extract_text(r))}
        for name, rows in splits.items()
    }
    text_overlaps: dict[str, int] = {}
    for a, b in (("train", "calibration"), ("train", "eval"), ("calibration", "eval")):
        ov_texts = split_norms.get(a, set()) & split_norms.get(b, set())
        text_overlaps[f"{a}_vs_{b}"] = len(ov_texts)
        if ov_texts:
            reasons.append(f"split_text_overlap:{a}_vs_{b}")

    gold_by_norm: dict[str, list[tuple[str, str]]] = defaultdict(list)
    gold_tokens: list[tuple[str, str, set[str]]] = []
    for suite_name, case_id, gtext in gold_texts:
        gn = normalize_text(gtext)
        if gn:
            gold_by_norm[gn].append((suite_name, case_id))
            gtoks = token_set(gtext)
            if len(gtoks) >= 4:
                gold_tokens.append((suite_name, case_id, gtoks))

    gold_exact_matches: list[dict[str, str]] = []
    gold_high_jaccard_matches: list[dict[str, Any]] = []
    for split_name, rows in splits.items():
        for idx, row in enumerate(rows):
            raw_text = _extract_text(row)
            norm = normalize_text(raw_text)
            if norm in gold_by_norm:
                for suite_name, case_id in gold_by_norm[norm]:
                    gold_exact_matches.append(
                        {"split": split_name, "row_index": str(idx), "gold_suite": suite_name, "gold_case_id": case_id}
                    )
            rtoks = token_set(raw_text)
            if len(rtoks) >= 4:
                for suite_name, case_id, gtoks in gold_tokens:
                    union = rtoks | gtoks
                    jac = len(rtoks & gtoks) / len(union) if union else 0.0
                    if jac >= 0.90:
                        gold_high_jaccard_matches.append(
                            {
                                "split": split_name,
                                "row_index": idx,
                                "gold_suite": suite_name,
                                "gold_case_id": case_id,
                                "jaccard": round(jac, 4),
                            }
                        )

    if gold_exact_matches:
        reasons.append("gold_benchmark_contamination_exact")
    if gold_high_jaccard_matches:
        reasons.append("gold_benchmark_contamination_near_duplicate")

    return {
        "passed": len(reasons) == 0,
        "failure_reasons": sorted(set(reasons)),
        "counts": {k: len(v) for k, v in splits.items()},
        "group_counts": {k: len(v) for k, v in split_groups.items()},
        "group_overlaps": group_overlaps,
        "text_overlaps": text_overlaps,
        "gold_exact_matches": gold_exact_matches[:20],
        "gold_high_jaccard_matches": gold_high_jaccard_matches[:20],
    }


def _evaluate_experimental_rejector(
    rejector: dict[str, Any] | None,
    logits: Any,
    raw_probs: list[float],
    cal_probs: list[float],
    cls_embedding: Any = None,
) -> tuple[bool, float | None]:
    """Evaluate a separate experimental rejection adapter without altering intent probabilities."""
    if not rejector:
        return False, None
    if rejector.get("enabled") is False:
        return False, None

    r_type = str(rejector.get("type") or rejector.get("kind") or "logistic_features").lower()
    if r_type == "logistic_regression_v1":
        logits_np = (
            logits.detach().cpu().numpy().astype(np.float64)
            if isinstance(logits, torch.Tensor)
            else np.asarray(logits, dtype=np.float64)
        )
        raw_np = np.asarray(raw_probs, dtype=np.float64)
        cal_np = np.asarray(cal_probs, dtype=np.float64)
        raw_sorted = np.sort(raw_np)[::-1]
        cal_sorted = np.sort(cal_np)[::-1]
        raw_max_prob = float(raw_sorted[0])
        raw_margin = float(raw_sorted[0] - raw_sorted[1]) if len(raw_sorted) > 1 else 0.0
        raw_entropy = float(-(raw_np * np.log(np.clip(raw_np, 1e-12, None))).sum())
        cal_max_prob = float(cal_sorted[0])
        cal_margin = float(cal_sorted[0] - cal_sorted[1]) if len(cal_sorted) > 1 else 0.0
        cal_entropy = float(-(cal_np * np.log(np.clip(cal_np, 1e-12, None))).sum())
        logit_max = float(logits_np.max())
        logit_shift = logits_np - logit_max
        logit_lse = float(logit_max + np.log(np.clip(np.exp(logit_shift).sum(), 1e-12, None)))
        geom = np.array(
            [
                raw_max_prob,
                raw_margin,
                raw_entropy,
                cal_max_prob,
                cal_margin,
                cal_entropy,
                logit_max,
                logit_lse,
            ],
            dtype=np.float64,
        )
        spec = str(rejector.get("feature_spec", ""))
        if spec == "logit_geometry_v1":
            feats = geom
        elif spec == "cls_l2_plus_logit_geometry_v1":
            if cls_embedding is None:
                raise ValueError("cls_embedding required for cls_l2_plus_logit_geometry_v1 rejector")
            cls_np = (
                cls_embedding.detach().cpu().numpy().astype(np.float64)
                if isinstance(cls_embedding, torch.Tensor)
                else np.asarray(cls_embedding, dtype=np.float64)
            )
            norm = max(float(np.linalg.norm(cls_np, ord=2)), 1e-12)
            feats = np.concatenate([cls_np / norm, geom])
        else:
            raise ValueError(f"Unsupported logistic_regression_v1 feature_spec: {spec!r}")

        mean = np.asarray(rejector["scaler_mean"], dtype=np.float64)
        scale = np.clip(np.asarray(rejector["scaler_scale"], dtype=np.float64), 1e-12, None)
        weights = np.asarray(rejector["weights"], dtype=np.float64)
        bias = float(rejector["bias"])
        threshold = float(rejector["threshold"])
        z = float(np.dot((feats - mean) / scale, weights) + bias)
        z = max(-40.0, min(40.0, z))
        in_scope_prob = 1.0 / (1.0 + math.exp(-z))
        return in_scope_prob < threshold, round(in_scope_prob, 6)

    ranked_raw = sorted(raw_probs, reverse=True)
    ranked_cal = sorted(cal_probs, reverse=True)
    eps = 1e-12
    cal_entropy = -sum(p * math.log(max(p, eps)) for p in cal_probs if p > 0.0)
    raw_entropy = -sum(p * math.log(max(p, eps)) for p in raw_probs if p > 0.0)
    top_logit = float(torch.max(logits).item())
    second_logit = float(torch.topk(logits, k=2).values[1].item()) if len(raw_probs) >= 2 else 0.0

    feature_map = {
        "max_prob": float(ranked_cal[0]),
        "calibrated_max_prob": float(ranked_cal[0]),
        "raw_max_prob": float(ranked_raw[0]),
        "margin": float(ranked_cal[0] - (ranked_cal[1] if len(ranked_cal) > 1 else 0.0)),
        "calibrated_margin": float(ranked_cal[0] - (ranked_cal[1] if len(ranked_cal) > 1 else 0.0)),
        "raw_margin": float(ranked_raw[0] - (ranked_raw[1] if len(ranked_raw) > 1 else 0.0)),
        "entropy": float(cal_entropy),
        "calibrated_entropy": float(cal_entropy),
        "raw_entropy": float(raw_entropy),
        "max_logit": top_logit,
        "logit_margin": float(top_logit - second_logit),
    }

    if r_type in {"logistic_features", "logistic", "linear"} and isinstance(rejector.get("weights"), dict):
        score = float(rejector.get("bias", 0.0))
        for fname, w in rejector["weights"].items():
            score += float(w) * float(feature_map.get(fname, 0.0))
        if r_type != "linear" and rejector.get("apply_sigmoid", True):
            score = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, score))))
        threshold = float(rejector.get("threshold", 0.5))
        # Convention: reject_when == "below" rejects in-scope when score < threshold; "above" rejects when anomaly score >= threshold.
        if str(rejector.get("reject_when", "below")).lower() == "above":
            return score >= threshold, round(score, 6)
        return score < threshold, round(score, 6)

    if r_type in {"threshold", "metric_threshold"}:
        metric_name = str(rejector.get("metric", "max_logit"))
        score = float(feature_map.get(metric_name, 0.0))
        threshold = float(rejector.get("threshold", 0.0))
        if str(rejector.get("reject_when", "below")).lower() == "above":
            return score >= threshold, round(score, 6)
        return score < threshold, round(score, 6)

    raise ValueError(f"Unsupported experimental rejector schema: {rejector!r}")


class GateSequenceClassifier:
    """Loaded safetensors sequence classifier implementing Engine's model interface."""

    def __init__(
        self,
        name: str,
        model_dir: Path,
        *,
        temperature: float = 1.0,
        calibrated: bool = False,
        rejector: dict[str, Any] | None = None,
        rejector_fn: Callable[[dict[str, Any]], tuple[bool, float | None]] | None = None,
    ):
        if not _is_valid_positive_temperature(temperature):
            raise ValueError(f"temperature must be finite positive, got {temperature!r}")
        self.name = name
        self.model_dir = model_dir
        self.temperature = float(temperature)
        self.calibrated = bool(calibrated)
        self.rejector = rejector
        self.rejector_fn = rejector_fn
        self.last_prediction: dict[str, Any] | None = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        cfg = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        self.id2label = {int(k): v for k, v in cfg["id2label"].items()}
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        self.model.eval()
        self.model.to(self.device)
        self.verified_model_version = name
        self.model_version = name
        self.model_mode = "trained"
        self.verified = True

    def predict(self, text: str, top_k_count: int = 5) -> dict[str, Any]:
        inputs = self.tokenizer(
            text, max_length=64, padding="max_length", truncation=True, return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        need_cls = bool(self.rejector and str(self.rejector.get("feature_spec", "")).startswith("cls_"))
        cls_embedding = None
        with torch.inference_mode():
            outputs = self.model(**inputs, output_hidden_states=True) if need_cls else self.model(**inputs)
            logits = outputs.logits[0]
            if need_cls:
                cls_embedding = outputs.hidden_states[-1][0, 0, :]
            raw_probs = torch.softmax(logits, dim=-1).cpu().tolist()
            if self.calibrated:
                cal_probs = torch.softmax(logits / self.temperature, dim=-1).cpu().tolist()
                score_kind = "calibrated_probability"
            else:
                cal_probs = list(raw_probs)
                score_kind = "uncalibrated_softmax"

        raw_ranked = sorted(range(len(raw_probs)), key=lambda i: raw_probs[i], reverse=True)
        ranked = sorted(range(len(cal_probs)), key=lambda i: cal_probs[i], reverse=True)
        top1_idx, top2_idx = ranked[0], ranked[1]
        raw1_idx, raw2_idx = raw_ranked[0], raw_ranked[1]
        top_k = [{"intent": self.id2label[i], "probability": float(cal_probs[i])} for i in ranked[:top_k_count]]

        rejected = False
        rejection_score: float | None = None
        if self.rejector_fn is not None:
            rejected, rejection_score = self.rejector_fn(
                {
                    "text": text,
                    "logits": logits,
                    "raw_probs": raw_probs,
                    "calibrated_probs": cal_probs,
                    "intent": self.id2label[top1_idx],
                    "confidence": float(cal_probs[top1_idx]),
                    "margin": float(cal_probs[top1_idx] - cal_probs[top2_idx]),
                }
            )
        elif self.rejector is not None:
            rejected, rejection_score = _evaluate_experimental_rejector(
                self.rejector, logits, raw_probs, cal_probs, cls_embedding=cls_embedding
            )

        result = {
            "intent": self.id2label[top1_idx],
            "confidence": float(cal_probs[top1_idx]),
            "margin": float(cal_probs[top1_idx] - cal_probs[top2_idx]),
            "raw_intent": self.id2label[raw1_idx],
            "raw_confidence": float(raw_probs[raw1_idx]),
            "raw_margin": float(raw_probs[raw1_idx] - raw_probs[raw2_idx]),
            "raw_score_kind": "uncalibrated_softmax",
            "top_k": top_k,
            "score_kind": score_kind,
            "temperature": self.temperature if self.calibrated else 1.0,
            "rejected_by_experimental_adapter": bool(rejected),
            "selective_accepted": (not bool(rejected)) if (self.rejector or self.rejector_fn) else None,
            "rejection_score": rejection_score,
            "rejector_decision": ("reject" if rejected else "accept") if (self.rejector or self.rejector_fn) else None,
            "model_mode": "trained",
            "verified": True,
        }
        self.last_prediction = result
        return result


class _OfflineGateSpyLLM:
    def generate(self, *args, **kwargs):
        raise AssertionError("Classifier gate must never invoke live or external LLM generation")


def _build_engine(model: GateSequenceClassifier, repo_root: Path) -> tuple[Engine, Any]:
    policy_path = repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy_v2 = load_policy_v2(str(policy_path))
    release = json.loads((repo_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(doc["document_id"], doc["version"]) for doc in release["documents"]}
    retriever = RetrievalAdapter(allowed_document_versions=allowed)
    engine = Engine(
        model,
        retriever,
        _OfflineGateSpyLLM(),
        {"release_id": f"gate-{model.name}", "model_version": model.name},
        policy,
    )
    return engine, policy_v2


def _adapt_action(rec: str) -> str:
    return {"draft": "retrieve_draft", "abstain": "manual_fallback", "escalate": "escalate"}.get(rec, "manual_fallback")


def _apply_adapter_routing_guard(action: str, pred: dict[str, Any] | None) -> tuple[str, bool]:
    """Experimental rejector can veto draft eligibility to manual_fallback without altering intent probability."""
    if pred and pred.get("rejected_by_experimental_adapter") and action == "retrieve_draft":
        return "manual_fallback", True
    return action, False


class _SpyRejectedModel:
    """Offline spy returning high-confidence supported intent alongside experimental rejector veto."""

    verified = True
    model_mode = "trained"
    model_version = "spy-experimental-rejector"

    def predict(self, text: str, top_k_count: int = 5) -> dict[str, Any]:
        return {
            "intent": "return_policy",
            "confidence": 0.95,
            "margin": 0.90,
            "top_k": [
                {"intent": "return_policy", "probability": 0.95},
                {"intent": "track_order", "probability": 0.05},
            ],
            "score_kind": "calibrated_probability",
            "temperature": 1.25,
            "rejected_by_experimental_adapter": True,
            "selective_accepted": False,
            "rejector_decision": "reject",
            "model_mode": "trained",
            "verified": True,
        }


class _SpyValidRetriever:
    """Offline deterministic retriever so Engine._analyse tests rejection flags without encoder downloads."""

    def __init__(self, eligible_versions: list[Any]):
        self.eligible_versions = eligible_versions
        self.relevance_threshold = 0.55

    def retrieve(self, query: str, intent: str, *, role: str = "agent", current_time: Any = None) -> dict[str, Any]:
        return {
            "evidence": [
                {
                    "document_id": "POL-RET-001",
                    "version": "1",
                    "title": "Return Policy",
                    "excerpt": "Tiki Trading items may be returned within 30 days under standard conditions.",
                    "score": 0.95,
                }
            ],
            "has_conflict": False,
            "reason_codes": [],
        }


def verify_engine_rejection_enforcement(repo_root: Path) -> dict[str, Any]:
    """Check whether Engine._analyse enforces experimental rejector flags vs harness guard."""
    spy = _SpyRejectedModel()
    policy_path = repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    engine = Engine(
        spy,
        _SpyValidRetriever([]),
        _OfflineGateSpyLLM(),
        {"release_id": "gate-spy-rejection-check", "model_version": spy.model_version},
        policy,
    )
    ans, _ = engine._analyse(
        {
            "message": "What is the standard return window for Tiki Trading items?",
            "as_of": "2026-11-13T00:00:00Z",
            "order_context": {},
        }
    )
    raw_rec = ans["routing"]["recommendation"]
    raw_engine_action = _adapt_action(raw_rec)
    guarded_action, vetoed = _apply_adapter_routing_guard(raw_engine_action, spy.predict("x"))
    return {
        "checked": True,
        "raw_engine_recommendation_on_rejected_spy": raw_rec,
        "raw_engine_action_on_rejected_spy": raw_engine_action,
        "engine_enforces_experimental_rejection": raw_engine_action == "manual_fallback",
        "harness_guarded_action_on_rejected_spy": guarded_action,
        "harness_guard_vetoed": vetoed,
        "distinction_note": (
            "ModelContainer parity verifies tokenization, 46-label bijection, temperature scaling, and score_kind. "
            "Engine._analyse enforcement of rejected_by_experimental_adapter/selective_accepted is measured separately "
            "from score parity; when False, experimental rejector vetoes occur only in Task C's _apply_adapter_routing_guard."
        ),
    }


def verify_runtime_score_parity(
    serving_dir: Path,
    probe_texts: list[str] | None = None,
    probe_temperature: float = 1.25,
    unpinned_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Compare GateSequenceClassifier against ModelContainer tokenization, score_kind, calibration, and fail-closed loading."""
    from apps.ml_inference.app import ModelContainer

    texts = probe_texts or [
        "How do I return a Tiki Trading item within 30 days?",
        "Where is my package right now?",
        "I want a human manager to refund my damaged camera.",
        "Can you recommend a coffee recipe?",
    ]
    if not serving_dir.exists() or not (serving_dir / "model.safetensors").exists():
        return {"checked": False, "passed": False, "reason": f"serving_dir_missing:{serving_dir}"}

    mc = ModelContainer()
    mc.load(serving_dir)
    if not mc.is_trained_ready():
        return {"checked": True, "passed": False, "reason": "model_container_not_ready_for_serving"}

    gate_raw = GateSequenceClassifier("parity-serving-raw", serving_dir, temperature=1.0, calibrated=False)
    gate_cal = GateSequenceClassifier("parity-serving-cal", serving_dir, temperature=probe_temperature, calibrated=True)

    max_raw_conf_diff = 0.0
    max_cal_conf_diff = 0.0
    max_raw_margin_diff = 0.0
    max_cal_margin_diff = 0.0
    token_mismatches = 0
    label_mismatches = 0
    score_kind_mismatches = 0

    for txt in texts:
        mc_tok = mc.tokenizer(txt, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
        gate_tok = gate_raw.tokenizer(txt, max_length=64, padding="max_length", truncation=True, return_tensors="pt")
        if not torch.equal(mc_tok["input_ids"], gate_tok["input_ids"]) or not torch.equal(
            mc_tok["attention_mask"], gate_tok["attention_mask"]
        ):
            token_mismatches += 1

        mc_raw = mc.predict(txt, top_k_count=5, calibrated=False)
        gr = gate_raw.predict(txt, top_k_count=5)
        if mc_raw["intent"] != gr["intent"]:
            label_mismatches += 1
        if mc_raw["score_kind"] != gr["score_kind"]:
            score_kind_mismatches += 1
        max_raw_conf_diff = max(max_raw_conf_diff, abs(float(mc_raw["confidence"]) - float(gr["confidence"])))
        max_raw_margin_diff = max(max_raw_margin_diff, abs(float(mc_raw["margin"]) - float(gr["margin"])))

        mc_cal = mc.predict(txt, top_k_count=5, temperature=probe_temperature, calibrated=True)
        gc = gate_cal.predict(txt, top_k_count=5)
        if mc_cal["intent"] != gc["intent"]:
            label_mismatches += 1
        if mc_cal["score_kind"] != gc["score_kind"]:
            score_kind_mismatches += 1
        max_cal_conf_diff = max(max_cal_conf_diff, abs(float(mc_cal["confidence"]) - float(gc["confidence"])))
        max_cal_margin_diff = max(max_cal_margin_diff, abs(float(mc_cal["margin"]) - float(gc["margin"])))

    fail_closed_unpinned_ok: bool | None = None
    if unpinned_dir is not None and unpinned_dir.exists() and unpinned_dir.resolve() != serving_dir.resolve():
        mc_cand = ModelContainer()
        mc_cand.load(unpinned_dir)
        fail_closed_unpinned_ok = (not mc_cand.is_ready()) and (not mc_cand.verified)

    passed = (
        mc.validate_label_bijection()
        and token_mismatches == 0
        and label_mismatches == 0
        and score_kind_mismatches == 0
        and max_raw_conf_diff < 1e-5
        and max_cal_conf_diff < 1e-5
        and max_raw_margin_diff < 1e-5
        and max_cal_margin_diff < 1e-5
        and (fail_closed_unpinned_ok in (None, True))
    )
    engine_rejection = verify_engine_rejection_enforcement(repo_root) if repo_root is not None else None
    return {
        "checked": True,
        "passed": passed,
        "probe_count": len(texts),
        "probe_temperature": probe_temperature,
        "tokenization_mismatches": token_mismatches,
        "label_mismatches": label_mismatches,
        "score_kind_mismatches": score_kind_mismatches,
        "max_raw_confidence_abs_diff": round(max_raw_conf_diff, 10),
        "max_raw_margin_abs_diff": round(max_raw_margin_diff, 10),
        "max_calibrated_confidence_abs_diff": round(max_cal_conf_diff, 10),
        "max_calibrated_margin_abs_diff": round(max_cal_margin_diff, 10),
        "fail_closed_non_serving_checksum": fail_closed_unpinned_ok,
        "engine_rejection_enforcement": engine_rejection,
    }


def evaluate_model_on_suites(
    model_name: str,
    model_dir: Path,
    repo_root: Path,
    holdout_rows: list[dict[str, Any]] | None = None,
    *,
    temperature: float = 1.0,
    calibrated: bool = False,
    rejector: dict[str, Any] | None = None,
    rejector_fn: Callable[[dict[str, Any]], tuple[bool, float | None]] | None = None,
) -> dict[str, Any]:
    """Evaluate a model across independent holdout (if given), OOD, noise, and known regression suites."""
    clf = GateSequenceClassifier(
        model_name,
        model_dir,
        temperature=temperature,
        calibrated=calibrated,
        rejector=rejector,
        rejector_fn=rejector_fn,
    )
    engine, policy_v2 = _build_engine(clf, repo_root)

    def _run_holdout(rows: list[dict[str, Any]]) -> dict[str, Any]:
        y_true, y_pred, confs, corr = [], [], [], []
        s34_true, s34_pred = [], []
        s12_true, s12_pred = [], []
        s12_raw_draft = 0
        s12_correct_draft = 0
        s12_abstain = 0
        s12_escalate = 0
        s34_unsafe_draft = 0
        adapter_rejected = 0

        for row in rows:
            txt = _extract_text(row)
            gold = _extract_intent(row)
            pred = clf.predict(txt)
            plabel = pred["intent"]
            pconf = pred["confidence"]
            y_true.append(gold)
            y_pred.append(plabel)
            confs.append(pconf)
            corr.append(plabel == gold)

            dec = decide_route(
                IntentPrediction(intent=plabel, confidence=pconf, margin=pred["margin"], model_version=model_name),
                RoutingContext(ticket_customer_id="gate-eval", extracted_slots={}, is_personal_lookup=False),
                policy_v2,
            )
            eff_action, vetoed = _apply_adapter_routing_guard(dec.action, pred)
            if vetoed:
                adapter_rejected += 1
            if gold in ESCALATED_34_INTENTS:
                s34_true.append(gold)
                s34_pred.append(plabel)
                if eff_action == "retrieve_draft":
                    s34_unsafe_draft += 1
            elif gold in SUPPORTED_12_INTENTS:
                s12_true.append(gold)
                s12_pred.append(plabel)
                if eff_action == "retrieve_draft":
                    s12_raw_draft += 1
                    if plabel == gold:
                        s12_correct_draft += 1
                elif eff_action == "escalate":
                    s12_escalate += 1
                else:
                    s12_abstain += 1

        return {
            "suite_role": "independent_group_isolated_holdout",
            "n_total": len(rows),
            "accuracy_46": M.accuracy(y_true, y_pred) if y_true else 0.0,
            "macro_f1_46": M.macro_f1(y_true, y_pred, labels=STANDARD_INTENTS_46) if y_true else 0.0,
            "ece_10bin": M.expected_calibration_error(confs, corr, n_bins=10)[0] if confs else 0.0,
            "binary_top_label_brier": binary_top_label_brier(confs, corr),
            "rejected_by_experimental_adapter_count": adapter_rejected,
            "escalated_34": {
                "n": len(s34_true),
                "accuracy": M.accuracy(s34_true, s34_pred) if s34_true else 0.0,
                "macro_f1": M.macro_f1(s34_true, s34_pred, labels=ESCALATED_34_INTENTS) if s34_true else 0.0,
                "unsafe_draft_eligible_count": s34_unsafe_draft,
            },
            "supported_12": {
                "n": len(s12_true),
                "accuracy": M.accuracy(s12_true, s12_pred) if s12_true else 0.0,
                "macro_f1": M.macro_f1(s12_true, s12_pred, labels=SUPPORTED_12_INTENTS) if s12_true else 0.0,
                "raw_draft_eligible_count": s12_raw_draft,
                "correct_intent_draft_eligible_count": s12_correct_draft,
                "selective_metrics": compute_selective_coverage_metrics(
                    raw_draft=s12_raw_draft,
                    correct_draft=s12_correct_draft,
                    abstain_count=s12_abstain,
                    escalate_count=s12_escalate,
                    total=len(s12_true),
                ),
            },
        }

    # 1. OOD 80
    oos_cases = load_jsonl(repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl")
    oos_leaks: list[str] = []
    oos_adapter_vetoes = 0
    for c in oos_cases:
        analysis = engine._analyse({"message": c["text"], "as_of": "2026-06-15T10:00:00Z"})[0]
        act = _adapt_action(analysis["routing"]["recommendation"])
        act, vetoed = _apply_adapter_routing_guard(act, clf.last_prediction)
        if vetoed:
            oos_adapter_vetoes += 1
        if act == "retrieve_draft":
            oos_leaks.append(c["id"])

    # 2. Noise 420 (supported 12 labels across clean/casual/typo)
    noise_cases = load_jsonl(repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl")
    noise_true, noise_pred, noise_conf, noise_corr = [], [], [], []
    noise_safe = 0
    noise_raw_draft = 0
    noise_correct_draft = 0
    noise_abstain = 0
    noise_escalate = 0
    noise_adapter_vetoes = 0
    for c in noise_cases:
        pred = clf.predict(c["text"])
        gold = c["true_intent"]
        noise_true.append(gold)
        noise_pred.append(pred["intent"])
        noise_conf.append(pred["confidence"])
        noise_corr.append(pred["intent"] == gold)
        dec = decide_route(
            IntentPrediction(intent=pred["intent"], confidence=pred["confidence"], margin=pred["margin"], model_version=model_name),
            RoutingContext(ticket_customer_id="gate-eval", extracted_slots={}, is_personal_lookup=False),
            policy_v2,
        )
        eff_action, vetoed = _apply_adapter_routing_guard(dec.action, pred)
        if vetoed:
            noise_adapter_vetoes += 1
        if eff_action == "retrieve_draft":
            noise_raw_draft += 1
            if pred["intent"] == gold:
                noise_correct_draft += 1
        elif eff_action == "escalate":
            noise_escalate += 1
        else:
            noise_abstain += 1
        if eff_action != "retrieve_draft" or pred["intent"] == gold:
            noise_safe += 1

    # 3. System acceptance 156 (known acceptance regression, NOT unseen holdout; covers all 34 escalated labels)
    sa_cases = load_jsonl(repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl")
    sa_34_raw = 0
    sa_34_correct = 0
    sa_34_abstain = 0
    sa_34_escalate = 0
    sa_34_total = 0
    sa_mand_strict_match = 0
    sa_mand_escalate = 0
    sa_mand_abstain = 0
    sa_mand_real_leaks: list[str] = []
    sa_mand_uninjected_faults: list[dict[str, Any]] = []
    sa_esc34_true: list[str] = []
    sa_esc34_pred: list[str] = []
    sa_all_true: list[str] = []
    sa_all_pred: list[str] = []
    for c in sa_cases:
        analysis = engine._analyse({"message": c["text"], "as_of": "2026-06-15T10:00:00Z"})[0]
        plabel = analysis["intent"]["label"]
        act, _ = _apply_adapter_routing_guard(_adapt_action(analysis["routing"]["recommendation"]), clf.last_prediction)
        exp = c["expected"]
        t_intent = c.get("true_intent")
        if t_intent:
            sa_all_true.append(t_intent)
            sa_all_pred.append(plabel)
            if t_intent in ESCALATED_34_INTENTS:
                sa_esc34_true.append(t_intent)
                sa_esc34_pred.append(plabel)
        if exp.get("draft_expected"):
            sa_34_total += 1
            if act == "retrieve_draft":
                sa_34_raw += 1
                if plabel == c["true_intent"]:
                    sa_34_correct += 1
            elif act == "escalate":
                sa_34_escalate += 1
            else:
                sa_34_abstain += 1
        if exp.get("must_escalate"):
            is_uninjected = c["id"] in KNOWN_UNINJECTED_ACCEPTANCE_IDS
            if is_uninjected:
                sa_mand_uninjected_faults.append(
                    {
                        "case_id": c["id"],
                        "observed_action_without_fault_injection": act,
                        "status": "NOT_EXECUTED_FAULT_INJECTION",
                        "does_not_count_as_passing_fault_coverage": True,
                    }
                )
            if act in exp["actions"]:
                sa_mand_strict_match += 1
            if act == "escalate":
                sa_mand_escalate += 1
            elif act == "manual_fallback":
                sa_mand_abstain += 1
            elif act == "retrieve_draft" and not is_uninjected:
                sa_mand_real_leaks.append(c["id"])

    # 4. Final acceptance 24 & 12 answerable (known acceptance regression, NOT unseen holdout)
    fa_cases = load_jsonl(repo_root / "data/benchmarks/final_acceptance/cases.jsonl")
    fa12_raw = 0
    fa12_correct = 0
    fa12_abstain = 0
    fa12_escalate = 0
    fa12_total = 0
    fa12_wrong_cases: list[str] = []
    fa_active_unans_n = 0
    fa_active_unans_leaks: list[str] = []
    fa_injected_fault_n = 0
    fa_injected_uninjected_drafted: list[str] = []
    for c in fa_cases:
        as_of = c.get("as_of") or "2026-06-15T10:00:00Z"
        analysis = engine._analyse({"message": c["query"], "as_of": as_of})[0]
        act, _ = _apply_adapter_routing_guard(_adapt_action(analysis["routing"]["recommendation"]), clf.last_prediction)
        if c.get("is_answerable"):
            fa12_total += 1
            pred = clf.predict(c["query"])
            dec = decide_route(
                IntentPrediction(intent=pred["intent"], confidence=pred["confidence"], margin=pred["margin"], model_version=model_name),
                RoutingContext(
                    ticket_customer_id="gate-eval",
                    extracted_slots={"order_id": c["order_id"]} if c.get("order_id") else {},
                    is_personal_lookup=bool(c.get("order_id")),
                ),
                policy_v2,
            )
            eff_action, _ = _apply_adapter_routing_guard(dec.action, pred)
            if eff_action == "retrieve_draft":
                fa12_raw += 1
                if pred["intent"] == c["intent"]:
                    fa12_correct += 1
                else:
                    fa12_wrong_cases.append(c["id"])
            elif eff_action == "escalate":
                fa12_escalate += 1
            else:
                fa12_abstain += 1
        else:
            if c.get("fixture_boundary") == "active_kb":
                fa_active_unans_n += 1
                if act == "retrieve_draft":
                    fa_active_unans_leaks.append(c["id"])
            else:
                fa_injected_fault_n += 1
                if act == "retrieve_draft":
                    fa_injected_uninjected_drafted.append(c["id"])

    return {
        "model_name": model_name,
        "score_path": {
            "score_kind": "calibrated_probability" if calibrated else "uncalibrated_softmax",
            "temperature": temperature if calibrated else 1.0,
            "calibrated": calibrated,
            "experimental_rejector_active": bool(rejector or rejector_fn),
        },
        "independent_holdout": _run_holdout(holdout_rows) if holdout_rows else None,
        "ml_oos_80": {
            "n_total": len(oos_cases),
            "flagged_safe_count": len(oos_cases) - len(oos_leaks),
            "false_draft_eligible_count": len(oos_leaks),
            "false_draft_case_ids": oos_leaks,
            "adapter_vetoes_count": oos_adapter_vetoes,
        },
        "ml_noise_420": {
            "n_total": len(noise_cases),
            "accuracy_12": M.accuracy(noise_true, noise_pred),
            "macro_f1_12": M.macro_f1(noise_true, noise_pred, labels=SUPPORTED_12_INTENTS),
            "safe_routing_rate": noise_safe / len(noise_cases),
            "ece_10bin": M.expected_calibration_error(noise_conf, noise_corr, n_bins=10)[0],
            "binary_top_label_brier": binary_top_label_brier(noise_conf, noise_corr),
            "adapter_vetoes_count": noise_adapter_vetoes,
            "selective_metrics": compute_selective_coverage_metrics(
                raw_draft=noise_raw_draft,
                correct_draft=noise_correct_draft,
                abstain_count=noise_abstain,
                escalate_count=noise_escalate,
                total=len(noise_cases),
            ),
        },
        "known_acceptance_regression_not_unseen_holdout": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "system_acceptance_156": {
                "labeled_153_accuracy": M.accuracy(sa_all_true, sa_all_pred) if sa_all_true else 0.0,
                "labeled_153_macro_f1_46": M.macro_f1(sa_all_true, sa_all_pred, labels=STANDARD_INTENTS_46) if sa_all_true else 0.0,
                "escalated_34_n": len(sa_esc34_true),
                "escalated_34_accuracy": M.accuracy(sa_esc34_true, sa_esc34_pred) if sa_esc34_true else 0.0,
                "escalated_34_macro_f1": M.macro_f1(sa_esc34_true, sa_esc34_pred, labels=ESCALATED_34_INTENTS) if sa_esc34_true else 0.0,
                "draft_expected_34_raw_draft": sa_34_raw,
                "draft_expected_34_correct_intent_draft": sa_34_correct,
                "draft_expected_34_selective_metrics": compute_selective_coverage_metrics(
                    raw_draft=sa_34_raw,
                    correct_draft=sa_34_correct,
                    abstain_count=sa_34_abstain,
                    escalate_count=sa_34_escalate,
                    total=sa_34_total,
                ),
                "mandatory_63_n": 63,
                "mandatory_63_strict_match": sa_mand_strict_match,
                "mandatory_63_strict_match_rate": round(sa_mand_strict_match / 63, 6),
                "mandatory_63_escalate": sa_mand_escalate,
                "mandatory_63_abstain_manual_fallback": sa_mand_abstain,
                "mandatory_63_real_unsafe_draft_leaks": sa_mand_real_leaks,
                "mandatory_63_uninjected_fault_fixtures": sa_mand_uninjected_faults,
            },
            "final_acceptance_24": {
                "answerable_12_raw_draft": fa12_raw,
                "answerable_12_correct_intent_draft": fa12_correct,
                "answerable_12_wrong_intent_draft_cases": fa12_wrong_cases,
                "answerable_12_selective_metrics": compute_selective_coverage_metrics(
                    raw_draft=fa12_raw,
                    correct_draft=fa12_correct,
                    abstain_count=fa12_abstain,
                    escalate_count=fa12_escalate,
                    total=fa12_total,
                ),
                "unanswerable_active_kb_n": fa_active_unans_n,
                "unanswerable_active_kb_draft_leaks": fa_active_unans_leaks,
                "unanswerable_injected_synthetic_fault_n": fa_injected_fault_n,
                "unanswerable_injected_synthetic_uninjected_drafted_cases": fa_injected_uninjected_drafted,
                "injected_fault_note": "fixture_boundary=='injected_synthetic' cases (final-case-21..24) run uninjected here and NEVER count as passing fault coverage.",
            },
        },
    }


def run_classifier_acceptance_gate(
    *,
    repo_root: Path,
    candidate_name: str,
    candidate_dir: Path,
    serving_dir: Path,
    candidate_manifest_path: Path | None = None,
    calibration_manifest_path: Path | None = None,
    train_split_path: Path | None = None,
    calibration_split_path: Path | None = None,
    eval_split_path: Path | None = None,
    verify_parity: bool = True,
) -> dict[str, Any]:
    provenance = audit_candidate_provenance(candidate_dir, candidate_manifest_path)
    calibration_audit = validate_calibration_manifest(candidate_dir, calibration_manifest_path)

    train_rows = load_jsonl(train_split_path) if train_split_path and train_split_path.exists() else None
    cal_rows = load_jsonl(calibration_split_path) if calibration_split_path and calibration_split_path.exists() else None
    eval_rows = load_jsonl(eval_split_path) if eval_split_path and eval_split_path.exists() else None

    gold_texts: list[tuple[str, str, str]] = []
    for sname, path in (
        ("ml_noise", repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl"),
        ("ml_oos", repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl"),
        ("system_acceptance", repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl"),
        ("final_acceptance", repo_root / "data/benchmarks/final_acceptance/cases.jsonl"),
    ):
        for r in load_jsonl(path):
            gold_texts.append((sname, r["id"], _extract_text(r)))

    isolation = check_split_isolation_and_gold_contamination(
        train_rows=train_rows,
        calibration_rows=cal_rows,
        eval_rows=eval_rows,
        gold_texts=gold_texts,
    )

    failure_reasons: list[str] = []
    failure_reasons.extend(provenance["failure_reasons"])
    if calibration_audit["present"] and not calibration_audit["valid"]:
        failure_reasons.extend(calibration_audit["failure_reasons"])
    failure_reasons.extend(isolation["failure_reasons"])

    serving_eval = evaluate_model_on_suites("distilbert-supportiq", serving_dir, repo_root, holdout_rows=eval_rows)
    candidate_eval = (
        evaluate_model_on_suites(candidate_name, candidate_dir, repo_root, holdout_rows=eval_rows)
        if provenance["files"]["weights"]["exists"] and provenance["valid_46_label_bijection"]
        else None
    )

    candidate_calibrated_eval: dict[str, Any] | None = None
    if (
        candidate_eval is not None
        and calibration_audit["present"]
        and calibration_audit["valid"]
        and (calibration_audit["calibrated"] or calibration_audit["rejector"] is not None)
    ):
        candidate_calibrated_eval = evaluate_model_on_suites(
            candidate_name,
            candidate_dir,
            repo_root,
            holdout_rows=eval_rows,
            temperature=float(calibration_audit["temperature"] or 1.0),
            calibrated=bool(calibration_audit["calibrated"]),
            rejector=calibration_audit["rejector"],
        )

    parity_audit: dict[str, Any] | None = None
    if verify_parity and serving_dir.exists():
        parity_audit = verify_runtime_score_parity(
            serving_dir,
            probe_temperature=float(calibration_audit["temperature"] or 1.25) if calibration_audit["valid"] else 1.25,
            unpinned_dir=candidate_dir if candidate_dir.exists() else None,
            repo_root=repo_root,
        )
        if not parity_audit["passed"]:
            failure_reasons.append("runtime_score_parity_mismatch")

    active_eval = candidate_calibrated_eval if candidate_calibrated_eval is not None else candidate_eval
    if active_eval is not None:
        if active_eval["ml_oos_80"]["false_draft_eligible_count"] > 0:
            failure_reasons.append("oos_draft_leak")
        if active_eval["ml_noise_420"]["safe_routing_rate"] < serving_eval["ml_noise_420"]["safe_routing_rate"] - 1e-6:
            failure_reasons.append("noise_safe_routing_regression")

        if eval_rows and active_eval["independent_holdout"] and serving_eval["independent_holdout"]:
            ch = active_eval["independent_holdout"]
            sh = serving_eval["independent_holdout"]
            if ch["escalated_34"]["unsafe_draft_eligible_count"] > 0:
                failure_reasons.append("holdout_34_label_unsafe_draft_leak")
            if sh["escalated_34"]["n"] > 0 and ch["escalated_34"]["macro_f1"] < sh["escalated_34"]["macro_f1"] - 0.02:
                failure_reasons.append("34_label_regression_holdout")

        creg = active_eval["known_acceptance_regression_not_unseen_holdout"]
        sreg = serving_eval["known_acceptance_regression_not_unseen_holdout"]
        if creg["system_acceptance_156"]["escalated_34_macro_f1"] < sreg["system_acceptance_156"]["escalated_34_macro_f1"] - 0.02:
            failure_reasons.append("34_label_regression_system_acceptance")
        if creg["system_acceptance_156"]["mandatory_63_real_unsafe_draft_leaks"]:
            failure_reasons.append("mandatory_escalation_unsafe_draft_leak")
        if creg["system_acceptance_156"]["mandatory_63_strict_match"] < sreg["system_acceptance_156"]["mandatory_63_strict_match"]:
            failure_reasons.append("mandatory_strict_action_regression")
        if creg["final_acceptance_24"]["unanswerable_active_kb_draft_leaks"]:
            failure_reasons.append("final_acceptance_unanswerable_draft_leak")
        if (
            len(creg["final_acceptance_24"]["answerable_12_wrong_intent_draft_cases"])
            > len(sreg["final_acceptance_24"]["answerable_12_wrong_intent_draft_cases"])
        ):
            failure_reasons.append("wrong_intent_draft_regression")

    unique_reasons = sorted(set(failure_reasons))
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "report_type": "task_c_classifier_acceptance_gate",
        "gate_decision": "PASS" if not unique_reasons else "REJECT",
        "failure_reasons": unique_reasons,
        "suite_classification_note": (
            "system_acceptance_156 and final_acceptance_24 are explicitly labeled "
            "known_acceptance_regression_not_unseen_holdout."
        ),
        "provenance_audit": provenance,
        "calibration_manifest_audit": calibration_audit,
        "runtime_parity_audit": parity_audit,
        "split_isolation_and_contamination": isolation,
        "serving_baseline_evaluation": serving_eval,
        "candidate_evaluation": candidate_eval,
        "candidate_calibrated_evaluation": candidate_calibrated_eval,
    }

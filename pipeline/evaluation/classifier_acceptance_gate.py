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
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

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
        declared_hashes = manifest_data.get("artifact_hashes") or {}
        if declared_hashes:
            for key, file_key in (("model.safetensors", "weights"), ("tokenizer.json", "tokenizer"), ("config.json", "config")):
                exp_hash = declared_hashes.get(key)
                actual_hash = files_info[file_key].get("sha256")
                if exp_hash and actual_hash and str(exp_hash).lower() != str(actual_hash).lower():
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


class GateSequenceClassifier:
    """Loaded safetensors sequence classifier implementing Engine's model interface."""

    def __init__(self, name: str, model_dir: Path):
        self.name = name
        self.model_dir = model_dir
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
        with torch.inference_mode():
            logits = self.model(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1).cpu().tolist()
        ranked = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx, top2_idx = ranked[0], ranked[1]
        top_k = [{"intent": self.id2label[i], "probability": float(probs[i])} for i in ranked[:top_k_count]]
        return {
            "intent": self.id2label[top1_idx],
            "confidence": float(probs[top1_idx]),
            "margin": float(probs[top1_idx] - probs[top2_idx]),
            "top_k": top_k,
            "score_kind": "uncalibrated_softmax",
            "model_mode": "trained",
            "verified": True,
        }


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


def evaluate_model_on_suites(
    model_name: str,
    model_dir: Path,
    repo_root: Path,
    holdout_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate a model across independent holdout (if given), OOD, noise, and known regression suites."""
    clf = GateSequenceClassifier(model_name, model_dir)
    engine, policy_v2 = _build_engine(clf, repo_root)

    def _run_holdout(rows: list[dict[str, Any]]) -> dict[str, Any]:
        y_true, y_pred, confs, corr = [], [], [], []
        s34_true, s34_pred = [], []
        s12_true, s12_pred = [], []
        s12_raw_draft = 0
        s12_correct_draft = 0
        s34_unsafe_draft = 0

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
            if gold in ESCALATED_34_INTENTS:
                s34_true.append(gold)
                s34_pred.append(plabel)
                if dec.action == "retrieve_draft":
                    s34_unsafe_draft += 1
            elif gold in SUPPORTED_12_INTENTS:
                s12_true.append(gold)
                s12_pred.append(plabel)
                if dec.action == "retrieve_draft":
                    s12_raw_draft += 1
                    if plabel == gold:
                        s12_correct_draft += 1

        return {
            "suite_role": "independent_group_isolated_holdout",
            "n_total": len(rows),
            "accuracy_46": M.accuracy(y_true, y_pred) if y_true else 0.0,
            "macro_f1_46": M.macro_f1(y_true, y_pred, labels=STANDARD_INTENTS_46) if y_true else 0.0,
            "ece_10bin": M.expected_calibration_error(confs, corr, n_bins=10)[0] if confs else 0.0,
            "binary_top_label_brier": binary_top_label_brier(confs, corr),
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
            },
        }

    # 1. OOD 80
    oos_cases = load_jsonl(repo_root / "data/benchmarks/autoeval/v1/ml_oos.jsonl")
    oos_leaks: list[str] = []
    for c in oos_cases:
        analysis = engine._analyse({"message": c["text"], "as_of": "2026-06-15T10:00:00Z"})[0]
        if analysis["routing"]["recommendation"] == "draft":
            oos_leaks.append(c["id"])

    # 2. Noise 420 (supported 12 labels across clean/casual/typo)
    noise_cases = load_jsonl(repo_root / "data/benchmarks/autoeval/v1/ml_noise.jsonl")
    noise_true, noise_pred, noise_conf, noise_corr = [], [], [], []
    noise_safe = 0
    for c in noise_cases:
        pred = clf.predict(c["text"])
        gold = c["true_intent"]
        noise_true.append(gold)
        noise_pred.append(pred["intent"])
        noise_conf.append(pred["confidence"])
        noise_corr.append(pred["intent"] == gold)
        if pred["intent"] == gold or pred["confidence"] < policy_v2.default_confidence_threshold or pred["intent"] not in SUPPORTED_12_INTENTS:
            noise_safe += 1

    # 3. System acceptance 156 (known acceptance regression, NOT unseen holdout; covers all 34 escalated labels)
    sa_cases = load_jsonl(repo_root / "data/benchmarks/system/v2/acceptance/cases.jsonl")
    sa_34_raw = 0
    sa_34_correct = 0
    sa_mand_strict_match = 0
    sa_mand_escalate = 0
    sa_mand_abstain = 0
    sa_mand_real_leaks: list[str] = []
    sa_esc34_true: list[str] = []
    sa_esc34_pred: list[str] = []
    sa_all_true: list[str] = []
    sa_all_pred: list[str] = []
    for c in sa_cases:
        analysis = engine._analyse({"message": c["text"], "as_of": "2026-06-15T10:00:00Z"})[0]
        plabel = analysis["intent"]["label"]
        act = _adapt_action(analysis["routing"]["recommendation"])
        exp = c["expected"]
        t_intent = c.get("true_intent")
        if t_intent:
            sa_all_true.append(t_intent)
            sa_all_pred.append(plabel)
            if t_intent in ESCALATED_34_INTENTS:
                sa_esc34_true.append(t_intent)
                sa_esc34_pred.append(plabel)
        if exp.get("draft_expected") and act == "retrieve_draft":
            sa_34_raw += 1
            if plabel == c["true_intent"]:
                sa_34_correct += 1
        if exp.get("must_escalate"):
            if act in exp["actions"]:
                sa_mand_strict_match += 1
            if act == "escalate":
                sa_mand_escalate += 1
            elif act == "manual_fallback":
                sa_mand_abstain += 1
            elif act == "retrieve_draft" and c["id"] not in KNOWN_UNINJECTED_ACCEPTANCE_IDS:
                sa_mand_real_leaks.append(c["id"])

    # 4. Final acceptance 24 & 12 answerable (known acceptance regression, NOT unseen holdout)
    fa_cases = load_jsonl(repo_root / "data/benchmarks/final_acceptance/cases.jsonl")
    fa12_raw = 0
    fa12_correct = 0
    fa12_wrong_cases: list[str] = []
    fa_active_unans_leaks: list[str] = []
    for c in fa_cases:
        as_of = c.get("as_of") or "2026-06-15T10:00:00Z"
        analysis = engine._analyse({"message": c["query"], "as_of": as_of})[0]
        act = _adapt_action(analysis["routing"]["recommendation"])
        if c.get("is_answerable"):
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
            if dec.action == "retrieve_draft":
                fa12_raw += 1
                if pred["intent"] == c["intent"]:
                    fa12_correct += 1
                else:
                    fa12_wrong_cases.append(c["id"])
        elif c.get("fixture_boundary") == "active_kb" and act == "retrieve_draft":
            fa_active_unans_leaks.append(c["id"])

    return {
        "model_name": model_name,
        "independent_holdout": _run_holdout(holdout_rows) if holdout_rows else None,
        "ml_oos_80": {
            "n_total": len(oos_cases),
            "flagged_safe_count": len(oos_cases) - len(oos_leaks),
            "false_draft_eligible_count": len(oos_leaks),
            "false_draft_case_ids": oos_leaks,
        },
        "ml_noise_420": {
            "n_total": len(noise_cases),
            "accuracy_12": M.accuracy(noise_true, noise_pred),
            "macro_f1_12": M.macro_f1(noise_true, noise_pred, labels=SUPPORTED_12_INTENTS),
            "safe_routing_rate": noise_safe / len(noise_cases),
            "ece_10bin": M.expected_calibration_error(noise_conf, noise_corr, n_bins=10)[0],
            "binary_top_label_brier": binary_top_label_brier(noise_conf, noise_corr),
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
                "mandatory_63_strict_match": sa_mand_strict_match,
                "mandatory_63_escalate": sa_mand_escalate,
                "mandatory_63_abstain_manual_fallback": sa_mand_abstain,
                "mandatory_63_real_unsafe_draft_leaks": sa_mand_real_leaks,
            },
            "final_acceptance_24": {
                "answerable_12_raw_draft": fa12_raw,
                "answerable_12_correct_intent_draft": fa12_correct,
                "answerable_12_wrong_intent_draft_cases": fa12_wrong_cases,
                "unanswerable_active_kb_draft_leaks": fa_active_unans_leaks,
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
    train_split_path: Path | None = None,
    calibration_split_path: Path | None = None,
    eval_split_path: Path | None = None,
) -> dict[str, Any]:
    provenance = audit_candidate_provenance(candidate_dir, candidate_manifest_path)

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
    failure_reasons.extend(isolation["failure_reasons"])

    serving_eval = evaluate_model_on_suites("distilbert-supportiq", serving_dir, repo_root, holdout_rows=eval_rows)
    candidate_eval = (
        evaluate_model_on_suites(candidate_name, candidate_dir, repo_root, holdout_rows=eval_rows)
        if provenance["files"]["weights"]["exists"] and provenance["valid_46_label_bijection"]
        else None
    )

    if candidate_eval is not None:
        if candidate_eval["ml_oos_80"]["false_draft_eligible_count"] > 0:
            failure_reasons.append("oos_draft_leak")
        if candidate_eval["ml_noise_420"]["safe_routing_rate"] < serving_eval["ml_noise_420"]["safe_routing_rate"] - 1e-6:
            failure_reasons.append("noise_safe_routing_regression")

        if eval_rows and candidate_eval["independent_holdout"] and serving_eval["independent_holdout"]:
            ch = candidate_eval["independent_holdout"]
            sh = serving_eval["independent_holdout"]
            if ch["escalated_34"]["unsafe_draft_eligible_count"] > 0:
                failure_reasons.append("holdout_34_label_unsafe_draft_leak")
            if sh["escalated_34"]["n"] > 0 and ch["escalated_34"]["macro_f1"] < sh["escalated_34"]["macro_f1"] - 0.02:
                failure_reasons.append("34_label_regression_holdout")

        creg = candidate_eval["known_acceptance_regression_not_unseen_holdout"]
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
        "split_isolation_and_contamination": isolation,
        "serving_baseline_evaluation": serving_eval,
        "candidate_evaluation": candidate_eval,
    }

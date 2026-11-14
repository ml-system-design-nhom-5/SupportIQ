#!/usr/bin/env python3
"""SupportIQ Candidate Model Comparison & Intent Coverage Diagnostic.

Compares already trained candidate models under identical policy boundaries:
1. Locks SHA-256 hashes of all inputs, gold benchmarks, and candidate models.
2. Formally audits model provenance and 46-label bijection for all candidates:
   - distilbert-supportiq (Active Serving)
   - supportpilot-distilbert (Finetuned Alternative Candidate)
   - Traditional Baselines (linear_svm, logistic_regression, multinomial_nb):
     audits historical training manifests, CV metrics, and reports missing bundle.joblib files.
3. Diagnostic: Reproduces and diagnoses the 7 uncertain answerable cases in final acceptance.
4. Suite 1: Evaluates frozen ML Noise benchmark (420 cases: clean, casual, typo).
5. Suite 2: Evaluates frozen ML OOD & Ambiguity benchmark (80 cases across 5 categories).
6. Suite 3: Evaluates frozen System Acceptance benchmark (156 cases).
7. Suite 4: Evaluates frozen Final Acceptance benchmark (24 cases).
8. Distinguishes raw accuracy, supported draftability, authority safety, and abstention.
9. Enforces OfflineSpyLLM (zero live provider calls).
10. Writes comprehensive raw row predictions, summary JSON, and diagnostic JSON.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.intent.routing import (
    load_policy_v2,
    decide_route,
    SUPPORTED_12_INTENTS,
    ESCALATED_34_INTENTS,
    STANDARD_INTENTS_46,
)
from apps.core_backend.intent.schemas import IntentPrediction, RoutingContext
from apps.ai_service.engine import Engine
from pipeline.evaluation.autoeval import metrics as M


def compute_file_sha256(path: Path) -> str:
    """Compute lowercase hex SHA-256 for a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def get_git_info() -> Dict[str, Any]:
    """Retrieve current git commit hash and dirty status."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        commit = "unknown"
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True
        ).strip()
        is_dirty = bool(status)
        dirty_files = [line.strip() for line in status.splitlines() if line.strip()]
    except Exception:
        is_dirty = False
        dirty_files = []
    return {
        "commit": commit,
        "is_dirty": is_dirty,
        "dirty_files": dirty_files,
    }


class CandidateModelAdapter:
    """Standardized adapter for DistilBERT sequence classification models."""

    def __init__(self, name: str, model_dir: Path, version: str):
        self.name = name
        self.model_dir = model_dir
        self.version = version
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        weights_file = model_dir / "model.safetensors"
        tokenizer_file = model_dir / "tokenizer.json"
        config_file = model_dir / "config.json"

        if not weights_file.exists():
            raise FileNotFoundError(f"Missing weights: {weights_file}")
        if not tokenizer_file.exists():
            raise FileNotFoundError(f"Missing tokenizer: {tokenizer_file}")
        if not config_file.exists():
            raise FileNotFoundError(f"Missing config: {config_file}")

        self.weights_sha256 = compute_file_sha256(weights_file)
        self.weights_size_bytes = weights_file.stat().st_size
        self.tokenizer_sha256 = compute_file_sha256(tokenizer_file)
        self.tokenizer_size_bytes = tokenizer_file.stat().st_size

        with open(config_file, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            raw_id2label = cfg.get("id2label", {})
            self.id2label = {int(k): v for k, v in raw_id2label.items()}

        # Verify strict 46-label bijection
        self.is_valid_bijection = (
            len(self.id2label) == 46
            and set(self.id2label.keys()) == set(range(46))
            and set(self.id2label.values()) == set(STANDARD_INTENTS_46)
        )
        if not self.is_valid_bijection:
            raise ValueError(f"Model {name} does not have valid 46-label bijection")

        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        self.model.eval()
        self.model.to(self.device)

        self.verified_model_version = version
        self.model_version = version
        self.model_mode = "trained"
        self.verified = True

    def predict(self, text: str, top_k_count: int = 5) -> Dict[str, Any]:
        inputs = self.tokenizer(
            text,
            max_length=64,
            padding="max_length",
            truncation=True,
            return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = self.model(**inputs)
            logits = outputs.logits[0]
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        sorted_indices = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
        top1_idx = sorted_indices[0]
        top1_intent = self.id2label[top1_idx]
        top1_prob = probs[top1_idx]

        top2_prob = probs[sorted_indices[1]] if len(sorted_indices) > 1 else 0.0
        margin = top1_prob - top2_prob

        top_k = [
            {"intent": self.id2label[idx], "probability": probs[idx]}
            for idx in sorted_indices[:top_k_count]
        ]

        return {
            "intent": top1_intent,
            "confidence": top1_prob,
            "margin": margin,
            "top_k": top_k,
            "score_kind": "uncalibrated_softmax",
            "model_version": self.version,
            "model_checksum": self.weights_sha256,
            "tokenizer_checksum": self.tokenizer_sha256,
            "model_mode": self.model_mode,
            "verified": self.verified,
        }


class OfflineSpyLLM:
    """Asserts zero external LLM invocations occur during offline evaluation."""

    def __init__(self):
        self.invocations: List[Dict[str, Any]] = []

    def draft(self, *args, **kwargs) -> Dict[str, Any]:
        call_info = {
            "args": args,
            "kwargs": kwargs,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.invocations.append(call_info)
        raise AssertionError(
            f"VIOLATION: External LLM was invoked during offline evaluation! Call: {call_info}"
        )


def adapt_engine_recommendation_to_routing_action(
    recommendation: str,
    reason_codes: Optional[List[str]] = None,
) -> str:
    if recommendation == "draft":
        return "retrieve_draft"
    elif recommendation == "escalate":
        return "escalate"
    elif recommendation == "abstain":
        return "manual_fallback"
    return recommendation


def audit_traditional_baselines(run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Audit traditional baseline manifests, CV reports, and weight file availability."""
    target_dir = run_dir if run_dir is not None else (REPO_ROOT / "artifacts/training/03-11-2026-00")
    manifest_file = target_dir / "manifest.json"

    try:
        manifest_rel = str(manifest_file.relative_to(REPO_ROOT))
    except ValueError:
        manifest_rel = str(manifest_file)

    audit_data: Dict[str, Any] = {
        "run_id": target_dir.name,
        "manifest_path": manifest_rel,
        "status": "manifest_missing",
        "gitignore_pattern": "/artifacts/**/*.joblib (line 79)",
        "models": {},
    }

    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            m = json.load(f)
        outputs = m.get("outputs", {})
        selection = m.get("selection", {}).get("best_per_model", {})

        present_count = 0
        model_ids = ["linear_svm", "logistic_regression", "multinomial_nb"]
        for model_id in model_ids:
            bundle_key = f"models/{model_id}/bundle.joblib"
            expected_sha = outputs.get(bundle_key)
            card_file = target_dir / f"models/{model_id}/model_card.json"
            bundle_file = target_dir / f"models/{model_id}/bundle.joblib"

            is_present = bundle_file.exists()
            actual_sha = compute_file_sha256(bundle_file) if is_present else None
            sha_match = (
                (actual_sha == expected_sha.lower())
                if (is_present and isinstance(expected_sha, str))
                else is_present
            )
            if is_present:
                present_count += 1

            best_meta = selection.get(model_id, {})
            audit_data["models"][model_id] = {
                "bundle_relative_path": bundle_key,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "sha256_match": sha_match if is_present else False,
                "file_present_on_disk": is_present,
                "model_card_present": card_file.exists(),
                "cv_macro_f1_mean": best_meta.get("macro_f1_mean"),
                "cv_macro_f1_std": best_meta.get("macro_f1_std"),
                "cv_accuracy_mean": best_meta.get("accuracy_mean"),
                "params": best_meta.get("params"),
                "runnable_for_live_inference": bool(is_present and sha_match),
                "reason_not_runnable": (
                    None
                    if (is_present and sha_match)
                    else (
                        "Checksum mismatch against manifest expected_sha256."
                        if is_present
                        else "Physical weights file was absent from disk at audit time."
                    )
                ),
            }

        if present_count == len(model_ids):
            audit_data["status"] = "weights_present"
        elif present_count > 0:
            audit_data["status"] = "weights_partially_present"
        else:
            audit_data["status"] = "weights_missing"

    return audit_data


def run_comparative_evaluation(output_dir: Path) -> Dict[str, Any]:
    start_time = time.perf_counter()
    utc_now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_predictions_path = output_dir / "raw_predictions.jsonl"
    raw_predictions_file = open(raw_predictions_path, "w", encoding="utf-8")

    git_info = get_git_info()
    print("=" * 80)
    print("SupportIQ â€” Comparative Model Evaluation & Intent Diagnostic")
    print(f"Timestamp: {utc_now}")
    print(f"Git Commit: {git_info['commit']} (dirty={git_info['is_dirty']})")
    print(f"Output Directory: {output_dir}")
    print("=" * 80)

    # 1. Lock hashes of shared assets
    print("\n[Worker A] Locking shared assets and benchmark suites...")
    files_to_lock = {
        "ml_noise": REPO_ROOT / "data/benchmarks/autoeval/v1/ml_noise.jsonl",
        "ml_oos": REPO_ROOT / "data/benchmarks/autoeval/v1/ml_oos.jsonl",
        "acceptance_cases": REPO_ROOT / "data/benchmarks/system/v2/acceptance/cases.jsonl",
        "final_acceptance_cases": REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl",
        "approved_kb": REPO_ROOT / "data/knowledge/approved_kb.v2.json",
        "intent_policy": REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v2.json",
    }
    locked_hashes = {}
    for name, path in files_to_lock.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing required asset: {path}")
        h = compute_file_sha256(path)
        locked_hashes[name] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "sha256": h,
            "size_bytes": path.stat().st_size,
        }
        print(f"  [LOCKED] {name:25s} -> {h[:16]}... ({path.name})")

    # 2. Audit traditional baselines
    print("\n[Worker A] Auditing traditional scikit-learn baselines...")
    traditional_audit = audit_traditional_baselines()
    for mid, mdata in traditional_audit["models"].items():
        print(f"  [BASELINE] {mid:20s}: CV Macro-F1={mdata['cv_macro_f1_mean']:.4f}, weights on disk={mdata['file_present_on_disk']}")

    # 3. Load valid trained candidates
    print("\n[Worker A] Loading trained DistilBERT candidates...")
    candidates = {}
    candidate_specs = [
        ("distilbert-supportiq", REPO_ROOT / "artifacts/models/trained/distilbert-supportiq", "v1.0.0-serving"),
        ("supportpilot-distilbert", REPO_ROOT / "artifacts/models/finetuned/supportpilot-distilbert", "v1.1.0-candidate"),
    ]

    for name, model_dir, ver in candidate_specs:
        adapter = CandidateModelAdapter(name, model_dir, ver)
        candidates[name] = adapter
        locked_hashes[f"{name}_weights"] = {
            "path": str((model_dir / "model.safetensors").relative_to(REPO_ROOT)),
            "sha256": adapter.weights_sha256,
            "size_bytes": adapter.weights_size_bytes,
        }
        locked_hashes[f"{name}_tokenizer"] = {
            "path": str((model_dir / "tokenizer.json").relative_to(REPO_ROOT)),
            "sha256": adapter.tokenizer_sha256,
            "size_bytes": adapter.tokenizer_size_bytes,
        }
        print(f"  [LOADED] {name:25s} -> weights {adapter.weights_sha256[:16]}... (46 labels verified)")

    with open(output_dir / "locked_hashes.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "created_at": utc_now,
                "git": git_info,
                "hashes": locked_hashes,
                "traditional_baselines_audit": traditional_audit,
            },
            f,
            indent=2,
        )

    # Prepare shared engine components
    policy_v2 = load_policy_v2()
    retriever = RetrievalAdapter(kb_path=str(files_to_lock["approved_kb"]))
    spy_llm = OfflineSpyLLM()

    # Evaluation results container
    results: Dict[str, Any] = {
        "metadata": {
            "created_at": utc_now,
            "git": git_info,
            "policy_version": policy_v2.version,
            "models_evaluated": list(candidates.keys()),
        },
        "traditional_baselines": traditional_audit,
        "diagnostic_7_cases": {},
        "final_acceptance_12_answerable": {},
        "suites": {},
    }

    # -------------------------------------------------------------------------
    # PART 1: Diagnostic on Final Acceptance 12 Answerable Cases (focus on the 7)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[Worker A] PART 1: Reproducing & Diagnosing 12 Answerable Cases (Focus on 7 Uncertain)")
    print("=" * 80)
    with open(files_to_lock["final_acceptance_cases"], "r", encoding="utf-8") as f:
        final_cases = [json.loads(line) for line in f if line.strip()]

    answerable_final_cases = [c for c in final_cases if c.get("is_answerable")]

    diagnostic_by_model = {}
    for cand_name, adapter in candidates.items():
        case_diagnostics = []
        drafted_count = 0
        clarify_count = 0
        escalate_count = 0
        correct_intent_count = 0

        for c in answerable_final_cases:
            cid = c["id"]
            query = c["query"]
            expected_intent = c["intent"]
            expected_action = c["expected_action"]

            pred = adapter.predict(query)
            top1_intent = pred["intent"]
            top1_prob = pred["confidence"]
            margin = pred["margin"]

            pred_obj = IntentPrediction(
                intent=top1_intent,
                confidence=top1_prob,
                margin=margin,
                model_version=cand_name,
            )
            ctx = RoutingContext(
                ticket_customer_id="cust-diag-01",
                extracted_slots={"order_id": c.get("order_id")} if c.get("order_id") else {},
                is_personal_lookup=bool(c.get("order_id")),
            )
            decision = decide_route(pred_obj, ctx, policy_v2)

            is_intent_correct = (top1_intent == expected_intent)
            if is_intent_correct:
                correct_intent_count += 1
            if decision.action == "retrieve_draft":
                drafted_count += 1
            elif decision.action == "clarify":
                clarify_count += 1
            elif decision.action == "escalate":
                escalate_count += 1

            thresh_conf = policy_v2.confidence_thresholds.get(top1_intent, policy_v2.default_confidence_threshold)
            thresh_margin = policy_v2.margin_thresholds.get(top1_intent, policy_v2.default_margin_threshold)

            diag_item = {
                "case_id": cid,
                "query": query,
                "expected_intent": expected_intent,
                "predicted_intent": top1_intent,
                "is_intent_correct": is_intent_correct,
                "confidence": round(top1_prob, 4),
                "confidence_threshold": thresh_conf,
                "confidence_pass": top1_prob >= thresh_conf,
                "margin": round(margin, 4),
                "margin_threshold": thresh_margin,
                "margin_pass": margin >= thresh_margin,
                "routing_action": decision.action,
                "reason_codes": decision.reason_codes,
                "target_queue": decision.target_queue,
                "is_automated_draft": (decision.action == "retrieve_draft"),
            }
            case_diagnostics.append(diag_item)

            raw_row = {
                "candidate": cand_name,
                "suite": "final_acceptance_answerable_12",
                **diag_item,
            }
            raw_predictions_file.write(json.dumps(raw_row) + "\n")

        diagnostic_by_model[cand_name] = {
            "n_answerable": len(answerable_final_cases),
            "correct_intent_count": correct_intent_count,
            "intent_accuracy": round(correct_intent_count / len(answerable_final_cases), 4),
            "drafted_count": drafted_count,
            "draft_rate": round(drafted_count / len(answerable_final_cases), 4),
            "clarify_count": clarify_count,
            "escalate_count": escalate_count,
            "cases": case_diagnostics,
        }

    results["final_acceptance_12_answerable"] = diagnostic_by_model
    # Specifically isolate the 7 uncertain cases
    target_7_ids = {"final-case-03", "final-case-04", "final-case-05", "final-case-06", "final-case-07", "final-case-10", "final-case-12"}
    results["diagnostic_7_cases"] = {
        cand_name: [c for c in cdata["cases"] if c["case_id"] in target_7_ids]
        for cand_name, cdata in diagnostic_by_model.items()
    }

    with open(output_dir / "diagnostic_7_cases.json", "w", encoding="utf-8") as f:
        json.dump(results["diagnostic_7_cases"], f, indent=2)

    print("\n--- Diagnostic Summary (12 Answerable Cases in Final Acceptance) ---")
    for cname, cdata in diagnostic_by_model.items():
        print(f"  {cname:25s}: Intent Acc={cdata['intent_accuracy']:.2%} ({cdata['correct_intent_count']}/12) | Drafts={cdata['drafted_count']}/12 ({cdata['draft_rate']:.2%}) | Clarify={cdata['clarify_count']} | Escalate={cdata['escalate_count']}")

    # -------------------------------------------------------------------------
    # PART 2: Comprehensive Evaluation Across the 4 Frozen Suites
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("[Worker A] PART 2: Comparative Evaluation Across Frozen Benchmark Suites")
    print("=" * 80)

    for cand_name, adapter in candidates.items():
        print(f"\nEvaluating candidate: {cand_name}")
        cand_summary = {}

        # Build Engine with this candidate
        cand_engine = Engine(
            model=adapter,
            retriever=retriever,
            llm=spy_llm,
            versions={
                "engine": "2.0.0",
                "policy": policy_v2.version,
                "model": adapter.version,
            },
            policy=policy_v2.model_dump(),
        )

        # ---------------------------------------------------------------------
        # Suite 1: ML Noise Robustness (420 cases)
        # ---------------------------------------------------------------------
        with open(files_to_lock["ml_noise"], "r", encoding="utf-8") as f:
            noise_cases = [json.loads(line) for line in f if line.strip()]

        noise_by_variant: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        noise_safe_count = 0

        for c in noise_cases:
            pred = adapter.predict(c["text"])
            top1 = pred["intent"]
            conf = pred["confidence"]
            vkind = c.get("kind", c.get("variant_kind", "clean"))
            true_intent = c["true_intent"]
            correct = (top1 == true_intent)

            is_safe = correct or (conf < 0.65) or (top1 not in SUPPORTED_12_INTENTS)
            if is_safe:
                noise_safe_count += 1

            row = {
                "candidate": cand_name,
                "suite": "ml_noise",
                "case_id": c["id"],
                "variant_kind": vkind,
                "true_intent": true_intent,
                "predicted_intent": top1,
                "confidence": conf,
                "correct": correct,
                "safe_routing": is_safe,
            }
            noise_by_variant[vkind].append(row)
            raw_predictions_file.write(json.dumps(row) + "\n")

        noise_metrics = {}
        for vk in ["clean", "casual", "typo"]:
            rows = noise_by_variant[vk]
            gold = [r["true_intent"] for r in rows]
            preds = [r["predicted_intent"] for r in rows]
            acc = M.accuracy(gold, preds)
            mf1 = M.macro_f1(gold, preds)
            confs = sorted([r["confidence"] for r in rows])
            med_c = confs[len(confs) // 2] if confs else 0.0
            noise_metrics[vk] = {
                "n": len(rows),
                "accuracy": round(acc, 4),
                "macro_f1": round(mf1, 4),
                "median_confidence": round(med_c, 4),
            }

        clean_f1 = noise_metrics["clean"]["macro_f1"]
        casual_f1 = noise_metrics["casual"]["macro_f1"]
        typo_f1 = noise_metrics["typo"]["macro_f1"]
        noise_metrics["casual_f1_drop"] = round(clean_f1 - casual_f1, 4)
        noise_metrics["typo_f1_drop"] = round(clean_f1 - typo_f1, 4)
        noise_metrics["max_f1_drop"] = max(noise_metrics["casual_f1_drop"], noise_metrics["typo_f1_drop"])
        noise_metrics["n_total"] = len(noise_cases)
        noise_metrics["safe_routing_count"] = noise_safe_count
        noise_metrics["safe_routing_rate"] = round(noise_safe_count / len(noise_cases), 4)
        all_noise = [r for rows in noise_by_variant.values() for r in rows]
        noise_metrics["overall_accuracy"] = round(
            M.accuracy([r["true_intent"] for r in all_noise], [r["predicted_intent"] for r in all_noise]), 4
        )
        cand_summary["ml_noise"] = noise_metrics
        print(f"  [ml_noise] Clean Acc: {noise_metrics['clean']['accuracy']:.2%}, Casual Acc: {noise_metrics['casual']['accuracy']:.2%}, Typo Acc: {noise_metrics['typo']['accuracy']:.2%}")
        print(f"             Safe Routing Rate: {noise_metrics['safe_routing_rate']:.2%} ({noise_safe_count}/420)")

        # ---------------------------------------------------------------------
        # Suite 2: ML OOD & Ambiguous (80 cases)
        # ---------------------------------------------------------------------
        with open(files_to_lock["ml_oos"], "r", encoding="utf-8") as f:
            oos_cases = [json.loads(line) for line in f if line.strip()]

        oos_rows = []
        oos_by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for c in oos_cases:
            req = {"message": c["text"], "as_of": utc_now, "order_context": {}}
            ans, evidence = cand_engine._analyse(req)
            rec = ans["routing"]["recommendation"]
            reasons = ans["routing"]["reason_codes"]
            pred_intent = ans["intent"]["label"]
            pred_conf = ans["intent"]["probability"]

            is_flagged = rec in ("abstain", "escalate")
            is_low_conf = "low_confidence" in reasons or pred_conf < 0.65
            is_drafted = (rec == "draft")

            row = {
                "candidate": cand_name,
                "suite": "ml_oos",
                "case_id": c["id"],
                "category": c["category"],
                "text": c["text"],
                "predicted_intent": pred_intent,
                "confidence": pred_conf,
                "recommendation": rec,
                "reason_codes": reasons,
                "flagged_safe": is_flagged,
                "low_confidence": is_low_conf,
                "is_drafted": is_drafted,
            }
            oos_rows.append(row)
            oos_by_cat[c["category"]].append(row)
            raw_predictions_file.write(json.dumps(row) + "\n")

        cat_breakdown = {}
        for cat, rows in oos_by_cat.items():
            n = len(rows)
            flagged = sum(r["flagged_safe"] for r in rows)
            low_c = sum(r["low_confidence"] for r in rows)
            drafted = sum(r["is_drafted"] for r in rows)
            cat_breakdown[cat] = {
                "n": n,
                "flagged_count": flagged,
                "flagged_rate": round(flagged / n, 4),
                "low_conf_count": low_c,
                "drafted_count": drafted,
            }

        total_flagged = sum(r["flagged_safe"] for r in oos_rows)
        total_low_c = sum(r["low_confidence"] for r in oos_rows)
        total_drafted = sum(r["is_drafted"] for r in oos_rows)
        cand_summary["ml_oos"] = {
            "n_total": len(oos_rows),
            "flagged_count": total_flagged,
            "flagged_rate": round(total_flagged / len(oos_rows), 4),
            "low_conf_count": total_low_c,
            "low_conf_rate": round(total_low_c / len(oos_rows), 4),
            "drafted_count": total_drafted,
            "false_draft_rate": round(total_drafted / len(oos_rows), 4),
            "by_category": cat_breakdown,
        }
        print(f"  [ml_oos]   Flagged Safe: {cand_summary['ml_oos']['flagged_rate']:.2%} ({total_flagged}/80) | Drafted (False Positives): {total_drafted}/80")

        # ---------------------------------------------------------------------
        # Suite 3: System Acceptance Suite (156 cases)
        # ---------------------------------------------------------------------
        with open(files_to_lock["acceptance_cases"], "r", encoding="utf-8") as f:
            acc_cases = [json.loads(line) for line in f if line.strip()]

        acc_rows = []
        action_match_count = 0
        supported_action_match_count = 0
        supported_total = 0
        answerable_drafted_count = 0
        answerable_total = 0
        sensitive_cases_total = 0
        sensitive_manager_routed_count = 0
        mandatory_escalations_total = 0
        mandatory_escalations_safe_count = 0

        for c in acc_cases:
            order_ctx = c.get("context", {}).get("extracted_slots", {})
            req = {"message": c["text"], "as_of": utc_now, "order_context": order_ctx}
            ans, evidence = cand_engine._analyse(req)
            rec = ans["routing"]["recommendation"]
            reasons = ans["routing"]["reason_codes"]
            pred_intent = ans["intent"]["label"]
            pred_conf = ans["intent"]["probability"]

            adapted_action = adapt_engine_recommendation_to_routing_action(rec, reasons)
            expected = c.get("expected", {})
            exp_actions = expected.get("actions", [])
            is_action_match = adapted_action in exp_actions
            if is_action_match:
                action_match_count += 1

            slice_tag = c.get("primary_slice", "")
            is_supported_slice = "supported" in slice_tag or c.get("true_intent") in SUPPORTED_12_INTENTS
            if is_supported_slice:
                supported_total += 1
                if is_action_match:
                    supported_action_match_count += 1

            is_ans = expected.get("answerable", False) or expected.get("draft_expected", False)
            if is_ans:
                answerable_total += 1
                if rec == "draft":
                    answerable_drafted_count += 1

            # Sensitive authority retention check
            is_sensitive_case = (
                c.get("true_intent") in policy_v2.sensitive_action_intents
                or pred_intent in policy_v2.sensitive_action_intents
            )
            if is_sensitive_case:
                sensitive_cases_total += 1
                if "requires_authority" in reasons:
                    sensitive_manager_routed_count += 1

            # Mandatory escalation safety
            if expected.get("must_escalate", False):
                mandatory_escalations_total += 1
                # Safe means it escalated or abstained (did not draft)
                if rec in ("escalate", "abstain"):
                    mandatory_escalations_safe_count += 1

            row = {
                "candidate": cand_name,
                "suite": "system_acceptance_156",
                "case_id": c["id"],
                "true_intent": c.get("true_intent"),
                "predicted_intent": pred_intent,
                "confidence": pred_conf,
                "engine_recommendation": rec,
                "adapted_routing_action": adapted_action,
                "expected_actions": exp_actions,
                "action_match": is_action_match,
                "reason_codes": reasons,
            }
            acc_rows.append(row)
            raw_predictions_file.write(json.dumps(row) + "\n")

        gold_acc_intents = [c.get("true_intent") for c in acc_cases if c.get("true_intent")]
        pred_acc_intents = [r["predicted_intent"] for r in acc_rows if r["true_intent"]]
        raw_intent_acc = M.accuracy(gold_acc_intents, pred_acc_intents)
        raw_macro_f1 = M.macro_f1(gold_acc_intents, pred_acc_intents)

        cand_summary["system_acceptance"] = {
            "n_total": len(acc_cases),
            "raw_intent_accuracy": round(raw_intent_acc, 4),
            "raw_intent_macro_f1": round(raw_macro_f1, 4),
            "action_match_count": action_match_count,
            "action_match_rate": round(action_match_count / len(acc_cases), 4),
            "supported_cases_total": supported_total,
            "supported_action_match_count": supported_action_match_count,
            "supported_action_match_rate": round(supported_action_match_count / supported_total, 4) if supported_total else 0.0,
            "answerable_total": answerable_total,
            "answerable_drafted_count": answerable_drafted_count,
            "supported_draftability_rate": round(answerable_drafted_count / answerable_total, 4) if answerable_total else 0.0,
            "sensitive_cases_total": sensitive_cases_total,
            "sensitive_authority_count": sensitive_manager_routed_count,
            "sensitive_authority_rate": round(sensitive_manager_routed_count / sensitive_cases_total, 4) if sensitive_cases_total else 0.0,
            "mandatory_escalations_total": mandatory_escalations_total,
            "mandatory_escalations_safe_count": mandatory_escalations_safe_count,
            "mandatory_escalations_safe_rate": round(mandatory_escalations_safe_count / mandatory_escalations_total, 4) if mandatory_escalations_total else 0.0,
        }
        print(f"  [acceptance] Overall Action Match: {cand_summary['system_acceptance']['action_match_rate']:.2%} ({action_match_count}/156)")
        print(f"               Supported Action Match: {cand_summary['system_acceptance']['supported_action_match_rate']:.2%} ({supported_action_match_count}/{supported_total})")
        print(f"               Supported Draftability: {cand_summary['system_acceptance']['supported_draftability_rate']:.2%} ({answerable_drafted_count}/{answerable_total})")
        print(f"               Authority Retention:    {cand_summary['system_acceptance']['sensitive_authority_rate']:.2%} ({sensitive_manager_routed_count}/{sensitive_cases_total})")
        print(f"               Mandatory Esc Safe:     {cand_summary['system_acceptance']['mandatory_escalations_safe_rate']:.2%} ({mandatory_escalations_safe_count}/{mandatory_escalations_total})")

        # ---------------------------------------------------------------------
        # Suite 4: Final Acceptance (24 cases total)
        # ---------------------------------------------------------------------
        fa_rows = []
        fa_correct_intent = 0
        fa_action_match = 0
        fa_drafted = 0
        fa_abstained = 0
        fa_escalated = 0

        for c in final_cases:
            cid = c["id"]
            query = c["query"]
            exp_intent = c["intent"]
            exp_action = c["expected_action"]  # 'draft', 'manual_fallback', 'escalate'

            req = {
                "message": query,
                "as_of": utc_now,
                "order_context": {"order_id": c.get("order_id")} if c.get("order_id") else {},
            }
            ans, evidence = cand_engine._analyse(req)
            rec = ans["routing"]["recommendation"]
            reasons = ans["routing"]["reason_codes"]
            pred_intent = ans["intent"]["label"]
            pred_conf = ans["intent"]["probability"]

            adapted_action = adapt_engine_recommendation_to_routing_action(rec, reasons)

            # Map expected action to routing action
            # 'draft' -> 'retrieve_draft', 'manual_fallback' -> 'manual_fallback', 'escalate' -> 'escalate'
            exp_mapped = adapt_engine_recommendation_to_routing_action(exp_action)
            is_match = (adapted_action == exp_mapped)
            if is_match:
                fa_action_match += 1

            if pred_intent == exp_intent:
                fa_correct_intent += 1

            if rec == "draft":
                fa_drafted += 1
            elif rec == "abstain":
                fa_abstained += 1
            elif rec == "escalate":
                fa_escalated += 1

            row = {
                "candidate": cand_name,
                "suite": "final_acceptance_24",
                "case_id": cid,
                "query": query,
                "true_intent": exp_intent,
                "predicted_intent": pred_intent,
                "confidence": pred_conf,
                "engine_recommendation": rec,
                "adapted_action": adapted_action,
                "expected_action": exp_action,
                "action_match": is_match,
                "reason_codes": reasons,
            }
            fa_rows.append(row)
            raw_predictions_file.write(json.dumps(row) + "\n")

        cand_summary["final_acceptance"] = {
            "n_total": len(final_cases),
            "intent_accuracy": round(fa_correct_intent / len(final_cases), 4),
            "action_match_count": fa_action_match,
            "action_match_rate": round(fa_action_match / len(final_cases), 4),
            "draft_count": fa_drafted,
            "abstain_count": fa_abstained,
            "escalate_count": fa_escalated,
        }
        print(f"  [final_acc]  Intent Acc: {cand_summary['final_acceptance']['intent_accuracy']:.2%} ({fa_correct_intent}/24) | Action Match: {cand_summary['final_acceptance']['action_match_rate']:.2%} ({fa_action_match}/24)")

        results["suites"][cand_name] = cand_summary

    raw_predictions_file.close()

    # Save summary json
    with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    elapsed = round(time.perf_counter() - start_time, 2)
    print("\n" + "=" * 80)
    print(f"[Worker A] Comparative evaluation finished in {elapsed}s.")
    print(f"Saved artifacts to {output_dir}")
    print("=" * 80)

    return results


if __name__ == "__main__":
    out_dir = REPO_ROOT / "artifacts/evaluation/candidate_comparison_20261113"
    run_comparative_evaluation(out_dir)

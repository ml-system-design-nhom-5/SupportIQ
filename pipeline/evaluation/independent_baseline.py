"""Independent Task C baseline freeze and raw-artifact denominator recomputation.

Locks SHA-256 hashes of source modules, policy/KB artifacts, candidate models,
and frozen gold benchmarks, and independently recomputes raw draft eligibility,
correct-intent draft eligibility, strict mandatory actions, and abstention
denominators directly from raw prediction and live execution artifacts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from apps.core_backend.intent.routing import STANDARD_INTENTS_46


BASELINE_IDENTITY_FILES: dict[str, str] = {
    "drafting_runtime": "apps/ai_service/drafting.py",
    "ai_engine": "apps/ai_service/engine.py",
    "ai_gateway_main": "apps/ai_service/main.py",
    "gemini_client": "apps/core_backend/llm/gemini.py",
    "intent_routing": "apps/core_backend/intent/routing.py",
    "ml_inference_app": "apps/ml_inference/app.py",
    "compare_trained_candidates_script": "scripts/compare_trained_candidates.py",
    "intent_policy_v2": "apps/core_backend/config/policies/intent_policy.v2.json",
    "approved_kb_v2": "data/knowledge/approved_kb.v2.json",
    "kb_release": "apps/ai_service/kb-release.json",
    "ml_noise": "data/benchmarks/autoeval/v1/ml_noise.jsonl",
    "ml_oos": "data/benchmarks/autoeval/v1/ml_oos.jsonl",
    "system_acceptance": "data/benchmarks/system/v2/acceptance/cases.jsonl",
    "final_acceptance": "data/benchmarks/final_acceptance/cases.jsonl",
    "serving_weights": "artifacts/models/trained/distilbert-supportiq/model.safetensors",
    "serving_tokenizer": "artifacts/models/trained/distilbert-supportiq/tokenizer.json",
    "serving_config": "artifacts/models/trained/distilbert-supportiq/config.json",
    "rejected_candidate_weights": "artifacts/models/finetuned/supportpilot-distilbert/model.safetensors",
    "rejected_candidate_tokenizer": "artifacts/models/finetuned/supportpilot-distilbert/tokenizer.json",
    "rejected_candidate_config": "artifacts/models/finetuned/supportpilot-distilbert/config.json",
    "candidate_comparison_raw": "artifacts/evaluation/candidate_comparison_20261113/raw_predictions.jsonl",
    "candidate_comparison_summary": "artifacts/evaluation/candidate_comparison_20261113/summary.json",
    "live_r3_evidence": "artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/evidence_records.jsonl",
    "live_r3_summary": "artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/summary.json",
    "live_r3_accounting": "artifacts/evaluation/coordinator-final-live-20261112-r3/final-evidence-20261112-151514-078471/accounting_recomputed.json",
}

KNOWN_UNINJECTED_ACCEPTANCE_IDS = {"unc-return_policy-04"}


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_46_label_bijection(config_path: Path) -> dict[str, Any]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    id2label = {int(k): v for k, v in cfg.get("id2label", {}).items()}
    valid = (
        len(id2label) == 46
        and set(id2label.keys()) == set(range(46))
        and set(id2label.values()) == set(STANDARD_INTENTS_46)
    )
    return {
        "valid_46_label_bijection": valid,
        "num_labels": len(id2label),
        "missing_from_standard_46": sorted(set(STANDARD_INTENTS_46) - set(id2label.values())),
        "extra_labels": sorted(set(id2label.values()) - set(STANDARD_INTENTS_46)),
    }


def get_git_state(repo_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()
    except Exception:
        commit = "unknown"
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, text=True
        ).strip()
        dirty = [line for line in status.splitlines() if line.strip()]
    except Exception:
        dirty = []
    return {
        "commit": commit,
        "is_dirty": bool(dirty),
        "dirty_files": dirty,
    }


def freeze_baseline_identities(repo_root: Path) -> dict[str, Any]:
    locked: dict[str, Any] = {}
    missing: list[str] = []
    for key, rel_path in BASELINE_IDENTITY_FILES.items():
        full_path = repo_root / rel_path
        if not full_path.exists():
            missing.append(rel_path)
            locked[key] = {"path": rel_path, "exists": False, "sha256": None, "size_bytes": None}
            continue
        entry: dict[str, Any] = {
            "path": rel_path,
            "exists": True,
            "sha256": compute_file_sha256(full_path),
            "size_bytes": full_path.stat().st_size,
        }
        if key.endswith("_config"):
            entry["label_bijection"] = verify_46_label_bijection(full_path)
        locked[key] = entry

    return {
        "git": get_git_state(repo_root),
        "missing_files": missing,
        "artifacts": locked,
    }


def _recompute_candidate_from_raw(
    candidate: str,
    raw_rows: list[dict[str, Any]],
    system_cases_by_id: dict[str, dict[str, Any]],
    final_cases_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cand_rows = [r for r in raw_rows if r.get("candidate") == candidate]

    # 1. Final acceptance answerable 12 (decide_route slice)
    fa12 = [r for r in cand_rows if r.get("suite") == "final_acceptance_answerable_12"]
    fa12_raw_draft = [r for r in fa12 if r.get("routing_action") == "retrieve_draft"]
    fa12_correct_draft = [
        r for r in fa12_raw_draft
        if r.get("predicted_intent") == final_cases_by_id[r["case_id"]]["intent"]
    ]
    fa12_wrong_draft = [
        r for r in fa12_raw_draft
        if r.get("predicted_intent") != final_cases_by_id[r["case_id"]]["intent"]
    ]
    fa12_actions = Counter(r.get("routing_action") for r in fa12)

    # 2. Final acceptance 24 (full suite via Engine._analyse + adapter)
    fa24 = [r for r in cand_rows if r.get("suite") == "final_acceptance_24"]
    fa24_ans = [r for r in fa24 if final_cases_by_id[r["case_id"]].get("is_answerable")]
    fa24_unans = [r for r in fa24 if not final_cases_by_id[r["case_id"]].get("is_answerable")]
    fa24_active_unans = [
        r for r in fa24_unans
        if final_cases_by_id[r["case_id"]].get("fixture_boundary") == "active_kb"
    ]
    fa24_inj_unans = [
        r for r in fa24_unans
        if final_cases_by_id[r["case_id"]].get("fixture_boundary") == "injected_synthetic"
    ]
    fa24_ans_raw_draft = [r for r in fa24_ans if r.get("adapted_action") == "retrieve_draft"]
    fa24_ans_correct_draft = [
        r for r in fa24_ans_raw_draft
        if r.get("predicted_intent") == final_cases_by_id[r["case_id"]]["intent"]
    ]
    fa24_active_unans_draft_leaks = [
        r["case_id"] for r in fa24_active_unans if r.get("adapted_action") == "retrieve_draft"
    ]
    fa24_inj_unans_uninjected_draft = [
        r["case_id"] for r in fa24_inj_unans if r.get("adapted_action") == "retrieve_draft"
    ]

    # 3. System acceptance 156 (known acceptance regression suite, NOT unseen holdout)
    sa = [r for r in cand_rows if r.get("suite") == "system_acceptance_156"]
    sa_draft_exp_34 = [
        r for r in sa if system_cases_by_id[r["case_id"]]["expected"].get("draft_expected")
    ]
    sa_34_raw_draft = [r for r in sa_draft_exp_34 if r.get("adapted_routing_action") == "retrieve_draft"]
    sa_34_correct_draft = [
        r for r in sa_34_raw_draft
        if r.get("predicted_intent") == system_cases_by_id[r["case_id"]]["true_intent"]
    ]
    sa_34_wrong_draft = [
        r for r in sa_34_raw_draft
        if r.get("predicted_intent") != system_cases_by_id[r["case_id"]]["true_intent"]
    ]

    sa_supported_60 = [
        r for r in sa if system_cases_by_id[r["case_id"]].get("primary_slice") == "supported"
    ]
    sa_60_raw_draft = [r for r in sa_supported_60 if r.get("adapted_routing_action") == "retrieve_draft"]
    sa_60_correct_draft = [
        r for r in sa_60_raw_draft
        if r.get("predicted_intent") == system_cases_by_id[r["case_id"]]["true_intent"]
    ]

    # Strict mandatory escalation N=63
    sa_mand = [
        r for r in sa if system_cases_by_id[r["case_id"]]["expected"].get("must_escalate")
    ]
    mand_action_counts = Counter(r.get("adapted_routing_action") for r in sa_mand)
    mand_strict_match = [
        r["case_id"]
        for r in sa_mand
        if r.get("adapted_routing_action") in system_cases_by_id[r["case_id"]]["expected"]["actions"]
    ]
    mand_draft_rows = [r for r in sa_mand if r.get("adapted_routing_action") == "retrieve_draft"]
    mand_real_leaks = [r["case_id"] for r in mand_draft_rows if r["case_id"] not in KNOWN_UNINJECTED_ACCEPTANCE_IDS]
    mand_not_executed = [r["case_id"] for r in mand_draft_rows if r["case_id"] in KNOWN_UNINJECTED_ACCEPTANCE_IDS]

    sa_all_actions = Counter(r.get("adapted_routing_action") for r in sa)

    # 4. OOD 80 & Noise 420
    oos = [r for r in cand_rows if r.get("suite") == "ml_oos"]
    oos_drafted = [r["case_id"] for r in oos if r.get("is_drafted")]
    oos_safe = [r["case_id"] for r in oos if r.get("flagged_safe")]

    noise = [r for r in cand_rows if r.get("suite") == "ml_noise"]
    noise_correct = sum(1 for r in noise if r.get("predicted_intent") == r.get("true_intent"))
    noise_safe = sum(1 for r in noise if r.get("safe_routing"))

    return {
        "final_acceptance_answerable_12": {
            "n_total": len(fa12),
            "raw_draft_eligible_count": len(fa12_raw_draft),
            "raw_draft_eligible_rate": round(len(fa12_raw_draft) / len(fa12), 6) if fa12 else 0.0,
            "raw_draft_case_ids": [r["case_id"] for r in fa12_raw_draft],
            "correct_intent_draft_eligible_count": len(fa12_correct_draft),
            "correct_intent_draft_eligible_rate": round(len(fa12_correct_draft) / len(fa12), 6) if fa12 else 0.0,
            "correct_intent_draft_case_ids": [r["case_id"] for r in fa12_correct_draft],
            "wrong_intent_draft_eligible_count": len(fa12_wrong_draft),
            "wrong_intent_draft_case_ids": [
                {
                    "case_id": r["case_id"],
                    "expected_intent": final_cases_by_id[r["case_id"]]["intent"],
                    "predicted_intent": r.get("predicted_intent"),
                    "confidence": r.get("confidence"),
                }
                for r in fa12_wrong_draft
            ],
            "action_breakdown": dict(fa12_actions),
            "pre_llm_non_draft_denominator": len(fa12) - len(fa12_raw_draft),
        },
        "final_acceptance_24": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "n_total": len(fa24),
            "answerable_12": {
                "n": len(fa24_ans),
                "raw_draft_eligible_count": len(fa24_ans_raw_draft),
                "correct_intent_draft_eligible_count": len(fa24_ans_correct_draft),
            },
            "unanswerable_12": {
                "n": len(fa24_unans),
                "active_kb_n": len(fa24_active_unans),
                "active_kb_draft_leaks": fa24_active_unans_draft_leaks,
                "injected_synthetic_n": len(fa24_inj_unans),
                "injected_static_uninjected_not_executed": fa24_inj_unans_uninjected_draft,
            },
        },
        "system_acceptance_156": {
            "suite_role": "known_acceptance_regression_not_unseen_holdout",
            "n_total": len(sa),
            "action_breakdown": dict(sa_all_actions),
            "exact_expected_action_matches": sum(1 for r in sa if r.get("action_match")),
            "draft_expected_34": {
                "n": len(sa_draft_exp_34),
                "raw_draft_eligible_count": len(sa_34_raw_draft),
                "raw_draft_eligible_rate": round(len(sa_34_raw_draft) / len(sa_draft_exp_34), 6) if sa_draft_exp_34 else 0.0,
                "correct_intent_draft_eligible_count": len(sa_34_correct_draft),
                "correct_intent_draft_eligible_rate": round(len(sa_34_correct_draft) / len(sa_draft_exp_34), 6) if sa_draft_exp_34 else 0.0,
                "wrong_intent_draft_eligible_count": len(sa_34_wrong_draft),
                "wrong_intent_draft_case_ids": [r["case_id"] for r in sa_34_wrong_draft],
                "abstention_or_non_draft_count": len(sa_draft_exp_34) - len(sa_34_raw_draft),
            },
            "primary_slice_supported_60": {
                "n": len(sa_supported_60),
                "raw_draft_eligible_count": len(sa_60_raw_draft),
                "correct_intent_draft_eligible_count": len(sa_60_correct_draft),
            },
            "mandatory_escalation_63": {
                "n": len(sa_mand),
                "strict_escalate_count": mand_action_counts.get("escalate", 0),
                "abstain_manual_fallback_count": mand_action_counts.get("manual_fallback", 0),
                "draft_eligible_total_count": mand_action_counts.get("retrieve_draft", 0),
                "real_unsafe_draft_leak_count": len(mand_real_leaks),
                "real_unsafe_draft_leak_case_ids": mand_real_leaks,
                "uninjected_fault_not_executed_count": len(mand_not_executed),
                "uninjected_fault_not_executed_case_ids": mand_not_executed,
                "strict_expected_actions_match_count": len(mand_strict_match),
                "strict_expected_actions_match_rate": round(len(mand_strict_match) / len(sa_mand), 6) if sa_mand else 0.0,
                "non_drafting_safe_count": len(sa_mand) - len(mand_draft_rows),
                "non_drafting_safe_rate": round((len(sa_mand) - len(mand_draft_rows)) / len(sa_mand), 6) if sa_mand else 0.0,
                "accounting_note": "abstain/manual_fallback != escalate; strict compliance counts only actions in expected.actions.",
            },
        },
        "ml_oos_80": {
            "n_total": len(oos),
            "flagged_safe_count": len(oos_safe),
            "flagged_safe_rate": round(len(oos_safe) / len(oos), 6) if oos else 0.0,
            "false_draft_eligible_count": len(oos_drafted),
            "false_draft_case_ids": oos_drafted,
        },
        "ml_noise_420": {
            "n_total": len(noise),
            "raw_intent_correct_count": noise_correct,
            "raw_intent_accuracy": round(noise_correct / len(noise), 6) if noise else 0.0,
            "safe_routing_count": noise_safe,
            "safe_routing_rate": round(noise_safe / len(noise), 6) if noise else 0.0,
        },
    }


def _recompute_live_r3(
    live_rows: list[dict[str, Any]],
    final_cases_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    http_rows = [r for r in live_rows if r.get("component_evidence") == "application_postgresql_gateway"]
    fixture_rows = [r for r in live_rows if r.get("component_evidence") != "application_postgresql_gateway"]
    ans_rows = [r for r in http_rows if r.get("slice") == "product_12_answerable"]

    pre_llm_draft_routed = [
        r for r in ans_rows
        if ((r.get("raw_model_routing") or {}).get("routing") or {}).get("recommendation") == "draft"
    ]
    pre_llm_abstained = [
        r for r in ans_rows
        if ((r.get("raw_model_routing") or {}).get("routing") or {}).get("recommendation") != "draft"
    ]
    terminal_draft_ready = [r for r in ans_rows if r.get("terminal_status") == "draft_ready"]
    terminal_llm_unavailable = [r for r in ans_rows if r.get("terminal_status") == "llm_unavailable"]
    correct_intent_and_draft_ready = [
        r for r in terminal_draft_ready
        if ((r.get("raw_model_routing") or {}).get("intent") or {}).get("label")
        == final_cases_by_id[r["case_id"]]["intent"]
    ]

    all_attempts: list[dict[str, Any]] = []
    for r in live_rows:
        atts = (r.get("llm_metadata") or {}).get("attempts") or []
        for att in atts:
            all_attempts.append({"case_id": r["case_id"], **att})

    return {
        "total_submitted": len(live_rows),
        "http_application_cases": len(http_rows),
        "component_fixture_cases": len(fixture_rows),
        "customer_no_auto_send_observed_http": sum(1 for r in http_rows if r.get("customer_no_auto_send_observed") is True),
        "answerable_12": {
            "n": len(ans_rows),
            "pre_llm_draft_routed_count": len(pre_llm_draft_routed),
            "pre_llm_abstained_count": len(pre_llm_abstained),
            "correct_intent_pre_llm_draft_routed_count": sum(
                1
                for r in pre_llm_draft_routed
                if ((r.get("raw_model_routing") or {}).get("intent") or {}).get("label")
                == final_cases_by_id[r["case_id"]]["intent"]
            ),
            "terminal_draft_ready_count": len(terminal_draft_ready),
            "terminal_draft_ready_case_ids": [r["case_id"] for r in terminal_draft_ready],
            "correct_intent_and_terminal_draft_ready_count": len(correct_intent_and_draft_ready),
            "terminal_llm_unavailable_count": len(terminal_llm_unavailable),
            "terminal_llm_unavailable_case_ids": [r["case_id"] for r in terminal_llm_unavailable],
        },
        "provider_attempts_observed": {
            "total_attempt_records": len(all_attempts),
            "timeout_attempt_count": sum(1 for a in all_attempts if a.get("status") == "llm_timeout"),
            "success_attempt_count": sum(1 for a in all_attempts if a.get("status") == "success"),
            "distinct_tickets_calling_llm": len({a["case_id"] for a in all_attempts}),
        },
    }


def build_independent_baseline_report(repo_root: Path) -> dict[str, Any]:
    identities = freeze_baseline_identities(repo_root)
    raw_rows = load_jsonl(repo_root / BASELINE_IDENTITY_FILES["candidate_comparison_raw"])
    system_cases = {c["id"]: c for c in load_jsonl(repo_root / BASELINE_IDENTITY_FILES["system_acceptance"])}
    final_cases = {c["id"]: c for c in load_jsonl(repo_root / BASELINE_IDENTITY_FILES["final_acceptance"])}
    live_rows = load_jsonl(repo_root / BASELINE_IDENTITY_FILES["live_r3_evidence"])

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "report_type": "task_c_independent_baseline_freeze",
        "baseline_identities": identities,
        "recomputed_metrics": {
            "serving_distilbert_supportiq": _recompute_candidate_from_raw(
                "distilbert-supportiq", raw_rows, system_cases, final_cases
            ),
            "rejected_supportpilot_distilbert": _recompute_candidate_from_raw(
                "supportpilot-distilbert", raw_rows, system_cases, final_cases
            ),
            "live_r3_run": _recompute_live_r3(live_rows, final_cases),
        },
    }

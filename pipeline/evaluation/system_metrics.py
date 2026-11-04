"""System evaluation metrics aggregators, Wilson score intervals, and quality gates."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    CaseResult,
    SystemConfig,
)


def compute_wilson_ci(
    k: int,
    n: int,
    confidence: float = 0.95,
) -> Optional[Tuple[float, float]]:
    """Compute Wilson score confidence interval for a binomial proportion k/n.
    Strictly applicable ONLY to binomial counts (e.g. guardrail pass rate, accuracy),
    never to continuous averages (such as Recall@3 or durations).
    """
    if n <= 0 or k < 0 or k > n:
        return None

    # Normal critical value (e.g. 1.95996 for 95%)
    # Using 1.959963984540054 for standard 95% interval
    z = 1.959963984540054
    p = k / n
    denominator = 1.0 + (z * z) / n
    centre = p + (z * z) / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p) / n) + ((z * z) / (4.0 * n * n)))

    lower = max(0.0, (centre - spread) / denominator)
    upper = min(1.0, (centre + spread) / denominator)
    return (round(lower, 4), round(upper, 4))


def _normalize_doc_key(doc_id: Any, version: Any) -> Tuple[str, str]:
    d_str = str(doc_id).strip()
    v_str = str(version).strip()
    if "." not in v_str:
        v_str = f"{v_str}.0"
    return (d_str, v_str)


def aggregate_system_metrics(
    cases: List[SystemCase],
    results: List[CaseResult],
) -> Dict[str, Any]:
    """Pure aggregator computing system evaluation metrics across routing, retrieval, drafting,
    and robustness slices.
    Strictly validates uniqueness and correspondence of case IDs.
    """
    total_cases = len(cases)
    if total_cases == 0:
        return {
            "summary": {
                "total_cases": 0,
                "executed_cases": 0,
                "completed_ok": 0,
                "timeouts": 0,
                "errors": 0,
                "missing": 0,
            },
            "routing": {
                "total_cases": 0,
                "must_escalate_total": 0,
                "must_escalate_correct": 0,
                "must_escalate_success_rate": "N/A",
                "must_escalate_ci": None,
                "guardrail_passed": "N/A",
                "coverage": "N/A",
                "coverage_ci": None,
                "selective_accuracy": "N/A",
                "selective_accuracy_ci": None,
                "draft_yield": "N/A",
            },
            "retrieval": {
                "total_cases": 0,
                "answerable_count": 0,
                "unanswerable_count": 0,
                "recall_at_3": "N/A",
                "hit_at_3": "N/A",
                "hit_at_3_ci": None,
                "false_evidence_count": 0,
                "false_evidence_rate": "N/A",
                "false_evidence_ci": None,
                "safety_violations": 0,
                "safety_guardrail_passed": True,
            },
            "drafting": {
                "draft_expected_count": 0,
                "draft_produced_count": 0,
                "draft_coverage": "N/A",
            },
            "by_slice": {},
        }

    cases_by_id: Dict[str, SystemCase] = {c.id: c for c in cases}
    results_by_id: Dict[str, CaseResult] = {}

    for r in results:
        cid = r.case_id
        if cid not in cases_by_id:
            raise EvaluationError(f"Extra result ID '{cid}' not declared in benchmark cases")
        if cid in results_by_id:
            raise EvaluationError(f"Duplicate result ID '{cid}' found in execution results")
        results_by_id[cid] = r

    # Summary counts
    executed_cases = len(results)
    completed_ok = sum(1 for r in results if r.execution_status == "ok")
    timeouts = sum(1 for r in results if r.execution_status == "timeout")
    errors = sum(1 for r in results if r.execution_status == "error")
    missing_count = total_cases - len(results_by_id)

    # 1. Routing metrics
    must_escalate_total = 0
    must_escalate_correct = 0
    routing_accepted_draft_count = 0
    routing_selective_correct = 0
    actual_draft_yield_count = 0

    for c in cases:
        r = results_by_id.get(c.id)

        # Escalation guardrail: missing result still counts in denominator!
        if c.expected.must_escalate:
            must_escalate_total += 1
            if r is not None and r.execution_status == "ok":
                # Must be correctly routed to escalate
                action = r.final_action or r.routing_action
                if action == "escalate":
                    must_escalate_correct += 1

        if r is not None:
            # Routing coverage based on initial routing action
            init_action = r.routing_action or r.final_action
            if init_action == "retrieve_draft":
                routing_accepted_draft_count += 1
                if r.predicted_intent == c.true_intent:
                    routing_selective_correct += 1

            # Draft yield: actual final draft produced
            if r.draft_body is not None and r.draft_body.strip():
                actual_draft_yield_count += 1
            elif r.final_action == "retrieve_draft" and r.draft_kind is not None:
                actual_draft_yield_count += 1

    if must_escalate_total == 0:
        guardrail_passed: Any = "N/A"
        must_escalate_rate: Any = "N/A"
        must_escalate_ci = None
    else:
        # Exact integer matching without float rounding leak
        guardrail_passed = (must_escalate_correct == must_escalate_total)
        must_escalate_rate = round(must_escalate_correct / must_escalate_total, 4)
        must_escalate_ci = compute_wilson_ci(must_escalate_correct, must_escalate_total)

    coverage = round(routing_accepted_draft_count / total_cases, 4) if total_cases > 0 else "N/A"
    coverage_ci = compute_wilson_ci(routing_accepted_draft_count, total_cases) if total_cases > 0 else None

    selective_acc = (
        round(routing_selective_correct / routing_accepted_draft_count, 4)
        if routing_accepted_draft_count > 0
        else "N/A"
    )
    selective_ci = (
        compute_wilson_ci(routing_selective_correct, routing_accepted_draft_count)
        if routing_accepted_draft_count > 0
        else None
    )

    draft_yield = round(actual_draft_yield_count / total_cases, 4) if total_cases > 0 else "N/A"

    routing_metrics = {
        "total_cases": total_cases,
        "must_escalate_total": must_escalate_total,
        "must_escalate_correct": must_escalate_correct,
        "must_escalate_success_rate": must_escalate_rate,
        "must_escalate_ci": must_escalate_ci,
        "guardrail_passed": guardrail_passed,
        "coverage": coverage,
        "coverage_ci": coverage_ci,
        "selective_accuracy": selective_acc,
        "selective_accuracy_ci": selective_ci,
        "draft_yield": draft_yield,
    }

    # 2. Retrieval metrics
    answerable_count = 0
    unanswerable_count = 0
    total_recall = 0.0
    hits_at_3 = 0
    false_evidence_count = 0
    safety_violations = 0

    for c in cases:
        r = results_by_id.get(c.id)
        retrieved_keys: Set[Tuple[str, str]] = set()

        if r is not None and r.sources:
            # Deduplicate top 3 sources by (doc_id, version)
            for s in r.sources[:3]:
                doc_id = s.get("doc_id") or s.get("document_id")
                ver = s.get("version", "1.0")
                if doc_id:
                    retrieved_keys.add(_normalize_doc_key(doc_id, ver))
                
                # Check safety flags if reported in source
                if s.get("status") not in (None, "approved"):
                    safety_violations += 1
                if s.get("is_expired") is True or s.get("is_revoked") is True:
                    safety_violations += 1

        if c.expected.answerable:
            answerable_count += 1
            gold_keys: Set[Tuple[str, str]] = {
                _normalize_doc_key(g.get("doc_id"), g.get("version", "1.0"))
                for g in c.expected.gold_sources
                if g.get("doc_id")
            }
            if gold_keys:
                recalled = len(retrieved_keys & gold_keys)
                total_recall += recalled / len(gold_keys)
                if recalled > 0:
                    hits_at_3 += 1
        else:
            unanswerable_count += 1
            if len(retrieved_keys) > 0:
                false_evidence_count += 1

    recall_at_3 = (
        round(total_recall / answerable_count, 4)
        if answerable_count > 0
        else "N/A"
    )
    hit_at_3 = (
        round(hits_at_3 / answerable_count, 4)
        if answerable_count > 0
        else "N/A"
    )
    hit_at_3_ci = (
        compute_wilson_ci(hits_at_3, answerable_count)
        if answerable_count > 0
        else None
    )

    false_evidence_rate = (
        round(false_evidence_count / unanswerable_count, 4)
        if unanswerable_count > 0
        else "N/A"
    )
    false_evidence_ci = (
        compute_wilson_ci(false_evidence_count, unanswerable_count)
        if unanswerable_count > 0
        else None
    )

    retrieval_metrics = {
        "total_cases": total_cases,
        "answerable_count": answerable_count,
        "unanswerable_count": unanswerable_count,
        "recall_at_3": recall_at_3,
        "hit_at_3": hit_at_3,
        "hit_at_3_ci": hit_at_3_ci,
        "false_evidence_count": false_evidence_count,
        "false_evidence_rate": false_evidence_rate,
        "false_evidence_ci": false_evidence_ci,
        "safety_violations": safety_violations,
        "safety_guardrail_passed": (safety_violations == 0),
    }

    # 3. Drafting metrics
    draft_expected_count = sum(1 for c in cases if c.expected.draft_expected)
    draft_produced_count = 0
    for c in cases:
        if c.expected.draft_expected:
            r = results_by_id.get(c.id)
            if r is not None and r.draft_body is not None and r.draft_body.strip():
                draft_produced_count += 1

    draft_coverage = (
        round(draft_produced_count / draft_expected_count, 4)
        if draft_expected_count > 0
        else "N/A"
    )
    drafting_metrics = {
        "draft_expected_count": draft_expected_count,
        "draft_produced_count": draft_produced_count,
        "draft_coverage": draft_coverage,
    }

    # 4. Slices breakdown
    by_slice: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        s_name = c.primary_slice
        if s_name not in by_slice:
            by_slice[s_name] = {"total": 0, "ok": 0, "error": 0, "timeout": 0, "missing": 0}
        by_slice[s_name]["total"] += 1
        r = results_by_id.get(c.id)
        if r is None:
            by_slice[s_name]["missing"] += 1
        elif r.execution_status == "ok":
            by_slice[s_name]["ok"] += 1
        elif r.execution_status == "timeout":
            by_slice[s_name]["timeout"] += 1
        elif r.execution_status == "error":
            by_slice[s_name]["error"] += 1

    return {
        "summary": {
            "total_cases": total_cases,
            "executed_cases": executed_cases,
            "completed_ok": completed_ok,
            "timeouts": timeouts,
            "errors": errors,
            "missing": missing_count,
        },
        "routing": routing_metrics,
        "retrieval": retrieval_metrics,
        "drafting": drafting_metrics,
        "by_slice": by_slice,
    }


def evaluate_system_gates(
    metrics: Dict[str, Any],
    config: SystemConfig,
    evidence_kind: str,
) -> Dict[str, Any]:
    """Evaluate quality and safety gates against system configuration.
    Strictly enforces:
    - Simulated evidence (mock profile) CANNOT pass live acceptance criteria.
    - Exact integer count guardrails (100% means 0 failures, 20000/20001 fails).
    - Threshold comparisons without pre-rounding.
    """
    gates: Dict[str, Dict[str, Any]] = {}
    mandatory = config.mandatory_gates or ["routing_guardrails", "retrieval_safety"]

    # 1. Routing guardrails
    r_metric = metrics.get("routing", {})
    must_esc_total = r_metric.get("must_escalate_total", 0)
    guardrail_passed = r_metric.get("guardrail_passed")
    if must_esc_total == 0:
        gates["routing_guardrails"] = {
            "status": "insufficient_evidence",
            "reason": "No must_escalate cases present in benchmark suite",
        }
    elif guardrail_passed is True:
        gates["routing_guardrails"] = {"status": "pass", "details": f"{must_esc_total}/{must_esc_total} escalated"}
    else:
        gates["routing_guardrails"] = {
            "status": "fail",
            "details": f"Escalated {r_metric.get('must_escalate_correct', 0)}/{must_esc_total}",
        }

    # 2. Retrieval safety
    ret_metric = metrics.get("retrieval", {})
    safety_violations = ret_metric.get("safety_violations", 0)
    if safety_violations == 0:
        gates["retrieval_safety"] = {"status": "pass", "details": "0 safety violations"}
    else:
        gates["retrieval_safety"] = {"status": "fail", "details": f"{safety_violations} safety violations"}

    # 3. Retrieval recall
    target_recall = config.thresholds.get("recall_at_3", 0.80)
    actual_recall = ret_metric.get("recall_at_3")
    ans_count = ret_metric.get("answerable_count", 0)
    if ans_count == 0 or actual_recall == "N/A":
        gates["retrieval_recall"] = {"status": "insufficient_evidence", "reason": "No answerable cases"}
    elif isinstance(actual_recall, (int, float)) and actual_recall >= target_recall:
        gates["retrieval_recall"] = {"status": "pass", "details": f"{actual_recall} >= {target_recall}"}
    else:
        gates["retrieval_recall"] = {"status": "fail", "details": f"{actual_recall} < {target_recall}"}

    # 4. Grounded claims (Human assessment)
    target_grounded = config.thresholds.get("grounded_claims", 0.90)
    human_metric = metrics.get("human_assessment")
    if human_metric is None or human_metric.get("status") == "insufficient_evidence":
        gates["grounded_claims"] = {
            "status": "insufficient_evidence",
            "reason": "Missing or incomplete human claim annotations",
        }
    else:
        grounded_ratio = human_metric.get("supported_claims_ratio")
        if isinstance(grounded_ratio, (int, float)) and grounded_ratio >= target_grounded:
            gates["grounded_claims"] = {"status": "pass", "details": f"{grounded_ratio} >= {target_grounded}"}
        else:
            gates["grounded_claims"] = {"status": "fail", "details": f"{grounded_ratio} < {target_grounded}"}

    # 5. ML Macro-F1
    target_f1 = config.thresholds.get("ml_macro_f1", 0.85)
    ml_metric = metrics.get("ml")
    if ml_metric is None or "macro_f1" not in ml_metric:
        gates["ml_macro_f1"] = {"status": "not_evaluated", "reason": "ML holdout benchmark not imported"}
    elif ml_metric.get("macro_f1", 0.0) >= target_f1:
        gates["ml_macro_f1"] = {"status": "pass", "details": f"{ml_metric['macro_f1']} >= {target_f1}"}
    else:
        gates["ml_macro_f1"] = {"status": "fail", "details": f"{ml_metric.get('macro_f1')} < {target_f1}"}

    # 6. Live latency
    target_p95 = config.thresholds.get("warm_p95_seconds", 12.0)
    lat_metric = metrics.get("latency")
    if lat_metric is None or "warm_p95_seconds" not in lat_metric:
        gates["live_latency"] = {"status": "not_evaluated", "reason": "Warm latency measurements not present"}
    elif lat_metric.get("warm_p95_seconds", float("inf")) <= target_p95:
        gates["live_latency"] = {"status": "pass", "details": f"{lat_metric['warm_p95_seconds']}s <= {target_p95}s"}
    else:
        gates["live_latency"] = {"status": "fail", "details": f"{lat_metric.get('warm_p95_seconds')}s > {target_p95}s"}

    # Profile & Evidence verification
    if evidence_kind == "simulated":
        all_mandatory_passed = False
        summary_reason = "Simulated mock runs cannot satisfy live acceptance criteria."
    else:
        all_mandatory_passed = True
        failed_gates = []
        for g_name in mandatory:
            g_info = gates.get(g_name, {"status": "not_evaluated"})
            if g_info["status"] != "pass":
                all_mandatory_passed = False
                failed_gates.append(f"{g_name} ({g_info['status']})")
        
        if all_mandatory_passed:
            summary_reason = "All mandatory acceptance gates passed with certified live evidence."
        else:
            summary_reason = f"Mandatory gates not satisfied: {', '.join(failed_gates)}"

    return {
        "evidence_kind": evidence_kind,
        "gates": gates,
        "all_mandatory_passed": all_mandatory_passed,
        "summary_reason": summary_reason,
    }

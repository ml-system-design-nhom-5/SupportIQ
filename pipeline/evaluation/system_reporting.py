"""System evaluation reporting, Markdown summary generation, and requirements matrix export."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict


def write_system_report(
    run_dir: Path | str,
    metrics: Dict[str, Any],
    gates: Dict[str, Any],
    state: str = "completed",
) -> None:
    """Generate report.md, slices.csv, and requirements_matrix.csv inside the run directory."""
    r_dir = Path(run_dir).resolve()
    r_dir.mkdir(parents=True, exist_ok=True)

    summary = metrics.get("summary", {})
    routing = metrics.get("routing", {})
    retrieval = metrics.get("retrieval", {})
    drafting = metrics.get("drafting", {})
    by_slice = metrics.get("by_slice", {})
    ml = metrics.get("ml", {})
    oversight = metrics.get("oversight", {})
    latency = metrics.get("latency", {})
    gate_dict = gates.get("gates", {})
    evidence_kind = gates.get("evidence_kind", "simulated")
    all_passed = gates.get("all_mandatory_passed", False)
    summary_reason = gates.get("summary_reason", "")

    # Truthful certification status
    if all_passed and evidence_kind == "live":
        cert_status = "certified_live_acceptance"
    elif evidence_kind == "simulated":
        cert_status = "simulated_mock_rejected"
    elif gate_dict.get("grounded_claims", {}).get("status") in ("insufficient_evidence", "not_evaluated"):
        cert_status = "pending_human_acceptance"
    else:
        cert_status = "failed_acceptance_criteria"

    # 1. Generate report.md
    report_lines = [
        "# SupportIQ System Evaluation Report",
        "",
        f"- **Execution State:** `{state}`",
        f"- **Certification Status:** `{cert_status}`",
        f"- **Evidence Kind:** `{evidence_kind}`",
        f"- **Mandatory Acceptance Gates Passed:** `{all_passed}`",
        f"- **Summary Reason:** {summary_reason}",
        "",
    ]

    if evidence_kind == "simulated":
        report_lines.extend([
            "> [!WARNING]",
            "> **Simulated Mock Run:** This run was executed using offline simulated mocks. "
            "Simulated evidence cannot certify live production acceptance criteria.",
            "",
        ])
    elif evidence_kind == "live_experimental":
        report_lines.extend([
            "> Live experimental run: real dependencies with an unapproved benchmark suite. "
            "Results are exploratory and cannot certify acceptance.",
            "",
        ])

    report_lines.extend([
        "## Summary Counts",
        "",
        f"- **Total Cases:** {summary.get('total_cases', 0)}",
        f"- **Executed Cases:** {summary.get('executed_cases', 0)}",
        f"- **Completed OK:** {summary.get('completed_ok', 0)}",
        f"- **Timeouts:** {summary.get('timeouts', 0)}",
        f"- **Errors:** {summary.get('errors', 0)}",
        f"- **Missing Results:** {summary.get('missing', 0)}",
        "",
        "## Gate Evaluation",
        "",
        "| Gate | Status | Details |",
        "|---|---|---|",
    ])

    for g_name, g_info in gate_dict.items():
        st = g_info.get("status", "unknown")
        dt = g_info.get("details") or g_info.get("reason", "")
        report_lines.append(f"| `{g_name}` | `{st}` | {dt} |")

    report_lines.extend([
        "",
        "## Component Metrics",
        "",
        "### Routing & Safety",
        f"- **Routing Coverage:** {routing.get('coverage')} (CI: {routing.get('coverage_ci')})",
        f"- **Selective Accuracy:** {routing.get('selective_accuracy')} (CI: {routing.get('selective_accuracy_ci')})",
        f"- **Final Draft Yield:** {routing.get('draft_yield')}",
        f"- **Escalation Guardrail:** {routing.get('must_escalate_correct', 0)}/{routing.get('must_escalate_total', 0)} "
        f"(Passed: {routing.get('guardrail_passed')})",
        "",
        "### Semantic Retrieval",
        f"- **Recall@3:** {retrieval.get('recall_at_3')}",
        f"- **Hit@3:** {retrieval.get('hit_at_3')} (CI: {retrieval.get('hit_at_3_ci')})",
        f"- **False Evidence Rate:** {retrieval.get('false_evidence_rate')} (CI: {retrieval.get('false_evidence_ci')})",
        f"- **Safety Violations:** {retrieval.get('safety_violations', 0)} (Guardrail: {retrieval.get('safety_guardrail_passed')})",
        "",
        "### Automated Drafting",
        f"- **Draft Expected:** {drafting.get('draft_expected_count', 0)}",
        f"- **Draft Produced:** {drafting.get('draft_produced_count', 0)}",
        f"- **Draft Coverage:** {drafting.get('draft_coverage')}",
        "",
        "### Verified ML Model",
        f"- **Model Type:** {ml.get('model_type', 'N/A')}",
        f"- **Package Version:** {ml.get('package_version', 'N/A')}",
        f"- **Macro-F1:** {ml.get('macro_f1', 'N/A')}",
        f"- **Verification Status:** {ml.get('status', 'unverified')}",
        "",
        "### Human Oversight & Persistence",
        f"- **Total Scenarios:** {oversight.get('total_scenarios', 0)}",
        f"- **Passed Scenarios:** {oversight.get('passed_scenarios', 0)}",
        f"- **Failed Scenarios:** {oversight.get('failed_scenarios', 0)}",
        f"- **Oversight Status:** {oversight.get('status', 'N/A')}",
        "",
        "### Request Latency",
        f"- **Warm p95 Total:** {latency.get('warm_p95_seconds', 'N/A')}s",
        f"- **LLM Branch p95:** {latency.get('llm_branch_p95_seconds', 'N/A')}s",
        f"- **No-LLM Branch p95:** {latency.get('no_llm_p95_seconds', 'N/A')}s",
        "",
    ])

    report_file = r_dir / "report.md"
    report_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    # 2. Generate slices.csv
    slices_file = r_dir / "slices.csv"
    with open(slices_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["slice_name", "total", "ok", "error", "timeout", "missing"])
        for s_name, s_data in sorted(by_slice.items()):
            writer.writerow([
                s_name,
                s_data.get("total", 0),
                s_data.get("ok", 0),
                s_data.get("error", 0),
                s_data.get("timeout", 0),
                s_data.get("missing", 0),
            ])

    # 3. Generate requirements_matrix.csv
    req_file = r_dir / "requirements_matrix.csv"
    matrix_rows = [
        ["ML 10-Fold CV Macro-F1", "Component (ML)", ">= 0.85", metrics.get("ml", {}).get("macro_f1", "N/A"), gate_dict.get("ml_macro_f1", {}).get("status", "not_evaluated")],
        ["Routing Escalation Guardrail", "System E2E", "100% exact", f"{routing.get('must_escalate_correct', 0)}/{routing.get('must_escalate_total', 0)}", gate_dict.get("routing_guardrails", {}).get("status", "unknown")],
        ["Semantic Retrieval Recall@3", "Component / E2E", ">= 0.80", str(retrieval.get("recall_at_3")), gate_dict.get("retrieval_recall", {}).get("status", "unknown")],
        ["Retrieval Safety", "System E2E", "0 violations", f"{retrieval.get('safety_violations', 0)} violations", gate_dict.get("retrieval_safety", {}).get("status", "unknown")],
        ["Human Grounded Claims", "Human Assessment", ">= 0.90", str(metrics.get("human_assessment", {}).get("supported_claims_ratio", "N/A")), gate_dict.get("grounded_claims", {}).get("status", "insufficient_evidence")],
        ["Live Warm Latency p95", "Performance", "<= 12.0s", str(metrics.get("latency", {}).get("warm_p95_seconds", "N/A")), gate_dict.get("live_latency", {}).get("status", "not_evaluated")],
        ["Human Oversight Audit", "Human Oversight", "100% exact", f"{oversight.get('passed_scenarios', 0)}/{oversight.get('total_scenarios', 0)}", gate_dict.get("oversight_compliance", {}).get("status", "not_evaluated")],
    ]

    with open(req_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["requirement", "scope", "target", "actual", "status"])
        for row in matrix_rows:
            writer.writerow(row)

"""Unit tests for System Reporting, markdown report generation, and matrix outputs."""

import pytest
from pathlib import Path

from pipeline.evaluation.system_reporting import write_system_report


def test_write_system_report_creates_expected_artifacts(tmp_path):
    """write_system_report generates report.md, slices.csv, and requirements_matrix.csv."""
    run_dir = tmp_path / "system_run_report"
    run_dir.mkdir()

    metrics = {
        "summary": {
            "total_cases": 156,
            "executed_cases": 156,
            "completed_ok": 150,
            "timeouts": 0,
            "errors": 6,
            "missing": 0,
        },
        "routing": {
            "coverage": 0.45,
            "selective_accuracy": 0.98,
            "draft_yield": 0.42,
            "must_escalate_total": 40,
            "must_escalate_correct": 40,
            "guardrail_passed": True,
            "must_escalate_success_rate": 1.0,
        },
        "retrieval": {
            "answerable_count": 24,
            "unanswerable_count": 18,
            "recall_at_3": 0.92,
            "hit_at_3": 0.96,
            "false_evidence_rate": 0.0,
            "safety_violations": 0,
            "safety_guardrail_passed": True,
        },
        "drafting": {
            "draft_expected_count": 24,
            "draft_produced_count": 24,
            "draft_coverage": 1.0,
        },
        "by_slice": {
            "supported": {"total": 60, "ok": 60, "error": 0, "timeout": 0, "missing": 0},
            "unsupported": {"total": 34, "ok": 34, "error": 0, "timeout": 0, "missing": 0},
            "answerable": {"total": 24, "ok": 24, "error": 0, "timeout": 0, "missing": 0},
            "unanswerable": {"total": 18, "ok": 18, "error": 0, "timeout": 0, "missing": 0},
            "uncertainty_and_faults": {"total": 20, "ok": 14, "error": 6, "timeout": 0, "missing": 0},
        },
    }

    gates = {
        "evidence_kind": "simulated",
        "all_mandatory_passed": False,
        "summary_reason": "Simulated mock runs cannot satisfy live acceptance criteria.",
        "gates": {
            "routing_guardrails": {"status": "pass", "details": "40/40 escalated"},
            "retrieval_safety": {"status": "pass", "details": "0 safety violations"},
            "retrieval_recall": {"status": "pass", "details": "0.92 >= 0.80"},
        },
    }

    write_system_report(run_dir=run_dir, metrics=metrics, gates=gates, state="completed")

    report_md = run_dir / "report.md"
    slices_csv = run_dir / "slices.csv"
    req_csv = run_dir / "requirements_matrix.csv"

    assert report_md.exists()
    assert slices_csv.exists()
    assert req_csv.exists()

    content = report_md.read_text(encoding="utf-8")
    assert "System Evaluation Report" in content
    assert "Simulated mock runs cannot satisfy live acceptance" in content
    assert "Recall@3" in content

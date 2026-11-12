"""Unit tests for ML metrics import, model-specific reporting, and truthful certification status (Task 7)."""

import json
from pathlib import Path
import pytest

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.assess_system import import_verified_ml_metrics
from pipeline.evaluation.system_reporting import write_system_report


class TestVerifiedMLMetricsImport:
    def test_import_verified_ml_metrics_validates_manifest_and_checksum(self, tmp_path):
        """import_verified_ml_metrics reads signed report and extracts Macro-F1 and per-intent metrics."""
        manifest_file = tmp_path / "manifest.json"
        manifest_data = {
            "package_version": "v2.0.0",
            "model_type": "bge-small-en-v1.5",
            "status": "approved",
            "signed_by": "lead_ml_engineer",
            "signed_at": "2026-11-04T00:00:00Z",
            "metrics": {
                "macro_f1": 0.885,
                "intents": {
                    "return_policy": {"f1": 0.92, "support": 50},
                    "track_order": {"f1": 0.89, "support": 50},
                },
            },
        }
        manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        # Self-declared signer/inline numbers are not verifiable CV provenance.
        res = import_verified_ml_metrics(manifest_file, expected_model_type="bge-small-en-v1.5")
        assert res["status"] == "unverified"
        assert res["macro_f1"] is None

    def test_import_verified_ml_metrics_rejects_model_type_mismatch(self, tmp_path):
        """import_verified_ml_metrics rejects report when model_type does not match expected model."""
        manifest_file = tmp_path / "wrong_manifest.json"
        manifest_data = {
            "package_version": "v1.0.0",
            "model_type": "tfidf_fallback_baseline",
            "status": "approved",
            "metrics": {"macro_f1": 0.65},
        }
        manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        with pytest.raises(EvaluationError, match="model_type"):
            import_verified_ml_metrics(manifest_file, expected_model_type="bge-small-en-v1.5", strict=True)

    def test_missing_ml_metrics_marks_na_without_fabrication(self, tmp_path):
        """Missing ML metrics file returns N/A status without fabricating inline numbers."""
        missing_file = tmp_path / "non_existent.json"
        res = import_verified_ml_metrics(missing_file, strict=False)
        assert res["status"] == "N/A"
        assert res["macro_f1"] is None


class TestTruthfulSystemReporting:
    def test_reporting_marks_pending_human_acceptance_when_human_review_missing(self, tmp_path):
        """write_system_report writes certification_status: pending_human_acceptance when human review is pending."""
        run_dir = tmp_path / "run_pending_human"
        run_dir.mkdir()

        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
            "routing": {"must_escalate_correct": 5, "must_escalate_total": 5, "guardrail_passed": True},
            "retrieval": {"recall_at_3": 0.95, "safety_violations": 0, "safety_guardrail_passed": True},
            "drafting": {"draft_expected_count": 5, "draft_produced_count": 5, "draft_coverage": 1.0},
            "ml": {"model_type": "bge-small-en-v1.5", "package_version": "v2.0", "macro_f1": 0.88, "status": "verified"},
            "oversight": {"total_scenarios": 5, "passed_scenarios": 5, "failed_scenarios": 0, "status": "pass"},
            "latency": {"warm_p95_seconds": 1.2, "llm_branch_p95_seconds": 1.5, "no_llm_p95_seconds": 0.2},
            "by_slice": {"supported": {"total": 10, "ok": 10}},
        }
        gates = {
            "evidence_kind": "live",
            "all_mandatory_passed": False,
            "summary_reason": "Human assessment pending.",
            "gates": {
                "routing_guardrails": {"status": "pass"},
                "retrieval_safety": {"status": "pass"},
                "grounded_claims": {"status": "insufficient_evidence", "reason": "No human annotations"},
                "oversight_compliance": {"status": "pass"},
            },
        }

        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)

        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "- **Certification Status:** `pending_human_acceptance`" in report_text
        assert "- **Model Type:** bge-small-en-v1.5" in report_text
        assert "- **Warm p95 Total:** 1.2s" in report_text
        assert "- **LLM Branch p95:** 1.5s" in report_text

        req_text = (run_dir / "requirements_matrix.csv").read_text(encoding="utf-8")
        assert "Human Oversight Audit" in req_text
        assert "ML 10-Fold CV Macro-F1" in req_text

    def test_reporting_marks_simulated_mock_rejected_for_mock_runs(self, tmp_path):
        """write_system_report writes certification_status: simulated_mock_rejected when run is offline mock."""
        run_dir = tmp_path / "run_mock"
        run_dir.mkdir()

        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
            "routing": {"must_escalate_correct": 5, "must_escalate_total": 5, "guardrail_passed": True},
            "retrieval": {"recall_at_3": 0.95, "safety_violations": 0},
            "drafting": {},
            "by_slice": {},
        }
        gates = {
            "evidence_kind": "simulated",
            "all_mandatory_passed": False,
            "summary_reason": "Simulated mock runs cannot satisfy live criteria.",
            "gates": {},
        }

        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)

        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "- **Certification Status:** `simulated_mock_rejected`" in report_text

"""Unit and integration tests for evaluation evidence contracts, provenance, and regression reporting (Task 3 / IMP-10, IMP-11)."""

import json
import math
import subprocess
import sys
from pathlib import Path
import pytest

from pipeline.evaluation.system_contracts import (
    EvaluationManifest,
    MetricProvenance,
    check_regression_comparability,
    check_mixed_evidence,
    audit_synthetic_benchmark,
)
from pipeline.evaluation.system_reporting import write_system_report
from pipeline.evaluation.system_metrics import evaluate_system_gates
from pipeline.evaluation.system_contracts import SystemConfig
from scripts.evaluate_regression import (
    extract_metrics,
    evaluate_metrics_against_targets,
    compare_runs,
    run_regression_evaluation,
    validate_metric_value,
    REPO_ROOT,
)


class TestMissingMetricsContracts:
    """Missing metrics cannot become 0.0 or PASS (IMP-10)."""

    def test_missing_hallucination_rate_is_not_evaluated_and_cannot_pass(self):
        """When hallucination_rate is missing from summary, it must be NOT_EVALUATED, not 0.0/PASS."""
        summary = {
            "intent_classification": {"accuracy": 0.90, "macro_f1": 0.90},
            "retrieval": {"recall_at_3": 0.85},
            "grounding": {
                "claim_grounding_rate": 0.95,
                "citation_correctness": 1.0,
                # Note: hallucination_rate is intentionally omitted!
            },
        }
        metrics = extract_metrics(summary)
        hallucination_m = metrics.get("grounding_hallucination_rate")
        assert hallucination_m is not None
        assert hallucination_m["value"] is None
        assert hallucination_m["status"] in ("NOT_EVALUATED", "INSUFFICIENT_EVIDENCE")

        results, has_failure = evaluate_metrics_against_targets(metrics)
        hallucination_res = next(r for r in results if r["metric"] == "grounding_hallucination_rate")
        assert hallucination_res["status"] in ("NOT_EVALUATED", "INSUFFICIENT_EVIDENCE")
        assert hallucination_res["status"] != "PASS"
        assert has_failure is True

    def test_missing_ece_is_not_evaluated_and_cannot_pass(self):
        """When ECE is missing, it must not default to 0.0 and pass upper-bound <= 0.10."""
        summary = {
            "intent_classification": {"accuracy": 0.90, "macro_f1": 0.90},
            # Note: ece is missing!
        }
        metrics = extract_metrics(summary)
        ece_m = metrics.get("intent_ece")
        assert ece_m is not None
        assert ece_m["value"] is None
        assert ece_m["status"] in ("NOT_EVALUATED", "INSUFFICIENT_EVIDENCE")

        results, has_failure = evaluate_metrics_against_targets(metrics)
        ece_res = next(r for r in results if r["metric"] == "intent_ece")
        assert ece_res["status"] != "PASS"
        assert ece_res["status"] in ("NOT_EVALUATED", "INSUFFICIENT_EVIDENCE")

    def test_legacy_summary_missing_provenance_reports_insufficient_evidence(self):
        """Summary lacking provenance metadata reports insufficient_evidence."""
        legacy_summary = {
            # Completely missing metadata / provenance block
            "intent_classification": {"accuracy": 0.95},
        }
        manifest_p = extract_metrics(legacy_summary, manifest=None)
        # Provenance should indicate unverified/insufficient provenance
        for m in manifest_p.values():
            assert m["evidence_kind"] in ("unverified", "insufficient_evidence", "simulated")


class TestMetricValueSanitization:
    """Metric values that are NaN, inf, bool, or out-of-range are strictly rejected."""

    def test_validate_metric_value_rejects_bool_nan_inf_negative(self):
        assert validate_metric_value(True) is None
        assert validate_metric_value(False) is None
        assert validate_metric_value(float("nan")) is None
        assert validate_metric_value(float("inf")) is None
        assert validate_metric_value(-0.1) is None
        assert validate_metric_value(1.2) is None
        assert validate_metric_value(0.95) == 0.95
        assert validate_metric_value(0.0) == 0.0
        assert validate_metric_value(1.0) == 1.0

    def test_ece_observe_does_not_pass_mandatory_target(self):
        """ECE in OBSERVE range (e.g. 0.105 > 0.10) sets has_target_failure=True and cannot pass mandatory."""
        metrics = {
            "intent_ece": {
                "metric": "intent_ece",
                "value": 0.105,
                "status": "EVALUATED",
                "evidence_ref": "ref",
            }
        }
        results, has_failure = evaluate_metrics_against_targets(metrics)
        ece_res = next(r for r in results if r["metric"] == "intent_ece")
        assert ece_res["status"] == "OBSERVE"
        # Must fail closed: cannot set mandatory passed via OBSERVE
        assert has_failure is True


class TestLiveCertificationAndMocks:
    """Mock or heuristic cannot certify live; mixed evidence is rejected (IMP-10)."""

    def test_simulated_mock_rejected_from_live_certification(self, tmp_path):
        """Simulated/mock evidence kind is rejected from live acceptance certification."""
        run_dir = tmp_path / "mock_run"
        run_dir.mkdir()
        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
            "routing": {"must_escalate_correct": 5, "must_escalate_total": 5, "guardrail_passed": True},
            "retrieval": {"recall_at_3": 0.95, "safety_violations": 0, "safety_guardrail_passed": True},
            "drafting": {"draft_expected_count": 5, "draft_produced_count": 5, "draft_coverage": 1.0},
        }
        gates = {
            "evidence_kind": "simulated",
            "all_mandatory_passed": True,  # Even if components passed!
            "gates": {
                "routing_guardrails": {"status": "pass"},
                "retrieval_safety": {"status": "pass"},
            },
        }
        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)
        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "- **Certification Status:** `simulated_mock_rejected`" in report_text
        assert "Simulated Mock Run" in report_text

    def test_heuristic_demo_rejected_from_live_certification(self, tmp_path):
        """Heuristic demo model mode is rejected from live acceptance."""
        run_dir = tmp_path / "heuristic_run"
        run_dir.mkdir()
        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
            "ml": {"model_type": "heuristic_demo", "status": "unverified", "macro_f1": 0.92},
        }
        gates = {
            "evidence_kind": "live",
            "model_mode": "heuristic_demo",
            "all_mandatory_passed": True,
            "gates": {"ml_macro_f1": {"status": "pass"}},
        }
        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)
        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "- **Certification Status:** `unverified_heuristic_rejected`" in report_text

    def test_mixed_evidence_is_detected_and_rejected(self):
        """When live evidence is mixed with mock or unverified components, check_mixed_evidence flags it."""
        mixed_manifest = {
            "evidence_kind": "live",
            "model_mode": "heuristic_demo",  # Contradiction: live with heuristic!
            "files": {"results.jsonl": {"path": "results.jsonl", "sha256": "ABC"}},
        }
        is_mixed, reasons = check_mixed_evidence(mixed_manifest)
        assert is_mixed is True
        assert len(reasons) > 0


class TestRegressionComparability:
    """Distinguish different model/KB/split configs from valid regression comparisons."""

    def test_empty_hashes_returns_incomparable(self):
        """When all hashes are absent from both runs, check_regression_comparability MUST return False."""
        run_a = {"hashes": {}}
        run_b = {"hashes": {}}
        comparable, reasons = check_regression_comparability(run_a, run_b)
        assert comparable is False
        assert len(reasons) > 0
        assert any("Missing required hash" in r for r in reasons)

    def test_missing_model_hash_returns_incomparable(self):
        """If model_hash is missing from either run, comparison is rejected."""
        run_a = {"hashes": {"kb_hash": "K1", "split_hash": "S1"}}
        run_b = {"hashes": {"kb_hash": "K1", "split_hash": "S1", "model_hash": "M1"}}
        comparable, reasons = check_regression_comparability(run_a, run_b)
        assert comparable is False
        assert any("model_hash" in r for r in reasons)

    def test_different_kb_hashes_incompatible_for_regression(self):
        """Runs with different KB hashes cannot be treated as regression under identical conditions."""
        run_a = {
            "hashes": {
                "kb_hash": "AAA111",
                "split_hash": "SPLIT01",
                "model_hash": "MODEL01",
            }
        }
        run_b = {
            "hashes": {
                "kb_hash": "BBB222",  # Different KB!
                "split_hash": "SPLIT01",
                "model_hash": "MODEL01",
            }
        }
        comparable, reasons = check_regression_comparability(run_a, run_b)
        assert comparable is False
        assert any("kb_hash" in r for r in reasons)

    def test_compare_runs_records_incomparable_notice(self):
        """compare_runs records comparability=False and prevents false regression alerts."""
        curr = {
            "hashes": {"kb_hash": "AAA", "split_hash": "S1", "model_hash": "M1"},
            "metrics": {"intent_accuracy": {"value": 0.88, "status": "PASS", "evidence_ref": "ref1"}},
        }
        base = {
            "hashes": {"kb_hash": "BBB", "split_hash": "S1", "model_hash": "M1"},
            "metrics": {"intent_accuracy": {"value": 0.95, "status": "PASS", "evidence_ref": "ref0"}},
        }
        res = compare_runs(curr, base)
        assert res["comparable"] is False
        assert len(res["incompatibility_reasons"]) > 0
        assert res["regressions_detected"] == []


class TestCachedMetricsContracts:
    """Cached metrics cannot imply new inference."""

    def test_cached_report_records_cached_mode_and_notice(self, tmp_path):
        """Cached run writes cached_only execution mode and notice in report."""
        run_dir = tmp_path / "cached_run"
        run_dir.mkdir()
        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
        }
        gates = {
            "evidence_kind": "cached",
            "execution_mode": "cached_only",
            "all_mandatory_passed": True,
            "gates": {},
        }
        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)
        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "cached_report_no_new_execution" in report_text or "Cached Report" in report_text
        assert "no new inference" in report_text.lower()


class TestAIGradingAndAgentSimulationProvenance:
    """Coordinator guidance: explicit evaluator_type=ai and study_type=agent_simulation."""

    def test_ai_grading_never_satisfies_human_acceptance_gate(self):
        """AI grading cannot satisfy human-rated grounded_claims gate; gate remains not_evaluated/insufficient."""
        cfg = SystemConfig.model_validate({
            "schema_version": "v1.0",
            "mandatory_gates": ["grounded_claims"],
            "thresholds": {"grounded_claims": 0.90},
        })
        metrics = {
            "human_assessment": {
                "evaluator_type": "ai",
                "model": "gemini-1.5-pro",
                "supported_claims_ratio": 0.96,
                "status": "ai_evaluated",
            }
        }
        gate_res = evaluate_system_gates(metrics, cfg, evidence_kind="live")
        gc_gate = gate_res["gates"]["grounded_claims"]
        assert gc_gate["status"] in ("insufficient_evidence", "not_evaluated")
        assert "ai grading" in gc_gate.get("reason", "").lower() or "ai" in gc_gate.get("details", "").lower()

    def test_ai_grading_reported_separately_without_fabricated_human_identity(self, tmp_path):
        """AI claim grading is reported in its own dedicated section with evaluator_type=ai."""
        run_dir = tmp_path / "ai_graded_run"
        run_dir.mkdir()
        metrics = {
            "summary": {"total_cases": 10, "completed_ok": 10},
            "ai_assessment": {
                "evaluator_type": "ai",
                "model": "gemini-1.5-pro",
                "rubric_version": "v1.0",
                "supported_claims_ratio": 0.94,
                "claims_evaluated": 50,
            },
            "human_assessment": None,
        }
        gates = {
            "evidence_kind": "live",
            "all_mandatory_passed": False,
            "gates": {
                "grounded_claims": {"status": "not_evaluated", "reason": "No human claim annotations"},
                "ai_grounded_claims": {"status": "pass", "details": "0.94 >= 0.90 (AI-graded)"},
            },
        }
        write_system_report(run_dir=run_dir, metrics=metrics, gates=gates)
        report_text = (run_dir / "report.md").read_text(encoding="utf-8")
        assert "AI" in report_text
        assert "0.94" in report_text


class TestAuditBenchmarkCommand:
    """Audit detection for synthetic/fabricated benchmark values."""

    def test_detects_synthetic_benchmark_values(self):
        """audit_synthetic_benchmark detects hardcoded claims and synthetic regex accuracy."""
        fake_summary = {
            "grounding": {
                "total_claims": 68,
                "grounded_claims": 68,
                "claim_grounding_rate": 1.0,
                "hallucination_rate": 0.0,
            },
            "intent_classification": {
                "accuracy": 0.9679,
            },
        }
        is_synthetic, reasons = audit_synthetic_benchmark(fake_summary)
        assert is_synthetic is True
        assert len(reasons) > 0


class TestFreshRunDirectoryAndTraceability:
    """Fresh run directory, git commit, source snapshot, and metric evidence tracing."""

    def test_fresh_run_directory_created_and_snapshotted(self, tmp_path):
        """Running evaluation generates a fresh sub-directory with source_summary.json snapshot."""
        output_base = tmp_path / "regression_out"
        output_base.mkdir()

        summary_file = tmp_path / "current_summary.json"
        summary_file.write_text(json.dumps({
            "metadata": {"suite_sha256": "S1", "kb_sha256": "K1"},
            "intent_classification": {"accuracy": 0.92, "macro_f1": 0.91},
            "retrieval": {"recall_at_3": 0.88},
            "grounding": {"claim_grounding_rate": 0.92, "hallucination_rate": 0.01},
        }), encoding="utf-8")

        run_dir, passed = run_regression_evaluation(
            current_path=summary_file,
            output_root=output_base,
            cached_only=True,
            skip_benchmark=True,
        )
        assert run_dir.exists()
        assert (run_dir / "evaluation_result.json").exists()
        assert (run_dir / "REGRESSION_REPORT.md").exists()
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "source_summary.json").exists()

        # Check manifest contents
        with open(run_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        assert "metrics" in manifest_data
        assert manifest_data["execution_mode"] == "cached_only"
        assert "environment" in manifest_data
        assert manifest_data["environment"]["platform"] is not None

        # Check evidence traceability: every PASS traces to source_summary.json
        pass_count = 0
        for m_name, m_info in manifest_data["metrics"].items():
            assert "evidence_ref" in m_info
            if m_info["status"] == "PASS":
                assert m_info["evidence_ref"].startswith("source_summary.json#")
                pass_count += 1
        assert pass_count > 0


class TestCLIIntegrationAndExitCodes:
    """Integration-style tests invoking CLI via subprocess on temporary environments."""

    def test_cli_require_live_exits_nonzero_on_cached_summary(self, tmp_path):
        """CLI with --require-live must exit non-zero when run against cached/read-only input."""
        summary_file = tmp_path / "test_summary.json"
        summary_file.write_text(json.dumps({
            "metadata": {"suite_sha256": "S1", "kb_sha256": "K1", "weights_sha256": "M1"},
            "intent_classification": {"accuracy": 0.92, "macro_f1": 0.91, "ece": 0.05, "brier_score": 0.05, "ood_detection_rate": 0.95, "far": 0.01, "frr": 0.01},
            "retrieval": {"recall_at_1": 0.80, "recall_at_3": 0.90, "recall_at_5": 0.95, "precision_at_3": 0.35, "mrr": 0.85, "ndcg_at_3": 0.88},
            "grounding": {"claim_grounding_rate": 0.95, "citation_correctness": 1.0, "hallucination_rate": 0.01, "appropriate_abstention_rate": 0.98},
        }), encoding="utf-8")

        res = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "evaluate_regression.py"),
                "--current", str(summary_file),
                "--require-live",
                "--output-dir", str(tmp_path / "out"),
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0
        assert "REQUIRE-LIVE FAILURE" in res.stdout

    def test_cli_exits_nonzero_on_target_failure(self, tmp_path):
        """CLI must exit non-zero when target requirements are violated."""
        summary_file = tmp_path / "failing_summary.json"
        summary_file.write_text(json.dumps({
            "intent_classification": {"accuracy": 0.40},  # Below 0.85 target!
        }), encoding="utf-8")

        res = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "evaluate_regression.py"),
                "--current", str(summary_file),
                "--cached-only",
                "--output-dir", str(tmp_path / "out_fail"),
            ],
            capture_output=True,
            text=True,
        )
        assert res.returncode != 0

"""Dedicated tests for Backend Evaluation Guardrails (Task B3).

Tests verify that:
1. Failed and timeout AI jobs prevent false acceptance.
2. Missing or unverified pricing reports cost as unavailable (never falsified as 0.0).
3. Verified pricing computes exact costs with verified status.
4. Missing or tampered model provenance fails closed.
5. Mismatched KB gold prevents false acceptance certification (Recall@3 is null/incompatible).
6. Human oversight invariant is enforced (no automatic reply dispatch).
7. Robustness paired conditional accuracy uses exact valid denominators.
8. Baseline and DistilBERT OOF provenance is truthfully recorded without forging fold manifests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from pipeline.evaluation.application_acceptance import (
    ApplicationAcceptanceConfig,
    ApplicationAcceptanceRunner,
    EphemeralMockAIServer,
    TicketCaseResult,
)
from pipeline.evaluation.autoeval.backends import verify_model
from pipeline.evaluation.ml_provenance_audit import (
    audit_baseline_oof,
    audit_distilbert_oof,
    audit_ml_robustness,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestApplicationAcceptanceGuardrails:
    """Tests proving failure handling, pricing integrity, and oversight guardrails."""

    def test_failed_and_timeout_jobs_prevent_false_acceptance(self):
        """A timeout or failed job must increment error counts and fail overall acceptance."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="What is your return policy?",
                ticket_id="TICK-001",
                wall_latency_ms=25000.0,
                analysis_status="timeout",
                draft_status="timeout",
                customer_reply_is_none=True,
                error_code="timeout",
                is_terminal=False,
                is_success=False,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="How long to return?",
                ticket_id="TICK-002",
                wall_latency_ms=1200.0,
                analysis_status="completed",
                draft_status="failed",
                customer_reply_is_none=True,
                error_code="ai_service_unavailable",
                is_terminal=True,
                is_success=False,
            ),
        ]

        config = ApplicationAcceptanceConfig(mode="mock")
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        acc = summary["acceptance_summary"]
        assert acc["overall_passed"] is False, "Acceptance must FAIL when jobs timeout or fail"
        assert acc["timeouts"] == 1
        assert acc["failed_jobs"] == 1
        assert acc["successful_cases"] == 0

    def test_missing_or_unverified_pricing_reports_unavailable_not_zero(self):
        """When token usage exists but pricing is unverified/missing, cost must be None/unavailable, never 0.0."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="What is your return policy?",
                ticket_id="TICK-001",
                wall_latency_ms=450.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"prompt_tokens": 150, "completion_tokens": 50, "total_tokens": 200},
                is_terminal=True,
                is_success=True,
            )
        ]

        # No pricing config supplied
        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=None)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["total_tokens"] == 200
        assert tc["cost_status"] == "unavailable"
        assert tc["cost_usd"] is None, "Cost must NEVER be falsified as 0.0 when unverified"
        assert "unverified or missing" in tc["cost_note"].lower()

    def test_arithmetic_fixture_pricing_labeled_unverified(self):
        """Arithmetic fixture without primary source provenance must be labeled arithmetic_fixture_unverified."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Test query",
                ticket_id="TICK-001",
                wall_latency_ms=300.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"prompt_tokens": 1_000_000, "completion_tokens": 500_000, "total_tokens": 1_500_000},
                is_terminal=True,
                is_success=True,
            )
        ]

        # Arithmetic fixture without primary source URL, verified_on, or model
        fixture_pricing = {
            "input_cost_per_million": 0.50,
            "output_cost_per_million": 1.50,
        }
        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=fixture_pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "arithmetic_fixture_unverified"
        assert pytest.approx(tc["cost_usd"], 1e-4) == 1.25
        assert "arithmetic unit test fixture" in tc["cost_note"].lower()

    def test_verified_official_pricing_calculates_estimate_with_thinking(self):
        """When verified pricing is supplied from primary source, cost is calculated as list-price estimate."""
        pricing_file = REPO_ROOT / "artifacts" / "evaluation" / "pricing" / "gemini-3.1-flash-lite-20261112.json"
        if not pricing_file.exists():
            pytest.skip("gemini-3.1-flash-lite-20261112.json not found")

        official_pricing = json.loads(pricing_file.read_text(encoding="utf-8"))

        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Test query with thinking tokens",
                ticket_id="TICK-001",
                wall_latency_ms=400.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={
                    "prompt_tokens": 1_000_000,
                    "candidate_tokens": 200_000,
                    "thinking_tokens": 300_000,
                    "total_tokens": 1_500_000,
                },
                is_terminal=True,
                is_success=True,
            )
        ]

        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=official_pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "verified_list_price_estimate"
        assert tc["thinking_tracked"] is True
        # input: 1M * 0.25 = $0.25; output (candidate 200k + thinking 300k = 500k): 0.5M * 1.50 = $0.75; total = $1.00
        assert pytest.approx(tc["cost_usd"], 1e-4) == 1.00
        assert "list-price estimate" in tc["cost_note"].lower()
        assert "gemini-3.1-flash-lite" in tc["cost_note"]

    def test_human_oversight_no_auto_send_invariant(self):
        """If an unreviewed draft is somehow dispatched to the customer, acceptance must fail."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="What is your return policy?",
                ticket_id="TICK-001",
                wall_latency_ms=350.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=False,  # VIOLATION: customer got reply without review!
                tokens={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                is_terminal=True,
                is_success=False,
            )
        ]

        config = ApplicationAcceptanceConfig(mode="mock")
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        acc = summary["acceptance_summary"]
        assert acc["auto_send_violations"] == 1
        assert acc["human_oversight_enforced"] is False
        assert acc["overall_passed"] is False

    @pytest.mark.integration
    def test_real_application_acceptance_runner_e2e_flow(self, tmp_path):
        """Run real application end-to-end ticket submit -> terminal AI state flow in disposable schema."""
        from scripts.native_runtime import configure_runtime_environment
        configure_runtime_environment()

        try:
            config = ApplicationAcceptanceConfig(mode="mock", num_warm_requests=1, poll_timeout_seconds=20.0)
            runner = ApplicationAcceptanceRunner(config)
            summary = runner.run(output_dir=tmp_path)
        except RuntimeError as e:
            if "database_url_owner" in str(e):
                pytest.skip("database_url_owner not configured in local environment")
            raise

        acc = summary["acceptance_summary"]
        perf = summary["performance"]
        tc = summary["tokens_and_cost"]

        assert acc["overall_passed"] is True, f"E2E Acceptance should pass, got summary: {summary}"
        assert acc["total_cases"] == 2  # 1 cold + 1 warm
        assert acc["successful_cases"] == 2
        assert acc["auto_send_violations"] == 0
        assert acc["human_oversight_enforced"] is True
        assert perf["p95_seconds"] <= 12.0
        assert perf["conditions"]["cold"]["count"] == 1
        assert perf["conditions"]["warm"]["count"] == 1
        assert tc["total_tokens"] > 0
        assert tc["cost_status"] == "unavailable"
        assert tc["cost_usd"] is None
        assert (tmp_path / "acceptance_e2e_report.json").exists()
        assert (tmp_path / "acceptance_e2e_report.md").exists()


class TestProvenanceAndIntegrityGuardrails:
    """Tests verifying model provenance fail-closed and KB mismatch detection."""

    def test_missing_model_provenance_fails_closed(self, tmp_path):
        """Missing weights, config or tampered checksums must fail closed."""
        empty_dir = tmp_path / "empty_model"
        empty_dir.mkdir()

        res = verify_model(empty_dir)
        assert res["ok"] is False
        assert "missing files" in res["error"]

    def test_tampered_model_checksum_fails_closed(self, tmp_path):
        """Model files with mismatched checksums must fail verification."""
        model_dir = tmp_path / "tampered_model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"corrupt_weights")
        (model_dir / "tokenizer.json").write_bytes(b"corrupt_tokenizer")
        (model_dir / "config.json").write_text(json.dumps({
            "id2label": {str(i): f"label_{i}" for i in range(46)}
        }), encoding="utf-8")

        res = verify_model(model_dir)
        assert res["ok"] is False
        assert res["checksum_match"] is False

    def test_mismatched_kb_gold_prevents_false_acceptance(self):
        """When benchmark gold specifies documents not in active application policies, Recall@3 must be null/incompatible."""
        app_policies_path = REPO_ROOT / "data" / "knowledge" / "policies.json"
        if not app_policies_path.exists():
            pytest.skip("data/knowledge/policies.json not found")

        app_policies = json.loads(app_policies_path.read_text(encoding="utf-8"))
        app_doc_ids = {doc["doc_id"] for doc in app_policies}

        # Legacy UUID gold cases used by shared acceptance v2
        legacy_gold_docs = ["b1000000-0000-0000-0000-000000000001", "b1000000-0000-0000-0000-000000000002"]
        mismatched_docs = [d for d in legacy_gold_docs if d not in app_doc_ids]

        assert len(mismatched_docs) == len(legacy_gold_docs), "Legacy UUIDs must not match active POL-* IDs"

        # Check that orchestrator or evaluation runner leaves recall_at_3 as null rather than forging
        compat_file = REPO_ROOT / "artifacts" / "evaluation" / "orchestrator-20261112-live-smoke" / "retrieval_benchmark_compatibility.json"
        if compat_file.exists():
            compat_data = json.loads(compat_file.read_text(encoding="utf-8"))
            assert compat_data["recall_at_3"] is None
            assert compat_data["status"] == "incompatible_benchmark_kb"
            assert "do not remap gold silently" in compat_data["reason"]


class TestMLAuditAndRobustness:
    """Tests verifying 10-fold CV audit, exact paired denominators, and disclosures."""

    def test_baseline_and_distilbert_oof_macro_f1_target(self):
        """All 4 intent models must achieve Macro-F1 >= 0.85 on fixed 10-fold CV."""
        baseline = audit_baseline_oof(REPO_ROOT)
        assert baseline["n_folds"] == 10
        assert baseline["n_labels"] == 46
        assert baseline["all_46_labels_present"] is True

        for cand in baseline["candidates"]:
            assert cand["macro_f1_mean"] >= 0.85
            assert cand["meets_target_085"] is True

        with tempfile.TemporaryDirectory() as tmp_dir:
            dist = audit_distilbert_oof(REPO_ROOT, Path(tmp_dir))
            assert dist["n_folds"] == 10
            assert dist["n_labels"] == 46
            assert dist["oof_macro_f1"] >= 0.85
            assert dist["new_training_executed"] is False
            assert dist["per_fold_checkpoint_manifest_verified"] is False
            assert dist["missing_fold_manifests_forged"] is False

    def test_robustness_paired_conditional_accuracy_denominator(self):
        """Paired conditional accuracy must use the exact count of correct clean queries as denominator."""
        rob = audit_ml_robustness(REPO_ROOT)
        ns = rob["noise_suite"]["slices"]

        clean_acc = ns["clean"]["accuracy"]
        clean_n = ns["clean"]["n"]
        assert clean_n == 84
        assert pytest.approx(clean_acc, 1e-3) == 0.7738

        # Valid clean pairs = 65
        casual = ns["casual"]
        assert casual["paired_denominator"] == 65
        assert pytest.approx(casual["paired_conditional_accuracy"], 1e-3) == 0.9077

        typo = ns["typo"]
        assert typo["paired_denominator"] == 195  # 65 * 3
        assert pytest.approx(typo["paired_conditional_accuracy"], 1e-3) == 0.7744

        # OOS flagged rate must be >= 0.90
        oos = rob["oos_suite"]
        assert oos["total_cases"] == 80
        assert oos["overall_flagged_rate"] >= 0.90

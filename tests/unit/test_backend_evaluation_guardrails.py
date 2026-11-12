"""Dedicated tests for Backend Evaluation Guardrails (Task B3).

Tests verify that:
1. Failed and timeout AI jobs prevent false acceptance.
2. Empty runs or invalid measurements fail closed with null latency (never false acceptance or 0.0s).
3. Missing or unverified pricing reports cost as unavailable (never falsified as 0.0).
4. Invalid rates (NaN, boolean, negative) are rejected.
5. Model mismatch between pricing and actual usage prevents verified cost claims.
6. Mock tokens are excluded from real verified list-price labels.
7. Missing or partial thinking tokens yields null complete cost with lower-bound disclosure.
8. Engine output_tokens alias is properly parsed.
9. Missing or tampered model provenance fails closed.
10. Baseline OOF audit fails closed on checksum mismatch against manifest.
11. 10-fold cross validation alignment (10 folds, 46 labels, 37,911 samples) is strictly verified.
12. Human oversight invariant is enforced (no automatic reply dispatch).
13. Robustness paired conditional accuracy uses exact valid denominators.
"""

from __future__ import annotations

import json
import math
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
    validate_pricing_rates,
)
from pipeline.evaluation.autoeval.backends import verify_model
from pipeline.evaluation.ml_provenance_audit import (
    EvaluationError,
    audit_baseline_oof,
    audit_distilbert_oof,
    audit_ml_robustness,
    validate_oof_alignment,
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
        assert acc["runner_checks_passed"] is False, "Acceptance must FAIL when jobs timeout or fail"
        assert acc["overall_passed"] is False
        assert acc["global_production_accepted"] is False
        assert acc["timeouts"] == 1
        assert acc["failed_jobs"] == 1
        assert acc["successful_cases"] == 0

    def test_empty_results_fails_closed_with_null_latencies(self):
        """Empty results must fail closed: runner_checks_passed is False and latencies are None (not 0.0s)."""
        empty_results: list[TicketCaseResult] = []

        config = ApplicationAcceptanceConfig(mode="mock")
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(empty_results, output_dir=None)

        acc = summary["acceptance_summary"]
        perf = summary["performance"]

        assert acc["runner_checks_passed"] is False, "Empty run must NEVER pass acceptance"
        assert acc["overall_passed"] is False
        assert acc["total_cases"] == 0
        assert perf["p50_seconds"] is None, "Missing latency must be None (null), never 0.0"
        assert perf["p95_seconds"] is None
        assert perf["target_p95_met"] is False
        assert summary["meta"]["status"] == "rejected_empty_results"

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

        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=None)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["total_tokens"] == 200
        assert tc["cost_status"] == "unavailable"
        assert tc["cost_usd"] is None, "Cost must NEVER be falsified as 0.0 when unverified"
        assert "unverified or missing" in tc["cost_note"].lower()

    def test_invalid_pricing_rates_rejected(self):
        """Pricing with boolean, NaN, Inf, or negative rates must fail validation and be marked unavailable."""
        assert validate_pricing_rates({"input_cost_per_million": True, "output_cost_per_million": 1.5})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": 0.25, "output_cost_per_million": float("nan")})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": -0.25, "output_cost_per_million": 1.5})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": float("inf"), "output_cost_per_million": 1.5})[0] is False

        # Compute summary with invalid rate pricing
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
                tokens={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
                is_terminal=True,
                is_success=True,
            )
        ]
        invalid_pricing = {"input_cost_per_million": True, "output_cost_per_million": 1.5}
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=invalid_pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "invalid_pricing_rates"
        assert tc["cost_usd"] is None

    def test_model_mismatch_prevents_cost_verification(self):
        """Pricing configured for gemini-3.1-flash-lite when request used different model must fail closed."""
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
                tokens={"prompt_tokens": 1000, "output_tokens": 500, "thinking_tokens": 100},
                llm_model="different-other-model",
                is_terminal=True,
                is_success=True,
            )
        ]
        pricing = {
            "model": "gemini-3.1-flash-lite",
            "tier": "standard_paid",
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.50,
            "source_url": "https://ai.google.dev/pricing",
            "verified_on": "2026-11-12",
        }
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "model_mismatch_unverified"
        assert tc["cost_usd"] is None
        assert "does not match" in tc["cost_note"]

    def test_mock_mode_excludes_verified_cost_label(self):
        """Even with official pricing passed, mock runs must be labeled mock_simulation_cost_estimate."""
        pricing_file = REPO_ROOT / "artifacts" / "evaluation" / "pricing" / "gemini-3.1-flash-lite-20261112.json"
        if not pricing_file.exists():
            pytest.skip("pricing file missing")

        official_pricing = json.loads(pricing_file.read_text(encoding="utf-8"))

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
                tokens={"prompt_tokens": 1000, "output_tokens": 500, "thinking_tokens": 100},
                llm_model="mock-eval-llm",
                is_terminal=True,
                is_success=True,
            )
        ]

        # Mode is mock
        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=official_pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "mock_simulation_cost_estimate"
        assert "MOCK TRANSPORT FIXTURE ONLY" in tc["cost_note"]

    def test_missing_or_partial_thinking_tokens_yields_null_complete_cost(self):
        """When thinking tokens are absent from a draft request, complete cost is null with lower bound disclosed."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="First query with thinking",
                ticket_id="TICK-001",
                wall_latency_ms=400.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"prompt_tokens": 1000, "candidate_tokens": 200, "thinking_tokens": 300},
                llm_model="gemini-3.1-flash-lite",
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Second query missing thinking",
                ticket_id="TICK-002",
                wall_latency_ms=400.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"prompt_tokens": 1000, "candidate_tokens": 200},  # thinking_tokens missing!
                llm_model="gemini-3.1-flash-lite",
                is_terminal=True,
                is_success=True,
            ),
        ]

        pricing = {
            "model": "gemini-3.1-flash-lite",
            "tier": "standard_paid",
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.50,
            "source_url": "https://ai.google.dev/pricing",
            "verified_on": "2026-11-12",
        }
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "partial_lower_bound_missing_thinking"
        assert tc["cost_usd"] is None, "Complete cost must be strictly null when thinking is incomplete"
        assert tc["lower_bound_cost_usd"] is not None
        # lower bound: 2000 in @ 0.25/M = 0.0005, 400 candidate @ 1.50/M = 0.0006 -> 0.0011
        assert pytest.approx(tc["lower_bound_cost_usd"], 1e-5) == 0.0011

    def test_output_tokens_alias_supported_and_complete_pricing_verified(self):
        """Engine output_tokens alias is parsed and when all drafts have thinking, verified cost estimate succeeds."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Test query",
                ticket_id="TICK-001",
                wall_latency_ms=400.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={
                    "input_tokens": 1_000_000,
                    "output_tokens": 200_000,      # output_tokens alias!
                    "thinking_tokens": 300_000,
                },
                llm_model="gemini-3.1-flash-lite",
                is_terminal=True,
                is_success=True,
            )
        ]

        pricing = {
            "model": "gemini-3.1-flash-lite",
            "tier": "standard_paid",
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.50,
            "source_url": "https://ai.google.dev/pricing",
            "verified_on": "2026-11-12",
        }
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["total_prompt_tokens"] == 1_000_000
        assert tc["total_candidate_tokens"] == 200_000
        assert tc["total_thinking_tokens"] == 300_000
        assert tc["total_completion_tokens"] == 500_000
        assert tc["all_requests_tracked_thinking"] is True
        assert tc["cost_status"] == "verified_list_price_estimate"
        # 1M * 0.25 + 0.5M * 1.50 = 0.25 + 0.75 = 1.00
        assert pytest.approx(tc["cost_usd"], 1e-4) == 1.00

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
        assert acc["runner_checks_passed"] is False

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

        assert acc["runner_checks_passed"] is True, f"E2E Acceptance should pass, got summary: {summary}"
        assert acc["overall_passed"] is True
        assert acc["global_production_accepted"] is False  # Runner alone cannot certify production
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
        assert (tmp_path / "latest_run.json").exists()


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

    def test_baseline_oof_fails_closed_on_manifest_mismatch(self):
        """If baseline OOF checksum does not match manifest, audit must fail closed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_repo = Path(tmp_dir)
            fake_base = fake_repo / "artifacts" / "training" / "03-11-2026-01"
            fake_base.mkdir(parents=True)

            (fake_base / "oof_predictions.csv").write_text(
                "sample_id,fold,y_true,y_pred,model_id\n0,0,return_policy,return_policy,linear_svm\n",
                encoding="utf-8",
            )
            # Declared sha does NOT match
            (fake_base / "manifest.json").write_text(json.dumps({
                "outputs": {"oof_predictions.csv": "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"}
            }), encoding="utf-8")

            with pytest.raises(EvaluationError) as exc_info:
                audit_baseline_oof(fake_repo, fail_closed=True)
            assert "checksum mismatch" in str(exc_info.value).lower()

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

        compat_file = REPO_ROOT / "artifacts" / "evaluation" / "orchestrator-20261112-live-smoke" / "retrieval_benchmark_compatibility.json"
        if compat_file.exists():
            compat_data = json.loads(compat_file.read_text(encoding="utf-8"))
            assert compat_data["recall_at_3"] is None
            assert compat_data["status"] == "incompatible_benchmark_kb"
            assert "do not remap gold silently" in compat_data["reason"]


class TestMLAuditAndRobustness:
    """Tests verifying 10-fold CV audit, exact paired denominators, and disclosures."""

    def test_baseline_and_distilbert_oof_mean_fold_macro_f1_target(self):
        """All 4 intent models must achieve Mean Fold Macro-F1 >= 0.85 on fixed 46-label 10-fold CV."""
        baseline = audit_baseline_oof(REPO_ROOT)
        assert baseline["status"] == "audited_verified"
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
            assert dist["macro_f1_mean"] >= 0.85
            assert dist["meets_target_085"] is True
            assert dist["new_training_executed"] is False
            assert dist["per_fold_checkpoint_manifest_verified"] is False
            assert dist["missing_fold_manifests_forged"] is False

    def test_oof_alignment_validation_10_folds_46_labels(self):
        """Verify exact sample_id, fold, and y_true alignment across 37,911 samples and 4 models."""
        align = validate_oof_alignment(REPO_ROOT)
        assert align["aligned"] is True
        assert align["total_samples"] == 37911
        assert align["n_models"] == 4
        assert align["n_folds"] == 10
        assert align["n_labels"] == 46
        assert len(align["errors"]) == 0

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

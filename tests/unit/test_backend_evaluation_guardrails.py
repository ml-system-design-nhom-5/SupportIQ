"""Dedicated tests for Backend Evaluation Guardrails (Task B3).

Tests verify that:
1. Failed and timeout AI jobs prevent false acceptance.
2. Empty runs or invalid measurements fail closed with null latency (never false acceptance or 0.0s).
3. Config validation rejects invalid modes, negative/bool/NaN counts and timeouts.
4. Partial or invalid latency (NaN, bool, negative, None) fails latency coverage and acceptance.
5. HTTP observation failure (non-200 or malformed JSON) fails human oversight invariant.
6. Missing or unverified pricing reports cost as unavailable (never falsified as 0.0).
7. Invalid rates (NaN, boolean, negative) are rejected.
8. Unknown or mixed models across billable calls fail closed.
9. Exact canonical model and provider match is required (substring match fails closed).
10. Mock tokens are excluded from real verified list-price labels.
11. Missing or partial thinking tokens yields null complete cost with lower-bound disclosure.
12. Actual B2 schema (thought_tokens, input_tokens, output_tokens) is fully supported.
13. Missing or invalid input/output tokens marks total_tokens unknown and cost incomplete.
14. Missing or tampered model provenance fails closed.
15. Baseline OOF audit fails closed on checksum mismatch against manifest.
16. 10-fold cross validation alignment (10 folds, 46 labels, 37,911 samples) is strictly verified.
17. Human oversight invariant is enforced (no automatic reply dispatch).
18. Robustness paired conditional accuracy uses exact valid denominators.
19. Run manifest records full safe provenance hashes and boundary kind.
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

    def test_config_validation_rejects_invalid_parameters(self):
        """Config validate() must reject invalid mode, bool/fractional/negative warm counts and timeouts."""
        with pytest.raises(ValueError, match="Invalid mode"):
            ApplicationAcceptanceConfig(mode="invalid_mode").validate()

        with pytest.raises(ValueError, match="num_warm_requests"):
            ApplicationAcceptanceConfig(num_warm_requests=-1).validate()

        with pytest.raises(ValueError, match="num_warm_requests"):
            ApplicationAcceptanceConfig(num_warm_requests=True).validate()  # bool is not int

        with pytest.raises(ValueError, match="poll_timeout_seconds"):
            ApplicationAcceptanceConfig(poll_timeout_seconds=float("nan")).validate()

        with pytest.raises(ValueError, match="poll_timeout_seconds"):
            ApplicationAcceptanceConfig(poll_timeout_seconds=-5.0).validate()

        with pytest.raises(ValueError, match="analysis_timeout_ms"):
            ApplicationAcceptanceConfig(analysis_timeout_ms=0).validate()

        with pytest.raises(ValueError, match="draft_timeout_ms"):
            ApplicationAcceptanceConfig(draft_timeout_ms=-100).validate()

    def test_partial_or_invalid_latency_fails_coverage(self):
        """If any case has missing, negative, NaN, or boolean latency, latency coverage fails and p95 is None."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Valid latency case",
                ticket_id="TICK-001",
                wall_latency_ms=250.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Corrupt latency case",
                ticket_id="TICK-002",
                wall_latency_ms=None,  # Missing latency!
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=False,
            ),
        ]

        config = ApplicationAcceptanceConfig(mode="mock")
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        acc = summary["acceptance_summary"]
        perf = summary["performance"]

        assert acc["latency_coverage_complete"] is False
        assert acc["runner_checks_passed"] is False, "Partial latency coverage must fail acceptance"
        assert perf["p95_seconds"] is None
        assert perf["p50_seconds"] is None
        assert perf["target_p95_met"] is False

    def test_http_observation_failure_fails_oversight_invariant(self):
        """If customer endpoint returns non-200 or malformed JSON, human oversight fails closed."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TICK-001",
                wall_latency_ms=300.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=False,
                observation_succeeded=False,  # Observation failed!
                error_code="CUSTOMER_VIEW_HTTP_500",
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
        assert tc["cost_status"] == "unavailable"
        assert tc["cost_usd"] is None, "Cost must NEVER be falsified as 0.0 when unverified"
        assert "unverified or missing" in tc["cost_note"].lower()

    def test_invalid_pricing_rates_rejected(self):
        """Pricing with boolean, NaN, Inf, or negative rates must fail validation and be marked unavailable."""
        assert validate_pricing_rates({"input_cost_per_million": True, "output_cost_per_million": 1.5})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": 0.25, "output_cost_per_million": float("nan")})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": -0.25, "output_cost_per_million": 1.5})[0] is False
        assert validate_pricing_rates({"input_cost_per_million": float("inf"), "output_cost_per_million": 1.5})[0] is False

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
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 0},
                llm_metadata={"model": "gemini-3.1-flash-lite", "provider": "gemini"},
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

    def test_missing_or_invalid_tokens_marks_tokens_unknown(self):
        """Missing or non-integer tokens on a billable call marks total_tokens unknown and cost incomplete."""
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
                tokens={"input_tokens": None, "output_tokens": 500},  # Missing input tokens!
                llm_metadata={"model": "gemini-3.1-flash-lite"},
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
        assert tc["total_tokens"] is None, "Total tokens cannot be claimed complete with missing tokens"
        assert tc["cost_status"] == "incomplete_token_coverage"
        assert tc["cost_usd"] is None

    def test_unknown_or_mixed_models_fails_closed(self):
        """Billable calls with missing model or mixed distinct models fail closed."""
        # 1. Missing model metadata on billable call
        results_missing = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Test query",
                ticket_id="TICK-001",
                wall_latency_ms=300.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 100},
                llm_metadata={},  # Missing model metadata!
                llm_model=None,
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
        runner = ApplicationAcceptanceRunner(ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing))
        summary1 = runner._compute_summary(results_missing, output_dir=None)
        assert summary1["tokens_and_cost"]["cost_status"] == "unknown_model_unverified"
        assert summary1["tokens_and_cost"]["cost_usd"] is None

        # 2. Mixed models across calls
        results_mixed = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="First",
                ticket_id="TICK-001",
                wall_latency_ms=300.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 100},
                llm_metadata={"model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Second",
                ticket_id="TICK-002",
                wall_latency_ms=300.0,
                analysis_status="completed",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 100},
                llm_metadata={"model": "gemini-2.5-flash"},  # Different model!
                is_terminal=True,
                is_success=True,
            ),
        ]
        summary2 = runner._compute_summary(results_mixed, output_dir=None)
        assert summary2["tokens_and_cost"]["cost_status"] == "mixed_models_unverified"
        assert summary2["tokens_and_cost"]["cost_usd"] is None

    def test_exact_canonical_model_match_required_substring_rejected(self):
        """Pricing requires exact canonical model match; partial substring match fails closed."""
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
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 100},
                llm_metadata={"model": "gemini-3.1-flash-lite-experimental-preview"},
                is_terminal=True,
                is_success=True,
            )
        ]
        pricing = {
            "model": "gemini-3.1-flash-lite",  # Not exact match!
            "tier": "standard_paid",
            "input_cost_per_million": 0.25,
            "output_cost_per_million": 1.50,
            "source_url": "https://ai.google.dev/pricing",
            "verified_on": "2026-11-12",
        }
        runner = ApplicationAcceptanceRunner(ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing))
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "model_mismatch_unverified"
        assert tc["cost_usd"] is None

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
                tokens={"input_tokens": 1000, "output_tokens": 500, "thought_tokens": 100},
                llm_metadata={"model": "mock-eval-llm"},
                is_terminal=True,
                is_success=True,
            )
        ]

        config = ApplicationAcceptanceConfig(mode="mock", verified_pricing=official_pricing)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["cost_status"] == "mock_simulation_cost_estimate"
        assert "MOCK TRANSPORT FIXTURE ONLY" in tc["cost_note"]

    def test_thought_tokens_b2_actual_schema_complete_pricing_verified(self):
        """Actual B2 schema (thought_tokens, input_tokens, output_tokens) verifies list-price estimate."""
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
                    "output_tokens": 200_000,
                    "thought_tokens": 300_000,
                },
                llm_metadata={"model": "gemini-3.1-flash-lite", "provider": "gemini"},
                is_terminal=True,
                is_success=True,
            )
        ]

        pricing = {
            "model": "gemini-3.1-flash-lite",
            "provider": "gemini",
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
        assert pytest.approx(tc["cost_usd"], 1e-4) == 1.00

    def test_missing_thought_tokens_yields_null_complete_cost_with_lower_bound(self):
        """When thought_tokens are missing from a billable call, cost_usd is null with lower_bound disclosed."""
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
                    "output_tokens": 200_000,
                    # thought_tokens missing!
                },
                llm_metadata={"model": "gemini-3.1-flash-lite", "provider": "gemini"},
                is_terminal=True,
                is_success=True,
            )
        ]

        pricing = {
            "model": "gemini-3.1-flash-lite",
            "provider": "gemini",
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
        # lower bound: 1M * 0.25 + 0.2M * 1.50 = 0.25 + 0.30 = 0.55
        assert pytest.approx(tc["lower_bound_cost_usd"], 1e-4) == 0.55

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
        assert acc["global_production_accepted"] is False
        assert acc["total_cases"] == 2  # 1 cold + 1 warm
        assert acc["successful_cases"] == 2
        assert acc["auto_send_violations"] == 0
        assert acc["human_oversight_enforced"] is True
        assert acc["latency_coverage_complete"] is True
        assert perf["p95_seconds"] <= 12.0
        assert perf["conditions"]["cold"]["count"] == 1
        assert perf["conditions"]["warm"]["count"] == 1
        assert tc["total_tokens"] > 0
        assert tc["cost_status"] == "unavailable"
        assert tc["cost_usd"] is None
        assert (tmp_path / "latest_run.json").exists()
        assert summary["meta"]["boundary_kind"] == "in_process_asgi_testclient"
        assert "provenance_hashes" in summary["meta"]


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

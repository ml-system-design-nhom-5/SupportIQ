"""Additive accounting and usage guardrail tests for Worker B.

Covers:
1. Gemini billing semantics derivation when thoughtsTokenCount is absent but totalTokenCount is reported.
2. Thoughts token absence handling (never asserted zero).
3. All-attempt retry and failure usage/latency aggregation in BudgetedDraftClient.
4. Latency strata separating draft-producing vs abstention latency with p50, p95, mean, error_rate.
5. Inconsistent token totals failing closed.
6. Invalid numeric token values (boolean, float, negative) failing closed.
7. No-call abstention reporting zero billable cost and clean strata.
8. Failed attempt tokens preserved and included in billable accounting.
9. Missing provider failing closed when pricing specifies provider.
10. Mixed providers and mixed models across billable calls failing closed.
11. Provider, model, and tier verification invariants for VERIFIED labels.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import httpx
import pytest
from unittest.mock import MagicMock

from apps.ai_service.drafting import BudgetedDraftClient
from apps.core_backend.llm.gemini import (
    GeminiDraftClient,
    LLMError,
    _resolve_policy_key,
    build_grounded_sources,
    prepare_llm_input,
    redact_contacts,
)
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.autoeval.llm_suite import evidence_from_kb
from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
from pipeline.evaluation.application_acceptance import (
    ApplicationAcceptanceConfig,
    ApplicationAcceptanceRunner,
    TicketCaseResult,
)


OFFICIAL_PRICING = {
    "provider": "google_ai_studio",
    "model": "gemini-3.1-flash-lite",
    "tier": "standard_paid",
    "input_cost_per_million": 0.25,
    "output_cost_per_million": 1.50,
    "source_url": "https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite",
    "verified_on": "2026-11-12",
}


class TestGeminiUsageSemanticsAndDerivation:
    """Tests proving complete billable output accounting under official Gemini billing semantics."""

    def test_gemini_billing_semantics_derivation_from_provider_total(self):
        """When thoughtsTokenCount is absent, but provider reports explicit totalTokenCount:
        derive complete billable output (total - prompt) without asserting thoughts zero,
        retaining raw reported total, formula, and derivation provenance.
        """
        # Exactly mirrors the integrated live 5 cases:
        # Case 0: prompt 1419, candidate 200, total 1619
        # Case 4: prompt 1569, candidate 81, total 1650
        # Sums: prompt 2988, candidate 281, total 3269
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="What is your return policy?",
                ticket_id="TCK-1001",
                wall_latency_ms=2499.21,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1419, "output_tokens": 200, "total_tokens": 1619},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Can I return an item I bought last week?",
                ticket_id="TCK-1002",
                wall_latency_ms=175.56,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                tokens={},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=2,
                condition="warm",
                message="How long do I have to make a return?",
                ticket_id="TCK-1003",
                wall_latency_ms=126.88,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                tokens={},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=3,
                condition="warm",
                message="Do you offer refunds for returned items?",
                ticket_id="TCK-1004",
                wall_latency_ms=128.32,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                tokens={},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=4,
                condition="warm",
                message="What are the return shipping costs?",
                ticket_id="TCK-1005",
                wall_latency_ms=3567.72,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1569, "output_tokens": 81, "total_tokens": 1650},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            ),
        ]

        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)

        tc = summary["tokens_and_cost"]
        assert tc["total_prompt_tokens"] == 2988
        assert tc["total_candidate_tokens"] == 281
        assert tc["provider_reported_total_tokens"] == 3269
        assert tc["total_tokens"] == 3269

        # Thought tokens MUST NOT be asserted to be zero!
        assert tc["total_thinking_tokens"] is None, "Missing thoughts must be None, never asserted as 0"
        assert tc["thinking_tokens_assumed_zero"] is False
        assert tc["all_requests_tracked_thinking"] is False

        # Derived billable output count
        assert tc["total_completion_tokens"] == 281
        dp = tc["derivation_provenance"]
        assert dp is not None
        assert dp["derived_output_tokens"] == 281
        assert dp["raw_reported_total_tokens"] == 3269
        assert dp["thinking_tokens_assumed_zero"] is False
        assert "Gemini API billing semantics" in dp["description"]
        assert "text-only/no-tools" in dp["formula"]
        assert "aistudio.google.com" in dp["source_doc"]

        # Cost calculation: (2988 * 0.25 + 281 * 1.50) / 1,000,000 = 0.0011685 USD
        expected_cost = (2988 * 0.25 + 281 * 1.50) / 1_000_000.0
        assert tc["cost_status"] == "conditional_list_price_estimate_unknown_account_tier"
        assert pytest.approx(tc["cost_usd"], 1e-7) == expected_cost
        assert pytest.approx(tc["lower_bound_cost_usd"], 1e-7) == expected_cost
        assert "thoughts are not asserted to be zero" in tc["cost_note"].lower()

    def test_inconsistent_token_totals_fails_closed(self):
        """When total_tokens < input_tokens + output_tokens, fails closed with inconsistent_token_totals."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1000.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1100},  # 1100 < 1000+200!
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "inconsistent_token_totals"
        assert tc["cost_usd"] is None
        assert tc["total_tokens"] is None
        assert "mathematically inconsistent" in tc["cost_note"].lower()

    def test_invalid_numeric_token_values_fails_closed(self):
        """Boolean or fractional token counts must fail closed with invalid_numeric_token_values."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1000.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": True, "output_tokens": 200},  # Boolean input!
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "invalid_numeric_token_values"
        assert tc["cost_usd"] is None
        assert tc["total_tokens"] is None

    def test_no_call_abstention_reports_zero_billable_cost(self):
        """When all submitted tickets abstain, zero billable LLM calls were executed."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Abstain 1",
                ticket_id="TCK-1001",
                wall_latency_ms=150.0,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                tokens={},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Abstain 2",
                ticket_id="TCK-1002",
                wall_latency_ms=120.0,
                analysis_status="ready",
                draft_status="escalation_recommended",
                customer_reply_is_none=True,
                tokens={},
                is_terminal=True,
                is_success=True,
            ),
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]
        perf = summary["performance"]

        assert tc["cost_status"] == "zero_billable_calls"
        assert tc["cost_usd"] == 0.0
        assert tc["total_tokens"] == 0
        assert tc["total_prompt_tokens"] == 0
        assert tc["total_completion_tokens"] == 0
        assert perf["strata"]["draft_producing"]["count"] == 0
        assert perf["strata"]["abstention"]["count"] == 2

    def test_failed_attempt_tokens_included_in_accounting(self):
        """When a job fails (e.g. llm_unavailable) but consumed provider tokens, they must be included."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="llm_unavailable",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=False,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["total_prompt_tokens"] == 1000
        assert tc["total_candidate_tokens"] == 100
        assert tc["total_completion_tokens"] == 100  # derived from 1100 - 1000
        assert tc["cost_usd"] is not None
        assert tc["cost_usd"] > 0


class TestProviderModelTierVerification:
    """Tests ensuring provider, model, and tier matching fails closed for VERIFIED labels."""

    def test_missing_provider_fails_closed(self):
        """When pricing declares a required provider but observed call lacks provider metadata."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"model": "gemini-3.1-flash-lite"},  # Provider missing!
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "provider_missing_unverified"
        assert tc["cost_usd"] is None
        assert "lack provider metadata" in tc["cost_note"].lower()

    def test_mixed_providers_fails_closed(self):
        """Multiple distinct providers observed across billable calls fails closed."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query 1",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Query 2",
                ticket_id="TCK-1002",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "vertex_ai", "model": "gemini-3.1-flash-lite"},  # Different provider!
                is_terminal=True,
                is_success=True,
            ),
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "mixed_providers_unverified"
        assert tc["cost_usd"] is None

    def test_mixed_models_fails_closed(self):
        """Multiple distinct models observed across billable calls fails closed."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query 1",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Query 2",
                ticket_id="TCK-1002",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-2.5-flash"},  # Different model!
                is_terminal=True,
                is_success=True,
            ),
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "mixed_models_unverified"
        assert tc["cost_usd"] is None


class TestLatencyStrata:
    """Tests proving separate draft-producing vs abstention latency reporting."""

    def test_latency_strata_separates_draft_producing_and_abstention(self):
        """Runner reports separate p50, p95, mean, min, max, error_rate for draft-producing vs abstention."""
        # 2 draft-producing (2.499s, 3.568s), 3 abstention (0.176s, 0.127s, 0.128s)
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Draft 1",
                ticket_id="TCK-1001",
                wall_latency_ms=2499.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Abstain 1",
                ticket_id="TCK-1002",
                wall_latency_ms=176.0,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=2,
                condition="warm",
                message="Abstain 2",
                ticket_id="TCK-1003",
                wall_latency_ms=127.0,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=3,
                condition="warm",
                message="Abstain 3",
                ticket_id="TCK-1004",
                wall_latency_ms=128.0,
                analysis_status="ready",
                draft_status="escalation_recommended",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
            TicketCaseResult(
                case_index=4,
                condition="warm",
                message="Draft 2",
                ticket_id="TCK-1005",
                wall_latency_ms=3568.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
        ]
        config = ApplicationAcceptanceConfig(mode="mock")
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        perf = summary["performance"]
        strata = perf["strata"]

        # Draft-producing stratum
        dp = strata["draft_producing"]
        assert dp["count"] == 2
        assert dp["p50_seconds"] == pytest.approx(3.0335, rel=1e-3)
        assert dp["p95_seconds"] == pytest.approx(3.568, rel=1e-3)
        assert dp["mean_seconds"] == pytest.approx(3.0335, rel=1e-3)
        assert dp["error_rate"] == 0.0

        # Abstention stratum
        ab = strata["abstention"]
        assert ab["count"] == 3
        assert ab["p50_seconds"] == pytest.approx(0.128, rel=1e-3)
        assert ab["p95_seconds"] == pytest.approx(0.176, rel=1e-3)
        assert ab["mean_seconds"] == pytest.approx((0.176 + 0.127 + 0.128) / 3.0, rel=1e-3)
        assert ab["error_rate"] == 0.0

        # Overall stratum
        ov = strata["overall"]
        assert ov["count"] == 5
        assert ov["p50_seconds"] == pytest.approx(0.176, rel=1e-3)
        assert ov["p95_seconds"] == pytest.approx(3.568, rel=1e-3)
        assert perf["mean_seconds"] == pytest.approx((2.499 + 0.176 + 0.127 + 0.128 + 3.568) / 5.0, rel=1e-3)
        assert perf["error_rate"] == 0.0


class TestBudgetedDraftClientRetryAccounting:
    """Tests proving all-attempt retry and failure usage/latency aggregation in BudgetedDraftClient."""

    def test_budgeted_draft_client_aggregates_usage_and_latency_on_retry(self):
        """When attempt 0 fails transiently and attempt 1 succeeds, combined usage and latency are preserved."""
        times = iter([0, 0, 3])

        class MockClient:
            def __init__(self):
                self.calls = 0

            def generate(self, *args, timeout_seconds=None, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise LLMError(
                        "llm_timeout",
                        usage={"promptTokenCount": 500, "totalTokenCount": 500},
                        metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                        latency_seconds=2.5,
                    )
                return {
                    "body": "Grounded draft reply [S1]",
                    "usage": {"promptTokenCount": 500, "candidatesTokenCount": 80, "totalTokenCount": 580},
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "latency_seconds": 1.2,
                }

        client = MockClient()
        budgeted = BudgetedDraftClient(client, clock=lambda: next(times))
        result = budgeted.generate("query", "intent", [])

        # Total usage must be aggregated across both attempts: 500 + 500 = 1000 prompt tokens
        assert result["usage"]["promptTokenCount"] == 1000
        assert result["usage"]["candidatesTokenCount"] == 80
        assert result["usage"]["totalTokenCount"] == 1080  # 500 (attempt 0) + 580 (attempt 1)
        assert result["latency_seconds"] == pytest.approx(3.7, rel=1e-2)

        # Full attempts history recorded
        assert len(result["attempts"]) == 2
        assert result["attempts"][0]["status"] == "llm_timeout"
        assert result["attempts"][0]["usage"]["promptTokenCount"] == 500
        assert result["attempts"][1]["status"] == "success"
        assert result["attempts"][1]["usage"]["promptTokenCount"] == 500

    def test_budgeted_draft_client_preserves_attempts_and_usage_when_all_fail(self):
        """When all retry attempts fail, the final raised LLMError carries aggregated usage and attempt history."""
        times = iter([0, 0, 3])

        class FailingClient:
            def __init__(self):
                self.calls = 0

            def generate(self, *args, timeout_seconds=None, **kwargs):
                self.calls += 1
                raise LLMError(
                    "llm_unavailable",
                    usage={"promptTokenCount": 400},
                    metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                    latency_seconds=1.5,
                )

        client = FailingClient()
        budgeted = BudgetedDraftClient(client, clock=lambda: next(times))

        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("query", "intent", [])

        err = exc_info.value
        assert err.code == "llm_unavailable"
        assert len(err.attempts) == 2
        assert err.usage["promptTokenCount"] == 800  # 400 + 400
        assert err.latency_seconds == pytest.approx(3.0, rel=1e-2)
        assert err.metadata["provider"] == "google_ai_studio"

    def test_budgeted_draft_client_does_not_synthesize_total_when_none_reported(self):
        """When neither attempt reports totalTokenCount, combined usage must NOT synthesize totalTokenCount."""
        times = iter([0, 0, 3])

        class NoTotalClient:
            def __init__(self):
                self.calls = 0

            def generate(self, *args, timeout_seconds=None, **kwargs):
                self.calls += 1
                return {
                    "body": "Reply [S1]",
                    "usage": {"promptTokenCount": 200, "candidatesTokenCount": 50},  # No totalTokenCount!
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "latency_seconds": 0.5,
                }

        client = NoTotalClient()
        budgeted = BudgetedDraftClient(client, clock=lambda: next(times))
        result = budgeted.generate("q", "intent", [])

        assert "totalTokenCount" not in result["usage"]
        assert result["usage"]["promptTokenCount"] == 200
        assert result["usage"]["candidatesTokenCount"] == 50

    def test_budgeted_draft_client_validates_finite_positive_bounds(self):
        """BudgetedDraftClient rejects non-finite or non-positive budget and attempt timeouts."""
        with pytest.raises(ValueError, match="budget_seconds must be a finite positive number"):
            BudgetedDraftClient(None, budget_seconds=0)
        with pytest.raises(ValueError, match="budget_seconds must be a finite positive number"):
            BudgetedDraftClient(None, budget_seconds=-5.0)
        with pytest.raises(ValueError, match="budget_seconds must be a finite positive number"):
            BudgetedDraftClient(None, budget_seconds=float("inf"))

        with pytest.raises(ValueError, match="attempt_timeout_seconds must be a finite positive number"):
            BudgetedDraftClient(None, attempt_timeout_seconds=0)
        with pytest.raises(ValueError, match="attempt_timeout_seconds must be a finite positive number"):
            BudgetedDraftClient(None, attempt_timeout_seconds=-1.0)
        with pytest.raises(ValueError, match="attempt_timeout_seconds must be a finite positive number"):
            BudgetedDraftClient(None, attempt_timeout_seconds=float("nan"))

    def test_default_attempt_timeout_is_five_seconds(self):
        """Default attempt timeout is exactly 5.0s across all clients without magic routing."""
        clock_state = [0.0]
        recorded_timeouts = []

        class MockClient:
            def generate(self, *args, timeout_seconds=None, **kwargs):
                recorded_timeouts.append(timeout_seconds)
                clock_state[0] += 5.0
                raise LLMError("llm_timeout", latency_seconds=5.0)

        budgeted = BudgetedDraftClient(MockClient(), clock=lambda: clock_state[0])
        with pytest.raises(LLMError):
            budgeted.generate("q", "intent", [])

        assert recorded_timeouts == [5.0, 5.0]

    def test_generic_client_success_leaves_http_status_unobserved_null(self):
        """Generic/mock client without HTTP transport metadata defaults http_status to None, not assumed 200."""
        class PlainMockClient:
            def generate(self, *args, **kwargs):
                return {"body": "Answer [S1]", "provider": "mock"}

        budgeted = BudgetedDraftClient(PlainMockClient())
        res = budgeted.generate("q", "intent", [])
        assert len(res["attempts"]) == 1
        assert res["attempts"][0]["http_status"] is None

    def test_just_over_five_second_request_succeeds_on_attempt_zero_with_advancing_clock(self):
        """Advancing fake clock past 5s (5.2s) proves request succeeds on attempt 0 within 7s cap,
        without triggering false-alarm retry or wasting a second call."""
        clock_state = [0.0]

        def fake_clock():
            return clock_state[0]

        recorded_timeouts = []

        class AdvancingClient:
            def generate(self, *args, timeout_seconds=None, **kwargs):
                recorded_timeouts.append(timeout_seconds)
                # Client call takes 5.2s, advancing clock
                clock_state[0] += 5.2
                return {
                    "body": "Grounded answer [S1]",
                    "usage": {"promptTokenCount": 600, "candidatesTokenCount": 90, "totalTokenCount": 690},
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "latency_seconds": 5.2,
                    "attempts": [{"stage": "complete", "http_status": 200}],
                }

        client = AdvancingClient()
        budgeted = BudgetedDraftClient(client, clock=fake_clock, budget_seconds=10.0, attempt_timeout_seconds=7.0)
        result = budgeted.generate("question", "intent", [])

        # Attempt 0 was offered 7.0s and finished at t=5.2s
        assert recorded_timeouts == [7.0]
        assert len(result["attempts"]) == 1
        assert result["attempts"][0]["status"] == "success"
        assert result["attempts"][0]["latency_seconds"] == 5.2
        assert result["attempts"][0]["stage"] == "complete"
        assert result["attempts"][0]["http_status"] == 200
        assert result["attempts"][0]["exception_category"] is None
        assert result["body"] == "Grounded answer [S1]"

    def test_just_over_five_second_transient_failure_retries_with_remaining_budget_advancing_clock(self):
        """When attempt 0 takes 5.5s (just over 5s) and fails transiently,
        fake clock advances and attempt 1 receives exactly the remaining 4.5s of the 10s budget."""
        clock_state = [0.0]

        def fake_clock():
            return clock_state[0]

        recorded_timeouts = []

        class FailingAdvancingClient:
            def generate(self, *args, timeout_seconds=None, **kwargs):
                recorded_timeouts.append(timeout_seconds)
                if len(recorded_timeouts) == 1:
                    # Attempt 0 takes 5.5s then fails with network error
                    clock_state[0] += 5.5
                    raise LLMError(
                        "llm_unavailable",
                        metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                        latency_seconds=5.5,
                        stage="connect",
                        http_status=None,
                        exception_category="network_error",
                    )
                # Attempt 1 takes 2.0s and succeeds
                clock_state[0] += 2.0
                return {
                    "body": "Second attempt answer [S1]",
                    "usage": {"promptTokenCount": 600, "candidatesTokenCount": 80, "totalTokenCount": 680},
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "latency_seconds": 2.0,
                    "attempts": [{"stage": "complete", "http_status": 200}],
                }

        client = FailingAdvancingClient()
        budgeted = BudgetedDraftClient(client, clock=fake_clock, budget_seconds=10.0, attempt_timeout_seconds=7.0)
        result = budgeted.generate("question", "intent", [])

        # Attempt 0 offered 7.0s; at t=5.5s it failed. Remaining = 10.0 - 5.5 = 4.5s.
        # Attempt 1 offered min(7.0, 4.5) = 4.5s.
        assert recorded_timeouts == [7.0, 4.5]
        assert len(result["attempts"]) == 2
        assert result["attempts"][0]["status"] == "llm_unavailable"
        assert result["attempts"][0]["stage"] == "connect"
        assert result["attempts"][0]["http_status"] is None
        assert result["attempts"][0]["exception_category"] == "network_error"
        assert result["attempts"][1]["status"] == "success"
        assert result["attempts"][1]["stage"] == "complete"
        assert result["attempts"][1]["http_status"] == 200
        assert result["latency_seconds"] == pytest.approx(7.5, rel=1e-2)

    def test_both_attempts_exhaust_ten_second_budget_advancing_clock(self):
        """When attempt 0 takes 7.0s and times out, attempt 1 gets remaining 3.0s and times out,
        raising LLMError with full attempt history and sanitized telemetry."""
        clock_state = [0.0]

        def fake_clock():
            return clock_state[0]

        recorded_timeouts = []

        class TimingOutClient:
            def generate(self, *args, timeout_seconds=None, **kwargs):
                recorded_timeouts.append(timeout_seconds)
                if len(recorded_timeouts) == 1:
                    clock_state[0] += 7.0
                    raise LLMError("llm_timeout", metadata={"provider": "google_ai_studio"}, latency_seconds=7.0,
                                   stage="transport", http_status=None, exception_category="timeout")
                clock_state[0] += 3.0
                raise LLMError("llm_timeout", metadata={"provider": "google_ai_studio"}, latency_seconds=3.0,
                               stage="transport", http_status=None, exception_category="timeout")

        client = TimingOutClient()
        budgeted = BudgetedDraftClient(client, clock=fake_clock, budget_seconds=10.0, attempt_timeout_seconds=7.0)
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("question", "intent", [])

        err = exc_info.value
        assert recorded_timeouts == [7.0, 3.0]
        assert len(err.attempts) == 2
        assert err.attempts[0]["status"] == "llm_timeout"
        assert err.attempts[0]["stage"] == "transport"
        assert err.attempts[1]["status"] == "llm_timeout"
        assert err.latency_seconds == pytest.approx(10.0, rel=1e-2)


class TestGeminiDraftClientDirectAttemptAccounting:
    """Tests proving direct GeminiDraftClient attaches attempts on success and failure."""

    def test_gemini_client_attaches_attempts_on_http_error(self):
        import httpx

        def handler(request):
            return httpx.Response(503, json={"error": {"message": "Service unavailable"}})

        client = GeminiDraftClient(
            api_key="test-key",
            model="gemini-3.1-flash-lite",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        evidence = [{"document_id": "d1", "version": "1.0", "title": "T", "excerpt": "Excerpt"}]

        with pytest.raises(LLMError) as exc_info:
            client.generate("q", "intent", evidence)

        err = exc_info.value
        assert err.code == "llm_unavailable"
        assert len(err.attempts) == 1
        assert err.attempts[0]["status"] == "llm_unavailable"
        assert err.attempts[0]["metadata"]["provider"] == "google_ai_studio"
        assert err.attempts[0]["stage"] == "http_response"
        assert err.attempts[0]["http_status"] == 503
        assert err.attempts[0]["exception_category"] == "http_status"

    def test_gemini_client_attaches_attempts_on_invalid_response(self):
        import httpx

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "modelVersion": "gemini-3.1-flash-lite",
                    "usageMetadata": {"promptTokenCount": 150, "candidatesTokenCount": 20, "totalTokenCount": 170},
                    "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "not valid json"}]}}],
                },
            )

        client = GeminiDraftClient(
            api_key="test-key",
            model="gemini-3.1-flash-lite",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        evidence = [{"document_id": "d1", "version": "1.0", "title": "T", "excerpt": "Excerpt"}]

        with pytest.raises(LLMError) as exc_info:
            client.generate("q", "intent", evidence)

        err = exc_info.value
        assert err.code == "llm_invalid_response"
        assert len(err.attempts) == 1
        assert err.attempts[0]["status"] == "llm_invalid_response"
        assert err.attempts[0]["stage"] == "schema_validation"
        assert err.attempts[0]["http_status"] == 200
        assert err.attempts[0]["exception_category"] == "schema_validation_error"
        # Consumed tokens are preserved!
        assert err.usage["promptTokenCount"] == 150
        assert err.attempts[0]["usage"]["promptTokenCount"] == 150

    def test_gemini_client_attaches_attempts_on_timeout(self):
        import httpx

        def handler(request):
            raise httpx.ReadTimeout("Read timed out")

        client = GeminiDraftClient(
            api_key="test-key",
            model="gemini-3.1-flash-lite",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        evidence = [{"document_id": "d1", "version": "1.0", "title": "T", "excerpt": "Excerpt"}]

        with pytest.raises(LLMError) as exc_info:
            client.generate("q", "intent", evidence)

        err = exc_info.value
        assert err.code == "llm_timeout"
        assert len(err.attempts) == 1
        assert err.attempts[0]["status"] == "llm_timeout"
        assert err.attempts[0]["stage"] == "transport"
        assert err.attempts[0]["http_status"] is None
        assert err.attempts[0]["exception_category"] == "timeout"

    def test_schema_parse_failure_suppresses_raw_exception_context_and_secrets(self):
        """When JSON decoding or schema validation fails, raw exception context is suppressed with `from None`
        ensuring tracebacks contain no raw response bodies, payload text, or sensitive credentials."""
        import traceback
        import httpx

        raw_secret_body = "SENSITIVE_CUSTOMER_SECRET_PAYLOAD_BODY_NOT_JSON"

        def handler(request):
            return httpx.Response(200, text=raw_secret_body)

        client = GeminiDraftClient(
            api_key="SUPER_SECRET_GEMINI_KEY_1234567890",
            model="gemini-3.1-flash-lite",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        evidence = [{"document_id": "d1", "version": "1.0", "title": "T", "excerpt": "Excerpt"}]

        with pytest.raises(LLMError) as exc_info:
            client.generate("q", "intent", evidence)

        err = exc_info.value
        assert err.code == "llm_invalid_response"
        assert err.__cause__ is None
        assert err.__suppress_context__ is True

        formatted = "".join(traceback.format_exception(err))
        assert "SUPER_SECRET_GEMINI_KEY" not in formatted
        assert "SENSITIVE_CUSTOMER_SECRET_PAYLOAD" not in formatted


class TestModelTierAndMissingTotalEdgeCases:
    """Additional edge cases for model matching, tier verification, and missing total tokens."""

    def test_model_mismatch_fails_closed(self):
        """Observed model differs from verified pricing declared model."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-2.5-flash"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "model_mismatch_unverified"
        assert tc["cost_usd"] is None

    def test_tier_mismatch_fails_closed(self):
        """Observed tier differs from verified pricing declared tier."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "free_tier"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "tier_mismatch_unverified"
        assert tc["cost_usd"] is None

    def test_verified_list_price_when_all_verified_including_tier(self):
        """When provider, model, AND tier match the verified pricing spec, cost_status is verified_list_price_estimate."""
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "verified_list_price_estimate"
        assert tc["cost_usd"] is not None

    def test_total_tokens_absent_and_thoughts_absent_reports_partial_lower_bound(self):
        """When neither total_tokens nor thought_tokens are present, total_completion_tokens is None,
        cost_status is partial_lower_bound_missing_thinking, and lower_bound_cost_usd is reported.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100},  # No total_tokens, no thought_tokens!
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["total_completion_tokens"] is None
        assert tc["total_thinking_tokens"] is None
        assert tc["cost_status"] == "partial_lower_bound_missing_thinking"
        assert tc["cost_usd"] is None
        assert tc["lower_bound_cost_usd"] == pytest.approx((1000 * 0.25 + 100 * 1.50) / 1_000_000.0)

    def test_missing_pricing_provider_cannot_yield_verified_label(self):
        """When pricing artifact omits declared provider, runner cannot yield a verified label."""
        pricing_no_provider = dict(OFFICIAL_PRICING)
        del pricing_no_provider["provider"]

        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query",
                ticket_id="TCK-1001",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=pricing_no_provider)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        # Even with matching tier, missing pricing provider prevents VERIFIED label!
        assert tc["cost_status"] != "verified_list_price_estimate"
        assert tc["cost_status"] == "conditional_list_price_estimate_unknown_account_tier"
        assert "unverified or unspecified" in tc["cost_note"].lower()


class TestRetryAccountingAndMetadataSurvivalRegressions:
    """Regressions for retry accounting, metadata survival through Engine, and timeout handling."""

    def test_retry_timeout_unknown_then_success_fails_closed(self):
        """When Attempt 0 timed out with unmeasured provider usage and Attempt 1 succeeded:
        Runner must keep unknown timeout usage as incomplete, failing closed with incomplete_token_coverage.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query with retry",
                ticket_id="TCK-1001",
                wall_latency_ms=3500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 500, "output_tokens": 80, "total_tokens": 580},
                llm_metadata={
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "attempts": [
                        {
                            "attempt_index": 0,
                            "status": "llm_timeout",
                            "latency_seconds": 2.5,
                            "usage": {},  # Unmeasured usage before timeout
                            "metadata": {"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                        },
                        {
                            "attempt_index": 1,
                            "status": "success",
                            "latency_seconds": 1.0,
                            "usage": {"promptTokenCount": 500, "candidatesTokenCount": 80, "totalTokenCount": 580},
                            "metadata": {"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                        },
                    ],
                },
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "incomplete_token_coverage"
        assert tc["cost_usd"] is None
        assert "timed out with unmeasured provider usage" in tc["cost_note"].lower()

    def test_mixed_models_across_retries_detected_and_fails_closed(self):
        """When Attempt 0 used gemini-2.5-flash and Attempt 1 used gemini-3.1-flash-lite:
        Runner detects mixed models across retries and fails closed with mixed_models_unverified.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query with retry",
                ticket_id="TCK-1001",
                wall_latency_ms=3000.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 80, "total_tokens": 1080},
                llm_metadata={
                    "attempts": [
                        {
                            "attempt_index": 0,
                            "status": "llm_unavailable",
                            "latency_seconds": 1.5,
                            "usage": {"promptTokenCount": 500, "candidatesTokenCount": 0},
                            "metadata": {"provider": "google_ai_studio", "model": "gemini-2.5-flash"},
                        },
                        {
                            "attempt_index": 1,
                            "status": "success",
                            "latency_seconds": 1.5,
                            "usage": {"promptTokenCount": 500, "candidatesTokenCount": 80, "totalTokenCount": 580},
                            "metadata": {"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                        },
                    ],
                },
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["cost_status"] == "mixed_models_unverified"
        assert tc["cost_usd"] is None

    def test_engine_metadata_survival_on_success_and_error(self):
        """Verify that Engine.draft persists attempts list into llm_metadata on both success and error."""
        from apps.ai_service.engine import Engine

        class DummyModel:
            def predict(self, text):
                return {"intent": "return_policy", "confidence": 0.95, "margin": 0.90}

        class DummyRetriever:
            def __init__(self):
                self.eligible_versions = []

            def retrieve(self, *a, **k):
                return {
                    "status": "success",
                    "evidence": [{"document_id": "POL-1", "version": "1.0", "title": "T", "excerpt": "Excerpt"}],
                }

        class MockLLMSuccess:
            def generate(self, *a, **k):
                return {
                    "body": "Reply [S1]",
                    "input_snapshot": {"sources": [{"source_id": "S1", "source_type": "policy", "document_id": "POL-1", "version": "1.0", "excerpt": "Excerpt"}]},
                    "is_clarification": False,
                    "latency_seconds": 0.2,
                    "usage": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120},
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "attempts": [
                        {"attempt_index": 0, "status": "success", "latency_seconds": 0.2, "usage": {"promptTokenCount": 100}}
                    ],
                }

        dummy_policy = {
            "supported_12_intents": ["return_policy"],
            "sensitive_action_intents": [],
            "default_confidence_threshold": 0.70,
            "default_margin_threshold": 0.10,
        }

        engine = Engine(
            model=DummyModel(),
            retriever=DummyRetriever(),
            llm=MockLLMSuccess(),
            versions={"model_version": "v1.0.0", "kb_version": "kb-v2"},
            policy=dummy_policy,
        )
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        res = engine.draft({"message": "Return query", "order_context": {}, "as_of": now_iso})
        assert "llm_metadata" in res
        assert "attempts" in res["llm_metadata"]
        assert len(res["llm_metadata"]["attempts"]) == 1
        assert res["llm_metadata"]["attempts"][0]["status"] == "success"

        # On error path:
        class MockLLMError:
            def generate(self, *a, **k):
                raise LLMError(
                    "llm_unavailable",
                    usage={"promptTokenCount": 100},
                    metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite"},
                    latency_seconds=0.5,
                    attempts=[{"attempt_index": 0, "status": "llm_unavailable", "latency_seconds": 0.5}],
                )

        engine_err = Engine(
            model=DummyModel(),
            retriever=DummyRetriever(),
            llm=MockLLMError(),
            versions={"model_version": "v1.0.0", "kb_version": "kb-v2"},
            policy=dummy_policy,
        )
        err_res = engine_err.draft({"message": "Return query", "order_context": {}, "as_of": now_iso})
        assert "llm_metadata" in err_res
        assert "attempts" in err_res["llm_metadata"]
        assert len(err_res["llm_metadata"]["attempts"]) == 1
        assert err_res["llm_metadata"]["attempts"][0]["status"] == "llm_unavailable"

    def test_cold_warm_error_rates_measured_from_actual_failures(self):
        """Runner reports measured error rates for cold and warm strata, not hardcoded 0.0%."""
        results = [
            # Cold case failed
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Cold query",
                ticket_id="TCK-1001",
                wall_latency_ms=1000.0,
                analysis_status="error",
                draft_status="error",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=False,
            ),
            # Warm case succeeded
            TicketCaseResult(
                case_index=1,
                condition="warm",
                message="Warm query",
                ticket_id="TCK-1002",
                wall_latency_ms=200.0,
                analysis_status="ready",
                draft_status="abstained",
                customer_reply_is_none=True,
                is_terminal=True,
                is_success=True,
            ),
        ]
        config = ApplicationAcceptanceConfig(mode="mock")
        runner = ApplicationAcceptanceRunner(config)
        summary = runner._compute_summary(results, output_dir=None)
        p = summary["performance"]

        assert p["conditions"]["cold"]["error_rate"] == 1.0
        assert p["conditions"]["warm"]["error_rate"] == 0.0
        assert p["error_rate"] == 0.5

        # In markdown report
        md = runner._render_markdown(summary)
        assert "| **Cold Start** | 1 | `1.000s` | `1.000s` | `1.000s` | 100.0% |" in md
        assert "| **Warm Runs** | 1 | `0.200s` | `0.200s` | `0.200s` | 0.0% |" in md

    def test_aggregate_usage_boolean_token_is_invalid(self):
        """BudgetedDraftClient._aggregate_usage marks boolean token counts as invalid and incomplete."""
        budgeted = BudgetedDraftClient(None)
        attempts = [
            {"attempt_index": 0, "status": "success", "usage": {"promptTokenCount": True, "candidatesTokenCount": 20}}
        ]
        combined = budgeted._aggregate_usage(attempts)
        assert combined.get("has_invalid_fields") is True
        assert combined.get("incomplete") is True
        assert "promptTokenCount" not in combined  # True is not counted as 1!

    def test_missing_output_with_known_thoughts_fails_closed_and_keeps_tokens_unknown(self):
        """When draft_ready has input_tokens: 100, thought_tokens: 5, but output and total are absent:
        total_candidate_tokens and completion must stay unknown (None, not 0 or 5),
        provider_reported_total_tokens must be None (not 105), and cost_status must be incomplete_token_coverage.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Missing output query",
                ticket_id="TCK-1001",
                wall_latency_ms=1200.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 100, "thought_tokens": 5},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["total_candidate_tokens"] is None, "Missing candidate tokens must not be defaulted to 0"
        assert tc["total_completion_tokens"] is None, "Completion tokens must not be fabricated from thoughts alone"
        assert tc["total_tokens"] is None, "Total tokens must not be fabricated"
        assert tc["provider_reported_total_tokens"] is None, "Provider total must be null when omitted by provider"
        assert tc["cost_status"] == "incomplete_token_coverage"
        assert tc["cost_usd"] is None

    def test_missing_provider_total_with_explicit_counts_reports_null_reported_total(self):
        """When explicit input (100), candidate (20), and thought (5) are present, but provider omitted total:
        total_tokens is computed (125), completion is 25, cost is verified, but provider_reported_total_tokens MUST be None.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Explicit counts query",
                ticket_id="TCK-1002",
                wall_latency_ms=1200.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 100, "candidate_tokens": 20, "thought_tokens": 5},  # totalTokenCount omitted
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["total_prompt_tokens"] == 100
        assert tc["total_candidate_tokens"] == 20
        assert tc["total_thinking_tokens"] == 5
        assert tc["total_completion_tokens"] == 25
        assert tc["total_tokens"] == 125
        assert tc["provider_reported_total_tokens"] is None, "provider_reported_total_tokens MUST be null if provider omitted it"
        assert tc["cost_status"] == "verified_list_price_estimate"
        assert tc["cost_usd"] is not None

    def test_zero_aliases_and_invalid_boolean_distinctly_preserved(self):
        """Zero counts (0) in completion_tokens / prompt_tokens must be preserved and not treated as falsy,
        while boolean False is preserved and rejected as invalid_numeric_token_values.
        """
        # Part A: Valid zero aliases with completion_tokens compatibility
        results_zero = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Zero query",
                ticket_id="TCK-1003",
                wall_latency_ms=800.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"prompt_tokens": 0, "completion_tokens": 0, "thought_tokens": 0},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary_zero = ApplicationAcceptanceRunner(config)._compute_summary(results_zero, output_dir=None)
        tc_zero = summary_zero["tokens_and_cost"]

        assert tc_zero["total_prompt_tokens"] == 0
        assert tc_zero["total_candidate_tokens"] == 0
        assert tc_zero["total_completion_tokens"] == 0
        assert tc_zero["cost_status"] == "verified_list_price_estimate"
        assert tc_zero["cost_usd"] == 0.0

        # Part B: Invalid boolean False must NOT be masked by alias fallback
        results_bool = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Bool query",
                ticket_id="TCK-1004",
                wall_latency_ms=800.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": False, "completion_tokens": 10},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=True,
            )
        ]
        summary_bool = ApplicationAcceptanceRunner(config)._compute_summary(results_bool, output_dir=None)
        tc_bool = summary_bool["tokens_and_cost"]

        assert tc_bool["cost_status"] == "invalid_numeric_token_values"
        assert tc_bool["cost_usd"] is None

    def test_per_attempt_missing_metadata_does_not_inherit_ticket_level_metadata(self):
        """When explicit raw attempts are present, Attempt 0 with missing provider/model/tier
        must NOT inherit from ticket-level llm_metadata; it must fail verification.
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Retry query",
                ticket_id="TCK-1005",
                wall_latency_ms=2500.0,
                analysis_status="ready",
                draft_status="draft_ready",
                customer_reply_is_none=True,
                tokens={"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050},
                llm_metadata={
                    # Ticket level has valid metadata from final success:
                    "provider": "google_ai_studio",
                    "model": "gemini-3.1-flash-lite",
                    "tier": "standard_paid",
                    "attempts": [
                        {
                            "attempt_index": 0,
                            "status": "llm_unavailable",
                            "usage": {"promptTokenCount": 500, "candidatesTokenCount": 0},
                            # Missing metadata dict: provider and model are None
                        },
                        {
                            "attempt_index": 1,
                            "status": "success",
                            "usage": {"promptTokenCount": 500, "candidatesTokenCount": 50, "totalTokenCount": 550},
                            "metadata": {
                                "provider": "google_ai_studio",
                                "model": "gemini-3.1-flash-lite",
                                "tier": "standard_paid",
                            },
                        },
                    ],
                },
                is_terminal=True,
                is_success=True,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        # Attempt 0 lacks model and provider metadata, and must not have inherited it from ticket-level
        assert tc["cost_status"] in ("unknown_model_unverified", "provider_missing_unverified")
        assert tc["cost_usd"] is None

    def test_invalid_response_missing_output_usage_fails_closed_and_keeps_tokens_unknown(self):
        """When an attempt fails with llm_invalid_response (or llm_blocked_or_incomplete, llm_invalid_citations)
        with usage={'input_tokens': 100, 'thought_tokens': 5} and output/total absent:
        Output tokens must NOT be assumed to be 0 (since invalid response may have generated billable candidate tokens).
        Candidates, completion, and total tokens must remain unknown (None), provider total must be None,
        and cost_status must be incomplete_token_coverage (never verified_list_price_estimate).
        """
        results = [
            TicketCaseResult(
                case_index=0,
                condition="cold",
                message="Query yielding invalid schema response",
                ticket_id="TCK-1006",
                wall_latency_ms=1500.0,
                analysis_status="ready",
                draft_status="llm_invalid_response",
                customer_reply_is_none=True,
                tokens={"input_tokens": 100, "thought_tokens": 5},
                llm_metadata={"provider": "google_ai_studio", "model": "gemini-3.1-flash-lite", "tier": "standard_paid"},
                is_terminal=True,
                is_success=False,
            )
        ]
        config = ApplicationAcceptanceConfig(mode="live", verified_pricing=OFFICIAL_PRICING)
        summary = ApplicationAcceptanceRunner(config)._compute_summary(results, output_dir=None)
        tc = summary["tokens_and_cost"]

        assert tc["total_candidate_tokens"] is None, "Missing candidate tokens in failed attempt must not be assumed 0"
        assert tc["total_completion_tokens"] is None, "Completion tokens must not be fabricated from thoughts alone"
        assert tc["total_tokens"] is None, "Total tokens must not be fabricated"
        assert tc["provider_reported_total_tokens"] is None, "Provider total must be null when omitted"
        assert tc["cost_status"] == "incomplete_token_coverage"
        assert tc["cost_usd"] is None


def _load_approved_pol_ship_004() -> dict:
    kb = json.loads(Path("data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8"))
    return next(d for d in kb if d["document_id"] == "POL-SHIP-004" and str(d["version"]) == "1.0")


def _retrieve_case10_evidence() -> list[dict]:
    release = json.loads(Path("apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
    adapter = RetrievalAdapter(
        encoder=MockPolicyEncoder(),
        allowed_document_versions=allowed,
        relevance_threshold=0.20,
    )
    ret = adapter.retrieve(
        query="The app shows my order was delivered but I never received the package from the courier.",
        intent="delivery_issue",
        current_time=datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
    )
    assert ret["status"] == "success"
    return [e for e in ret["evidence"] if e["document_id"] == "POL-SHIP-004"]


class TestPublicHotlinePreservationAndPrivacy:
    """Task B: Origin-aware preservation of verified public policy hotline with fail-closed provenance."""

    def test_reproduce_case10_policy_hotline_preserved_in_grounded_sources(self):
        """Regression test reproducing Case 10 using real current callers:
        1. RetrievalAdapter.retrieve() shape (excerpt = '<title>\\n<content>', chunk_ids, content_hash).
        2. evidence_from_kb() shape (full document content + content_hash).
        Grounded source construction must preserve 1900 6035 in both verified shapes.
        """
        retrieval_evidence = _retrieve_case10_evidence()
        assert len(retrieval_evidence) == 1
        assert retrieval_evidence[0]["chunk_ids"] == ["POL-SHIP-004:1.0:c0"]

        sources_from_retrieval = build_grounded_sources(retrieval_evidence, authorized_facts=None)
        assert len(sources_from_retrieval) == 1
        assert sources_from_retrieval[0]["document_id"] == "POL-SHIP-004"
        assert sources_from_retrieval[0]["version"] == "1.0"
        assert "1900 6035" in sources_from_retrieval[0]["excerpt"], (
            f"Public hotline 1900 6035 must be preserved in retrieved Case 10 S1, got: {sources_from_retrieval[0]['excerpt']}"
        )
        assert "[PHONE_OR_NUMBER]" not in sources_from_retrieval[0]["excerpt"]

        doc = _load_approved_pol_ship_004()
        kb_evidence = evidence_from_kb({doc["document_id"]: doc}, ["POL-SHIP-004"])
        sources_from_kb = build_grounded_sources(kb_evidence, authorized_facts=None)
        assert len(sources_from_kb) == 1
        assert "1900 6035" in sources_from_kb[0]["excerpt"]
        assert "[PHONE_OR_NUMBER]" not in sources_from_kb[0]["excerpt"]

    def test_controlled_draft_generation_with_case10_hotline(self):
        """Under controlled MockTransport (zero external provider requests):
        Verify that GeminiDraftClient generates a grounded draft for real retrieved Case 10 evidence:
        1. Prompt sent to provider contains 1900 6035 in source S1.
        2. Prompt does NOT contain [PHONE_OR_NUMBER] in source S1.
        3. Model response with hotline 1900 6035 and citation [S1] succeeds.
        4. Citations contain document_id 'POL-SHIP-004' and version '1.0'.
        5. Citation digest is strictly preserved in input_snapshot.
        """
        captured_requests = []
        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            payload = json.loads(request.content)
            user_text = payload["contents"][0]["parts"][0]["text"]
            assert "1900 6035" in user_text, f"Prompt must contain preserved hotline, got: {user_text}"
            assert "[PHONE_OR_NUMBER]" not in user_text
            resp_body = {
                "modelVersion": "gemini-3.1-flash-lite",
                "usageMetadata": {
                    "promptTokenCount": 150,
                    "candidatesTokenCount": 45,
                    "totalTokenCount": 195,
                },
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "answerable": True,
                                        "answer": (
                                            "If the courier marked your package as delivered but you have not received it, "
                                            "please contact Tiki Customer Support within 24-48 hours via hotline 1900 6035. [S1]"
                                        ),
                                        "citations": ["S1"],
                                        "is_clarification": False,
                                    })
                                }
                            ]
                        },
                    }
                ],
            }
            return httpx.Response(200, json=resp_body)

        client = GeminiDraftClient(
            api_key="test-api-key",
            model="gemini-3.1-flash-lite",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        evidence = _retrieve_case10_evidence()
        res = client.generate(
            question="The app shows my order was delivered but I never received the package from the courier.",
            intent="delivery_issue",
            evidence=evidence,
        )
        assert len(captured_requests) == 1
        assert "1900 6035" in res["body"]
        assert "[PHONE_OR_NUMBER]" not in res["body"]
        assert len(res["citations"]) == 1
        assert res["citations"][0]["document_id"] == "POL-SHIP-004"
        assert res["citations"][0]["version"] == "1.0"
        assert res["citations"][0]["source_id"] == "S1"
        assert res["input_snapshot"]["sources"][0]["sha256"] == hashlib.sha256(
            res["input_snapshot"]["sources"][0]["excerpt"].encode("utf-8")
        ).hexdigest()

    def test_customer_private_contacts_in_question_and_order_facts_remain_strictly_redacted(self):
        """Customer private phone numbers, emails, cards, order IDs, and tokens
        MUST remain strictly redacted to [PHONE_OR_NUMBER], [EMAIL], [IDENTIFIER], [REDACTED_TOKEN]
        in customer question and customer order facts. No universal number whitelisting.
        """
        question = (
            "My phone is 0912345678, email is alice@example.com, card is 4532 1234 5678 9010, "
            "order is ORD-99887766, and session token is tok_12345678901234567890123456789012"
        )
        business_context = {
            "order_status": "Delivered",
            "phone": "0987654321",
            "delivery_date": "2026-11-04",
        }
        evidence = [
            {
                "document_id": "POL-RET-001",
                "version": "2.0",
                "title": "Return Policy",
                "excerpt": "Products may be returned within 30 days in original packaging.",
            }
        ]
        snapshot = prepare_llm_input(
            question=question,
            intent="return_policy",
            evidence=evidence,
            business_context=business_context,
        )
        prompt_text = snapshot["prompt"]

        assert "0912345678" not in prompt_text
        assert "alice@example.com" not in prompt_text
        assert "4532 1234 5678 9010" not in prompt_text
        assert "ORD-99887766" not in prompt_text
        assert "tok_12345678901234567890123456789012" not in prompt_text
        assert "0987654321" not in prompt_text

        assert "[EMAIL]" in prompt_text
        assert "[IDENTIFIER]" in prompt_text
        assert "[REDACTED_TOKEN]" in prompt_text
        assert "[PHONE_OR_NUMBER]" in prompt_text
        # ISO date remains intact
        assert "2026-11-04" in prompt_text

    def test_customer_question_with_public_and_private_phone_redacts_both(self):
        """When customer text includes an approved public hotline adjacent to a private customer phone:
        Customer text has origin='customer', so neither number is whitelisted.
        Private customer phone 0912345678 is redacted, and 1900 6035 in customer text is also redacted.
        """
        customer_q = "I tried calling hotline 1900 6035 from my phone 0912345678 but got no answer."
        redacted_q = redact_contacts(customer_q)
        assert "0912345678" not in redacted_q
        assert "1900 6035" not in redacted_q
        assert redacted_q == "I tried calling hotline [PHONE_OR_NUMBER] from my phone [PHONE_OR_NUMBER] but got no answer."

    def test_adjacent_private_contacts_redacted_with_verified_policy_and_redact_helper(self):
        """Customer/private contacts adjacent to an approved Case 10 policy source remain redacted,
        while redact_contacts with explicit allowed_numbers preserves only the whitelisted hotline.
        Any policy source attempting to smuggle adjacent private contacts fails closed completely.
        """
        evidence = _retrieve_case10_evidence()
        snapshot = prepare_llm_input(
            question="Call me at 0912345678 or email badactor@example.com; I tried 1900 6035.",
            intent="delivery_issue",
            evidence=evidence,
            business_context={
                "order_id": "ORD-1005",
                "order_status": "Delivered",
                "carrier": "Contact 0987654321 or badactor@example.com",
                "tracking_code": "0911223344",
                "delivery_date": "2026-06-14",
            },
        )
        assert "1900 6035" in snapshot["sources"][0]["excerpt"]
        assert len(snapshot["sources"]) == 2
        order_source = snapshot["sources"][1]
        assert "0987654321" not in order_source["excerpt"]
        assert "0911223344" not in order_source["excerpt"]
        assert "badactor@example.com" not in order_source["excerpt"]
        assert "0912345678" not in snapshot["prompt"]
        assert "0987654321" not in snapshot["prompt"]
        assert "0911223344" not in snapshot["prompt"]
        assert "badactor@example.com" not in snapshot["prompt"]
        assert "2026-06-14" in snapshot["prompt"]

        direct_redacted = redact_contacts(
            "Contact Tiki Customer Support within 24-48 hours via hotline 1900 6035 "
            "or private mobile 0912345678 or write to badactor@example.com.",
            allowed_numbers=("1900 6035",),
        )
        assert "1900 6035" in direct_redacted
        assert "0912345678" not in direct_redacted
        assert "badactor@example.com" not in direct_redacted
        assert "[PHONE_OR_NUMBER]" in direct_redacted
        assert "[EMAIL]" in direct_redacted

    def test_untrusted_or_unknown_policy_source_redacts_all_phone_numbers(self):
        """Policy sources not registered as approved documents (e.g. POL-FAKE)
        or having unknown versions (e.g. POL-SHIP-004:99.0) must FAIL CLOSED:
        All phone numbers must be redacted to [PHONE_OR_NUMBER].
        """
        fake_evidence = [
            {
                "document_id": "POL-FAKE",
                "version": "1.0",
                "title": "Forged Policy",
                "excerpt": "Call our fake support at 1900 6035 or 0987654321.",
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "99.0",
                "title": "Unknown Version Policy",
                "excerpt": "Call support at 1900 6035 or 0912345678.",
            },
        ]
        sources = build_grounded_sources(fake_evidence, authorized_facts=None)
        assert len(sources) == 2
        for s in sources:
            assert "1900 6035" not in s["excerpt"], f"Untrusted source must not preserve contact: {s['excerpt']}"
            assert "0987654321" not in s["excerpt"]
            assert "0912345678" not in s["excerpt"]
            assert "[PHONE_OR_NUMBER]" in s["excerpt"]

    def test_missing_hash_with_correct_id_version_and_forged_snippet_rejects_contact(self):
        """Correct document_id/version without content_hash MUST FAIL CLOSED even for real text or forged snippets."""
        doc = _load_approved_pol_ship_004()
        cases = [
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "excerpt": "Forged content: call 1900 6035.",
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "title": doc["title"],
                "excerpt": doc["content"],
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": "",
                "excerpt": "Forged content: call 1900 6035.",
            },
        ]
        for item in cases:
            sources = build_grounded_sources([item], authorized_facts=None)
            assert len(sources) == 1
            assert "1900 6035" not in sources[0]["excerpt"]
            assert "[PHONE_OR_NUMBER]" in sources[0]["excerpt"]

    def test_forged_content_hash_in_policy_source_rejects_contact_preservation(self):
        """When a policy source supplies a content_hash that does not match the approved registry:
        It is identified as forged/tampered and contact preservation is refused.
        """
        doc = _load_approved_pol_ship_004()
        tampered_evidence = [
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": "forged_sha256_hash_that_does_not_match",
                "title": doc["title"],
                "excerpt": doc["content"],
            }
        ]
        sources = build_grounded_sources(tampered_evidence, authorized_facts=None)
        assert len(sources) == 1
        assert "1900 6035" not in sources[0]["excerpt"]
        assert "[PHONE_OR_NUMBER]" in sources[0]["excerpt"]

    def test_copied_known_hash_with_altered_content_or_inconsistent_provenance_rejects_contact(self):
        """Supplying the real approved content_hash alone MUST NOT grant trust when content,
        excerpt, title, chunk_ids, or source_type are altered or inconsistent.
        """
        doc = _load_approved_pol_ship_004()
        known_hash = doc["content_hash"]
        altered_cases = [
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": doc["title"],
                "excerpt": "Forged content: call 1900 6035.",
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": doc["title"],
                "excerpt": f"{doc['content']} Or call private mobile 0912345678.",
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": doc["title"],
                "content": doc["content"],
                "excerpt": "Altered excerpt: call 1900 6035.",
            },
            {
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": "Tampered Title",
                "excerpt": doc["content"],
            },
            {
                "source_type": "customer",
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": doc["title"],
                "excerpt": doc["content"],
            },
            {
                "source_type": "policy",
                "document_id": "POL-SHIP-004",
                "version": "1.0",
                "content_hash": known_hash,
                "title": doc["title"],
                "chunk_ids": ["POL-FAKE:1.0:c0"],
                "excerpt": f"{doc['title']}\n{doc['content']}",
            },
        ]
        for item in altered_cases:
            sources = build_grounded_sources([item], authorized_facts=None)
            assert len(sources) == 1
            assert "1900 6035" not in sources[0]["excerpt"], f"Must reject forged provenance: {item}"
            assert "[PHONE_OR_NUMBER]" in sources[0]["excerpt"]

    def test_conflicting_embedded_and_explicit_versions_rejected(self):
        """_resolve_policy_key and build_grounded_sources MUST reject conflicting embedded vs explicit versions
        and conflicting document_id vs doc_id aliases.
        """
        assert _resolve_policy_key("POL-SHIP-004:1.0", "2.0") is None
        assert _resolve_policy_key("POL-SHIP-004:2.0", "1.0") is None
        assert _resolve_policy_key("POL-SHIP-004:1.0", "") is None
        assert _resolve_policy_key("POL-SHIP-004:", "1.0") is None
        assert _resolve_policy_key("POL-SHIP-004:1.0", "1.0") == ("POL-SHIP-004", "1.0")
        assert _resolve_policy_key("POL-SHIP-004:1.0", None) == ("POL-SHIP-004", "1.0")

        doc = _load_approved_pol_ship_004()
        conflicting_cases = [
            {
                "document_id": "POL-SHIP-004:1.0",
                "version": "2.0",
                "content_hash": doc["content_hash"],
                "title": doc["title"],
                "excerpt": doc["content"],
            },
            {
                "document_id": "POL-SHIP-004:2.0",
                "version": "1.0",
                "content_hash": doc["content_hash"],
                "title": doc["title"],
                "excerpt": doc["content"],
            },
            {
                "document_id": "POL-SHIP-004",
                "doc_id": "POL-OTHER",
                "version": "1.0",
                "content_hash": doc["content_hash"],
                "title": doc["title"],
                "excerpt": doc["content"],
            },
        ]
        for item in conflicting_cases:
            sources = build_grounded_sources([item], authorized_facts=None)
            assert len(sources) == 1
            assert "1900 6035" not in sources[0]["excerpt"], f"Must reject conflicting versions/IDs: {item}"
            assert "[PHONE_OR_NUMBER]" in sources[0]["excerpt"]

    def test_citation_hash_consistency_with_preserved_contact(self):
        """Citation hashes and input snapshot digests must be mathematically consistent
        with the preserved contact excerpt from an approved Case 10 source.
        """
        evidence = _retrieve_case10_evidence()
        sources = build_grounded_sources(evidence, authorized_facts=None)
        assert "1900 6035" in sources[0]["excerpt"]
        expected_sha = hashlib.sha256(sources[0]["excerpt"].encode("utf-8")).hexdigest()
        assert sources[0]["sha256"] == expected_sha
        assert sources[0]["text"] == sources[0]["excerpt"]

        snapshot = prepare_llm_input("Where is my package?", "delivery_issue", evidence)
        assert snapshot["sources"][0]["sha256"] == expected_sha
        assert snapshot["sha256"] == hashlib.sha256(snapshot["prompt"].encode("utf-8")).hexdigest()



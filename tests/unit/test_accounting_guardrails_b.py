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

import json
import pytest
from unittest.mock import MagicMock

from apps.ai_service.drafting import BudgetedDraftClient
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
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
        # Consumed tokens are preserved!
        assert err.usage["promptTokenCount"] == 150
        assert err.attempts[0]["usage"]["promptTokenCount"] == 150


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
                            "usage": {"promptTokenCount": 500},
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
                            "usage": {"promptTokenCount": 500},
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

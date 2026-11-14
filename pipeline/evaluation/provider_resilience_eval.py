"""Controlled before/after provider resilience evaluation harness (Task C).

Exercises real `GeminiDraftClient`, `BudgetedDraftClient`, and `Engine.draft`
against deterministic `httpx.MockTransport` fault schedules and a simulated
monotonic/perf_counter clock (zero live external provider calls).

Persists per-attempt telemetry, unknown/incomplete usage status, total latency,
deadline budget compliance, fallback outcomes, and no-auto-send verification.
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
import os
import subprocess
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from apps.ai_service.drafting import BudgetedDraftClient
from apps.ai_service.engine import Engine
from apps.core_backend.intent.routing import load_policy_v2
from apps.core_backend.llm.gemini import GeminiDraftClient


KB_POLICY_CONTENT = (
    "Customers may request an exchange or return within 30 days (for products directly "
    "distributed by Tiki Trading) or within 7 days (for products from marketplace partner "
    "sellers on Tiki) from the date of successful delivery."
)


class _DeterministicEvalModel:
    model_version = "eval-fixture-v1"
    verified_model_version = "eval-fixture-v1"
    model_mode = "controlled_fixture"
    verified = True

    def predict(self, message: str) -> dict[str, Any]:
        return {
            "intent": "return_policy",
            "confidence": 0.94,
            "margin": 0.86,
            "score_kind": "controlled_fixture",
            "model_mode": "controlled_fixture",
            "verified": True,
            "top_k": [
                {"intent": "return_policy", "probability": 0.94},
                {"intent": "return_product", "probability": 0.08},
            ],
        }


class _ControlledDocMeta:
    valid_from = "2026-01-01T00:00:00Z"
    valid_to = "2026-12-31T23:59:59Z"


class _ControlledDoc:
    doc_id = "POL-RET-001"
    version = "2.0"
    metadata = _ControlledDocMeta()


class _DeterministicEvalRetriever:
    relevance_threshold = 0.55
    eligible_versions = [_ControlledDoc()]

    def retrieve(self, message: str, intent: str, role: str = "agent", current_time: Any = None) -> dict[str, Any]:
        return {
            "has_conflict": False,
            "reason_codes": [],
            "evidence": [
                {
                    "document_id": "POL-RET-001",
                    "version": "2.0",
                    "title": "Tiki Standard Product Return and Exchange Policy and Conditions",
                    "excerpt": KB_POLICY_CONTENT,
                    "score": 0.91,
                }
            ],
        }


@dataclass(frozen=True)
class ScheduleStep:
    outcome: str  # "success" | "http_error" | "timeout" | "connect_error" | "network_error"
    duration_seconds: float
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    usage_metadata: dict[str, Any] | None = None
    error_body: dict[str, Any] | None = None
    timeout_kind: str = "read"  # "read" | "connect"
    answer_text: str = (
        "Products directly distributed by Tiki Trading have a 30-day return window from delivery [S1]."
    )


@dataclass(frozen=True)
class ResilienceSchedule:
    schedule_id: str
    description: str
    category: str
    steps: list[ScheduleStep]
    expected_if_recovered: str  # "draft_ready" | "fallback"


DEFAULT_SCHEDULES: list[ResilienceSchedule] = [
    ResilienceSchedule(
        schedule_id="S01_clean_success",
        description="Clean first-attempt 200 OK response within budget.",
        category="control_success",
        steps=[
            ScheduleStep(
                outcome="success",
                duration_seconds=0.75,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 68, "totalTokenCount": 1488},
            )
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S02_single_503_then_success",
        description="Transient HTTP 503 (no usage) followed by 200 OK on retry.",
        category="transient_503",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=0.40, status_code=503, usage_metadata=None),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.90,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 70, "totalTokenCount": 1490},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S03_double_503_then_success",
        description="Two consecutive transient 503 responses followed by 200 OK well inside 10s budget.",
        category="transient_503_multi",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=0.35, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="http_error", duration_seconds=0.35, status_code=503, usage_metadata=None),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.85,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 72, "totalTokenCount": 1492},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S04_503_short_retry_after_then_success",
        description="HTTP 503 with Retry-After: 1 header followed by 200 OK.",
        category="retry_after_bounded",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=503,
                headers={"Retry-After": "1"},
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.80,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S05_503_retry_after_beyond_budget",
        description="HTTP 503 with Retry-After: 15 exceeding remaining 10s budget; must fail closed without sleeping past budget.",
        category="retry_after_excessive",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.50,
                status_code=503,
                headers={"Retry-After": "15"},
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.50,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S06_429_short_retry_after_then_success",
        description="HTTP 429 rate limit with Retry-After: 1 followed by 200 OK.",
        category="transient_429",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                headers={"Retry-After": "1"},
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.90,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 66, "totalTokenCount": 1486},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S07_timeout_then_success",
        description="First attempt ReadTimeout (no usage) followed by 200 OK recovery within 10s.",
        category="transient_timeout",
        steps=[
            ScheduleStep(outcome="timeout", duration_seconds=5.0, timeout_kind="read"),
            ScheduleStep(
                outcome="success",
                duration_seconds=1.20,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 69, "totalTokenCount": 1489},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S08_repeated_timeouts_exhaust_budget",
        description="Consecutive ReadTimeouts exhausting the 10s deadline; must fall back cleanly with unknown usage.",
        category="timeout_exhaustion",
        steps=[
            ScheduleStep(outcome="timeout", duration_seconds=5.0, timeout_kind="read"),
            ScheduleStep(outcome="timeout", duration_seconds=5.0, timeout_kind="read"),
            ScheduleStep(outcome="timeout", duration_seconds=5.0, timeout_kind="read"),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S09_slow_503_then_clamped_timeout",
        description="Slow 4.5s HTTP 503 followed by ReadTimeout clamped to remaining budget (~5.0-5.5s); must respect 10s deadline.",
        category="budget_clamping",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=4.50, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="timeout", duration_seconds=6.00, timeout_kind="read"),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.50,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 64, "totalTokenCount": 1484},
            ),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S10_permanent_503_exhaustion",
        description="Permanent HTTP 503 across all retries; must fall back cleanly with every attempt recorded.",
        category="permanent_503",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=0.40, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="http_error", duration_seconds=0.40, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="http_error", duration_seconds=0.40, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="http_error", duration_seconds=0.40, status_code=503, usage_metadata=None),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S11_non_retryable_400_fast_fail",
        description="Non-retryable HTTP 400 request error; must fail fast in 1 attempt and preserve any error usageMetadata.",
        category="non_retryable_400",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.25,
                status_code=400,
                usage_metadata={"promptTokenCount": 310, "totalTokenCount": 310},
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.50,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 64, "totalTokenCount": 1484},
            ),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S12_connect_error_then_success",
        description="Transient ConnectError on first attempt followed by 200 OK.",
        category="transient_connect_error",
        steps=[
            ScheduleStep(outcome="connect_error", duration_seconds=0.35),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.85,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 67, "totalTokenCount": 1487},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S13_remaining_budget_clamped_timeout",
        description="Slow 503 (4.2s) + slow 503 (3.5s) leaving 2.3s; verifies timeout clamping below 5s and budget <= 10s.",
        category="remaining_budget_clamp",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=4.20, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="http_error", duration_seconds=3.50, status_code=503, usage_metadata=None),
            ScheduleStep(outcome="timeout", duration_seconds=5.00, timeout_kind="read"),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S14_503_malformed_retry_after_header",
        description="HTTP 503 with malformed/negative Retry-After values; must never crash or sleep negative, recovering cleanly.",
        category="retry_after_malformed",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=503,
                headers={"Retry-After": "invalid-garbage"},
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=503,
                headers={"Retry-After": "-5"},
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.80,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S15_429_invalid_retry_info_typing",
        description="HTTP 429 carrying malformed Google RPC RetryInfo retryDelay types/values (int, NaNs, negative) before 200 OK.",
        category="retry_info_invalid",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                error_body={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "Rate limit exceeded; retry shortly.",
                        "details": [
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": 123},
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "NaNs"},
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "-2s"},
                        ],
                    }
                },
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.80,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S16_429_valid_retry_info_json",
        description="HTTP 429 carrying valid Google RPC RetryInfo retryDelay '1s' followed by 200 OK.",
        category="retry_info_valid",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                error_body={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "Too many requests per minute.",
                        "details": [
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1s"},
                        ],
                    }
                },
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.80,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="draft_ready",
    ),
    ResilienceSchedule(
        schedule_id="S17_429_daily_quota_exhausted_non_retryable",
        description="HTTP 429 with QuotaFailure / GenerateRequestsPerDay hard quota exhausted; should fail fast without futile retries.",
        category="quota_classification",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                error_body={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "Quota exceeded for quota metric 'Generate Requests' and limit 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'.",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                "violations": [
                                    {
                                        "quotaMetric": "generativelanguage.googleapis.com/generate_requests_per_day",
                                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                                    }
                                ],
                            }
                        ],
                    }
                },
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.80,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 65, "totalTokenCount": 1485},
            ),
        ],
        expected_if_recovered="fallback",
    ),
    ResilienceSchedule(
        schedule_id="S18_fast_503_storm_max_attempts_bound",
        description="Fast 0.05s HTTP 503 storm verifying bounded max attempt count and clean fallback.",
        category="max_attempts_bound",
        steps=[
            ScheduleStep(outcome="http_error", duration_seconds=0.05, status_code=503, usage_metadata=None)
            for _ in range(10)
        ],
        expected_if_recovered="fallback",
    ),
]


class ControlledSimClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = float(start)
        self.sleep_calls: list[float] = []

    def monotonic(self) -> float:
        return self._now

    def perf_counter(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        if seconds > 0:
            self._now += float(seconds)

    def sleep(self, seconds: float) -> None:
        val = float(seconds)
        self.sleep_calls.append(val)
        if val > 0:
            self._now += val


class ScheduledMockTransport(httpx.BaseTransport):
    def __init__(self, schedule: ResilienceSchedule, clock: ControlledSimClock) -> None:
        self.schedule = schedule
        self.clock = clock
        self.call_index = 0
        self.transport_requests: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        idx = self.call_index
        self.call_index += 1
        step = (
            self.schedule.steps[idx]
            if idx < len(self.schedule.steps)
            else self.schedule.steps[-1]
        )

        ext_timeout = request.extensions.get("timeout") or {}
        req_read_timeout = ext_timeout.get("read") if isinstance(ext_timeout, dict) else None
        req_connect_timeout = ext_timeout.get("connect") if isinstance(ext_timeout, dict) else None

        elapsed_step = step.duration_seconds
        if step.outcome == "timeout":
            bound = req_connect_timeout if step.timeout_kind == "connect" else req_read_timeout
            if isinstance(bound, (int, float)) and bound > 0:
                elapsed_step = min(step.duration_seconds, float(bound))

        self.clock.advance(elapsed_step)
        self.transport_requests.append(
            {
                "transport_call_index": idx,
                "url": str(request.url),
                "requested_read_timeout": req_read_timeout,
                "requested_connect_timeout": req_connect_timeout,
                "simulated_step_outcome": step.outcome,
                "simulated_step_duration_seconds": round(elapsed_step, 4),
            }
        )

        if step.outcome == "timeout":
            if step.timeout_kind == "connect":
                raise httpx.ConnectTimeout("Simulated connect timeout", request=request)
            raise httpx.ReadTimeout("Simulated read timeout", request=request)
        if step.outcome == "connect_error":
            raise httpx.ConnectError("Simulated network connect error", request=request)
        if step.outcome == "network_error":
            raise httpx.NetworkError("Simulated network error", request=request)

        if step.outcome == "http_error":
            if step.error_body is not None:
                body = json.loads(json.dumps(step.error_body))
            else:
                body = {"error": {"code": step.status_code, "message": "Simulated provider error"}}
            if step.usage_metadata is not None:
                body["usageMetadata"] = step.usage_metadata
            return httpx.Response(
                status_code=step.status_code,
                headers=step.headers,
                json=body,
                request=request,
            )

        payload_json = json.dumps(
            {
                "answerable": True,
                "answer": step.answer_text,
                "citations": ["S1"],
                "is_clarification": False,
            }
        )
        ok_body: dict[str, Any] = {
            "modelVersion": "gemini-3.1-flash-lite",
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": payload_json}]},
                }
            ],
        }
        if step.usage_metadata is not None:
            ok_body["usageMetadata"] = step.usage_metadata
        return httpx.Response(
            status_code=200,
            headers=step.headers,
            json=ok_body,
            request=request,
        )


def _classify_usage_status(attempts: list[dict[str, Any]], usage_raw: dict[str, Any]) -> str:
    if not attempts:
        return "no_attempts"
    any_without_usage = any(not isinstance(att.get("usage"), dict) or not att.get("usage") for att in attempts)
    any_with_usage = any(isinstance(att.get("usage"), dict) and bool(att.get("usage")) for att in attempts)
    if not any_with_usage:
        return "unknown_no_response"
    if any_without_usage or usage_raw.get("incomplete"):
        return "incomplete_mixed_attempts"
    if "totalTokenCount" in usage_raw or "total_tokens" in usage_raw:
        return "complete"
    return "partial_no_total"


def run_schedule(schedule: ResilienceSchedule, repo_root: Path) -> dict[str, Any]:
    policy_path = repo_root / "apps/core_backend/config/policies/intent_policy.v2.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    load_policy_v2(str(policy_path))  # validate policy schema

    clock = ControlledSimClock(start=1000.0)
    transport = ScheduledMockTransport(schedule, clock)
    http_client = httpx.Client(transport=transport, follow_redirects=False, trust_env=False)

    created_clients: list[int] = [id(http_client)]
    versions = {
        "release_id": "controlled-resilience-eval",
        "model_version": "eval-fixture-v1",
        "model_mode": "controlled_fixture",
        "verified": True,
    }

    t_start = clock.monotonic()
    with ExitStack() as stack:
        stack.enter_context(patch("time.perf_counter", clock.perf_counter))
        stack.enter_context(patch("time.sleep", clock.sleep))
        try:
            gemini = GeminiDraftClient(
                api_key="synthetic-controlled-eval-key",
                model="gemini-3.1-flash-lite",
                http_client=http_client,
            )
            budgeted_kwargs: dict[str, Any] = {
                "clock": clock.monotonic,
                "budget_seconds": 10.0,
                "attempt_timeout_seconds": 5.0,
            }
            sig_params = inspect.signature(BudgetedDraftClient.__init__).parameters
            if "sleep" in sig_params:
                budgeted_kwargs["sleep"] = clock.sleep
            elif "sleep_fn" in sig_params:
                budgeted_kwargs["sleep_fn"] = clock.sleep
            budgeted = BudgetedDraftClient(gemini, **budgeted_kwargs)
            engine = Engine(
                _DeterministicEvalModel(),
                _DeterministicEvalRetriever(),
                budgeted,
                versions,
                policy,
            )
            result = engine.draft(
                {
                    "message": "What is the return window for Tiki Trading products?",
                    "order_context": {"order_status": "delivered"},
                    "as_of": "2026-06-15T10:00:00Z",
                }
            )
        finally:
            http_client.close()

    total_simulated_elapsed = round(clock.monotonic() - t_start, 4)
    attempts = list((result.get("llm_metadata") or {}).get("attempts") or getattr(budgeted, "last_attempts", []) or [])
    llm_usage = dict(result.get("llm_usage") or {})

    reported_llm_latency_seconds = round(((result.get("step_latency_ms") or {}).get("llm", 0) or 0) / 1000.0, 4)
    sum_attempt_latency_seconds = round(sum((att.get("latency_seconds") or 0.0) for att in attempts), 4)
    total_sleep_seconds = round(sum(s for s in clock.sleep_calls if s > 0), 4)
    latency_includes_retry_waits = abs(reported_llm_latency_seconds - total_simulated_elapsed) <= 0.05

    # Reconstruct raw combined usage from budgeted attempt history if present
    raw_usage_combined: dict[str, Any] = {}
    if getattr(budgeted, "_aggregate_usage", None):
        raw_usage_combined = budgeted._aggregate_usage(attempts)

    requested_read_timeouts = [
        tr["requested_read_timeout"]
        for tr in transport.transport_requests
        if tr.get("requested_read_timeout") is not None
    ]
    max_requested_timeout = max(requested_read_timeouts) if requested_read_timeouts else 0.0

    # Strict no-auto-send check: Engine.draft can only prepare draft/fallback metadata, never dispatch customer reply.
    no_auto_send = (
        result.get("status") in {"draft_ready", "llm_unavailable", "escalation_recommended", "abstained"}
        and "sent" not in result
        and "auto_sent" not in result
        and "customer_reply_sent" not in result
    )

    return {
        "schedule_id": schedule.schedule_id,
        "category": schedule.category,
        "description": schedule.description,
        "expected_if_recovered": schedule.expected_if_recovered,
        "terminal_status": result.get("status"),
        "failure_code": result.get("failure_code"),
        "reason_codes": list(result.get("reason_codes") or []),
        "fallback_triggered": result.get("status") != "draft_ready",
        "draft_recovered": result.get("status") == "draft_ready",
        "no_auto_send_verified": no_auto_send,
        "simulated_elapsed_seconds": total_simulated_elapsed,
        "reported_llm_latency_seconds": reported_llm_latency_seconds,
        "sum_attempt_latency_seconds": sum_attempt_latency_seconds,
        "total_sleep_seconds": total_sleep_seconds,
        "latency_includes_retry_waits": latency_includes_retry_waits,
        "budget_respected_10s": total_simulated_elapsed <= 10.0 + 1e-3,
        "max_requested_attempt_timeout_seconds": max_requested_timeout,
        "attempt_cap_respected_5s": max_requested_timeout <= 5.0 + 1e-6,
        "sleep_delays_seconds": [round(s, 4) for s in clock.sleep_calls],
        "attempt_count": len(attempts),
        "transport_call_count": len(transport.transport_requests),
        "attempts": attempts,
        "transport_requests": transport.transport_requests,
        "llm_usage_mapped": llm_usage,
        "raw_usage_combined": raw_usage_combined,
        "usage_status": _classify_usage_status(attempts, raw_usage_combined),
        "total_tokens_fabricated": (
            "totalTokenCount" in raw_usage_combined
            and raw_usage_combined.get("incomplete", False)
        ),
        "http_clients_injected": len(created_clients),
    }


def check_owned_client_trust_env_false() -> dict[str, Any]:
    """Verify whether GeminiDraftClient constructs owned httpx.Client with trust_env=False under proxy env."""
    fake_client = GeminiDraftClient(api_key="synthetic-trust-env-check", model="gemini-3.1-flash-lite", http_client=None)

    def _raise_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Simulated fast failure without network")

    with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:9999", "HTTP_PROXY": "http://127.0.0.1:9999"}):
        with patch.object(httpx.Client, "post", side_effect=_raise_timeout):
            try:
                fake_client.generate(
                    "What is the return policy?",
                    "return_policy",
                    [{"document_id": "POL-RET-001", "version": "2.0", "title": "Return", "excerpt": KB_POLICY_CONTENT}],
                )
            except Exception:
                pass
    created = getattr(fake_client, "_http", None)
    trust_env_val = getattr(created, "trust_env", None) if created is not None else None
    if created is not None:
        created.close()
    return {
        "owned_client_created": created is not None,
        "trust_env": trust_env_val,
        "unconditional_trust_env_false": trust_env_val is False,
    }


def verify_b_candidate_edge_contracts(repo_root: Path, source_commit: str | None = None) -> dict[str, Any]:
    """Verify wait-inclusive fields, typed RetryInfo, hard-quota 429 + valid header, and malformed injected retry_after."""
    if source_commit is None:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()

    from apps.ai_service.drafting import BudgetedDraftClient
    from apps.ai_service.engine import Engine
    from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError

    checks: dict[str, Any] = {}
    policy = json.loads((repo_root / "apps/core_backend/config/policies/intent_policy.v2.json").read_text(encoding="utf-8"))
    kb_release = json.loads((repo_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
    versions = {
        "kb_version": kb_release.get("kb_version", "2.0"),
        "policy_version": policy.get("version", "2.0"),
        "prompt_version": "grounded-v3",
        "model_version": "eval-fixture-v1",
        "model_mode": "controlled_fixture",
        "verified": True,
    }

    # 1. Hard quota 429 QuotaFailure WITH valid Retry-After: 1 header -> fail fast (1 attempt, 0 sleep)
    s_hard_quota_header = ResilienceSchedule(
        schedule_id="E01_hard_quota_429_with_valid_retry_after_header",
        description="429 QuotaFailure with valid Retry-After: 1 must still fail fast without retrying or sleeping.",
        category="hard_quota_with_header",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                headers={"Retry-After": "1"},
                error_body={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "Quota exceeded for quota limit GenerateRequestsPerDayPerProjectPerModel.",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                            }
                        ],
                    }
                },
                usage_metadata=None,
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.50,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 60, "totalTokenCount": 1480},
            ),
        ],
        expected_if_recovered="fallback",
    )
    r_hq = run_schedule(s_hard_quota_header, repo_root)
    checks["hard_quota_429_with_valid_header"] = {
        "passed": (
            r_hq["fallback_triggered"]
            and r_hq["failure_code"] == "llm_rate_limited"
            and r_hq["attempt_count"] == 1
            and r_hq["sleep_delays_seconds"] == []
            and r_hq["no_auto_send_verified"]
            and not r_hq["total_tokens_fabricated"]
        ),
        "result": r_hq,
    }

    # 2. Untyped retryDelay dict vs typed google.rpc.RetryInfo on 429
    s_untyped = ResilienceSchedule(
        schedule_id="E02_429_untyped_retry_delay_dict",
        description="429 carrying retryDelay without google.rpc.RetryInfo @type must not retry.",
        category="retry_info_untyped",
        steps=[
            ScheduleStep(
                outcome="http_error",
                duration_seconds=0.30,
                status_code=429,
                error_body={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "details": [{"@type": "type.googleapis.com/google.rpc.BadRequest", "retryDelay": "1s"}],
                    }
                },
            ),
            ScheduleStep(
                outcome="success",
                duration_seconds=0.50,
                status_code=200,
                usage_metadata={"promptTokenCount": 1420, "candidatesTokenCount": 60, "totalTokenCount": 1480},
            ),
        ],
        expected_if_recovered="fallback",
    )
    r_untyped = run_schedule(s_untyped, repo_root)
    checks["untyped_retry_delay_rejected"] = {
        "passed": (
            r_untyped["fallback_triggered"]
            and r_untyped["attempt_count"] == 1
            and r_untyped["sleep_delays_seconds"] == []
            and r_untyped["no_auto_send_verified"]
        ),
        "result": r_untyped,
    }

    # 3. Direct BudgetedDraftClient output & LLMError wait-inclusive latency fields
    clock_succ = ControlledSimClock()
    sched_succ = DEFAULT_SCHEDULES[3]  # S04_503_short_retry_after_then_success
    transport_succ = ScheduledMockTransport(sched_succ, clock_succ)
    http_succ = httpx.Client(transport=transport_succ, timeout=httpx.Timeout(5.0))
    with ExitStack() as stack:
        stack.enter_context(patch("time.perf_counter", clock_succ.perf_counter))
        stack.enter_context(patch("time.sleep", clock_succ.sleep))
        try:
            g_succ = GeminiDraftClient(api_key="synthetic-key", model="gemini-3.1-flash-lite", http_client=http_succ)
            b_succ = BudgetedDraftClient(g_succ, clock=clock_succ.monotonic, sleep=clock_succ.sleep)
            res_succ = b_succ.generate("Return window?", "return_policy", [{"document_id": "POL-RET-001", "version": "2.0", "title": "R", "excerpt": KB_POLICY_CONTENT}])
        finally:
            http_succ.close()
    checks["success_wait_inclusive_fields"] = {
        "latency_seconds": res_succ.get("latency_seconds"),
        "transport_latency_seconds": res_succ.get("transport_latency_seconds"),
        "retry_wait_seconds": res_succ.get("retry_wait_seconds"),
        "passed": (
            res_succ.get("latency_seconds") == 2.1
            and res_succ.get("transport_latency_seconds") == 1.1
            and res_succ.get("retry_wait_seconds") == 1.0
        ),
    }

    # 4. Direct BudgetedDraftClient LLMError wait-inclusive latency fields on permanent 503 exhaustion
    clock_fail = ControlledSimClock()
    sched_fail = DEFAULT_SCHEDULES[9]  # S10_permanent_503_exhaustion
    transport_fail = ScheduledMockTransport(sched_fail, clock_fail)
    http_fail = httpx.Client(transport=transport_fail, timeout=httpx.Timeout(5.0))
    exc_fields: dict[str, Any] = {}
    with ExitStack() as stack:
        stack.enter_context(patch("time.perf_counter", clock_fail.perf_counter))
        stack.enter_context(patch("time.sleep", clock_fail.sleep))
        try:
            g_fail = GeminiDraftClient(api_key="synthetic-key", model="gemini-3.1-flash-lite", http_client=http_fail)
            b_fail = BudgetedDraftClient(g_fail, clock=clock_fail.monotonic, sleep=clock_fail.sleep)
            try:
                b_fail.generate("Return window?", "return_policy", [{"document_id": "POL-RET-001", "version": "2.0", "title": "R", "excerpt": KB_POLICY_CONTENT}])
            except LLMError as exc:
                exc_fields = {
                    "code": exc.code,
                    "latency_seconds": getattr(exc, "latency_seconds", None),
                    "transport_latency_seconds": getattr(exc, "transport_latency_seconds", None),
                    "retry_wait_seconds": getattr(exc, "retry_wait_seconds", None),
                    "attempt_count": len(exc.attempts),
                }
        finally:
            http_fail.close()
    checks["failure_exception_wait_inclusive_fields"] = {
        **exc_fields,
        "passed": (
            exc_fields.get("latency_seconds") == 1.05
            and exc_fields.get("transport_latency_seconds") == 0.8
            and exc_fields.get("retry_wait_seconds") == 0.25
        ),
    }

    # 5. Malformed injected retry_after values on LLMError fail closed without crashing
    class _MalformedRetryAfterInner:
        def __init__(self, bad_val: Any):
            self.bad_val = bad_val
            self.calls = 0

        def generate(self, *args, **kwargs):
            self.calls += 1
            raise LLMError(
                "llm_unavailable",
                latency_seconds=0.1,
                http_status=503,
                retry_after=self.bad_val,
                attempts=[{"attempt_index": 0, "status": "llm_unavailable", "latency_seconds": 0.1, "stage": "http_response", "http_status": 503, "exception_category": "http_status", "usage": {}, "metadata": {}}],
            )

    malformed_cases = ["not-a-number", True, float("nan"), -3.0, 90000.0]
    malformed_results = []
    for bad_val in malformed_cases:
        clk = ControlledSimClock()
        inner = _MalformedRetryAfterInner(bad_val)
        b_bad = BudgetedDraftClient(inner, clock=clk.monotonic, sleep=clk.sleep)
        raised_code = None
        wait_reported = None
        try:
            b_bad.generate("msg", "return_policy", [])
        except LLMError as exc:
            raised_code = exc.code
            wait_reported = getattr(exc, "retry_wait_seconds", None)
        malformed_results.append(
            {
                "injected": repr(bad_val),
                "calls": inner.calls,
                "sleep_calls": list(clk.sleep_calls),
                "raised_code": raised_code,
                "retry_wait_seconds": wait_reported,
                "passed": inner.calls == 1 and clk.sleep_calls == [] and raised_code == "llm_unavailable" and wait_reported == 0.0,
            }
        )
    checks["malformed_injected_retry_after"] = {
        "passed": all(m["passed"] for m in malformed_results),
        "cases": malformed_results,
    }

    return {
        "report_type": "b_candidate_edge_contracts_verification",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_commit": source_commit,
        "all_passed": all(v["passed"] for v in checks.values()),
        "checks": checks,
    }


def run_resilience_suite(repo_root: Path, label: str, source_commit: str | None = None) -> dict[str, Any]:
    if source_commit is None:
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True
        ).strip()

    trust_env_audit = check_owned_client_trust_env_false()
    rows = [run_schedule(sched, repo_root) for sched in DEFAULT_SCHEDULES]
    n_total = len(rows)
    transient_rows = [r for r in rows if r["expected_if_recovered"] == "draft_ready" and r["schedule_id"] != "S01_clean_success"]
    recovered_transient = sum(1 for r in transient_rows if r["draft_recovered"])
    latencies = sorted(r["simulated_elapsed_seconds"] for r in rows)
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))]
    by_id = {r["schedule_id"]: r for r in rows}

    return {
        "report_type": "controlled_provider_resilience_evaluation",
        "label": label,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_commit": source_commit,
        "controlled_transport_boundary": (
            "Executed via deterministic httpx.MockTransport + ControlledSimClock with 0 external provider calls. "
            "Controlled recovery does NOT establish live provider uptime or real API availability."
        ),
        "external_provider_calls": 0,
        "trust_env_audit": trust_env_audit,
        "summary": {
            "total_schedules": n_total,
            "draft_ready_count": sum(1 for r in rows if r["draft_recovered"]),
            "fallback_count": sum(1 for r in rows if r["fallback_triggered"]),
            "transient_recoverable_schedules": len(transient_rows),
            "transient_recovered_count": recovered_transient,
            "transient_recovery_rate": round(recovered_transient / len(transient_rows), 4) if transient_rows else 0.0,
            "unconditional_trust_env_false": trust_env_audit["unconditional_trust_env_false"],
            "latency_includes_retry_waits_all": all(r["latency_includes_retry_waits"] for r in rows),
            "quota_429_non_retryable_fail_fast": (
                by_id["S17_429_daily_quota_exhausted_non_retryable"]["fallback_triggered"]
                and by_id["S17_429_daily_quota_exhausted_non_retryable"]["attempt_count"] == 1
            ),
            "fast_storm_max_attempts_observed": by_id["S18_fast_503_storm_max_attempts_bound"]["attempt_count"],
            "budget_respected_all": all(r["budget_respected_10s"] for r in rows),
            "attempt_cap_respected_all": all(r["attempt_cap_respected_5s"] for r in rows),
            "no_auto_send_all": all(r["no_auto_send_verified"] for r in rows),
            "zero_fabricated_totals": all(not r["total_tokens_fabricated"] for r in rows),
            "all_attempts_persisted": all(r["attempt_count"] == r["transport_call_count"] and r["attempt_count"] >= 1 for r in rows),
            "simulated_latency_p50_seconds": p50,
            "simulated_latency_p95_seconds": p95,
            "simulated_latency_max_seconds": max(latencies) if latencies else 0.0,
        },
        "schedules": rows,
    }


def compare_resilience_runs(before_report: dict[str, Any], after_report: dict[str, Any]) -> dict[str, Any]:
    before_by_id = {r["schedule_id"]: r for r in before_report["schedules"]}
    after_by_id = {r["schedule_id"]: r for r in after_report["schedules"]}
    schedule_diffs = []
    for sched in DEFAULT_SCHEDULES:
        sid = sched.schedule_id
        b = before_by_id[sid]
        a = after_by_id[sid]
        schedule_diffs.append(
            {
                "schedule_id": sid,
                "category": sched.category,
                "expected_if_recovered": sched.expected_if_recovered,
                "before_status": b["terminal_status"],
                "after_status": a["terminal_status"],
                "before_failure_code": b["failure_code"],
                "after_failure_code": a["failure_code"],
                "before_attempts": b["attempt_count"],
                "after_attempts": a["attempt_count"],
                "before_latency_s": b["simulated_elapsed_seconds"],
                "after_latency_s": a["simulated_elapsed_seconds"],
                "before_reported_latency_s": b["reported_llm_latency_seconds"],
                "after_reported_latency_s": a["reported_llm_latency_seconds"],
                "after_latency_includes_retry_waits": a["latency_includes_retry_waits"],
                "before_usage_status": b["usage_status"],
                "after_usage_status": a["usage_status"],
                "before_budget_ok": b["budget_respected_10s"],
                "after_budget_ok": a["budget_respected_10s"],
                "after_no_auto_send": a["no_auto_send_verified"],
            }
        )

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "before_commit": before_report["source_commit"],
        "after_commit": after_report["source_commit"],
        "controlled_transport_boundary": before_report["controlled_transport_boundary"],
        "before_summary": before_report["summary"],
        "after_summary": after_report["summary"],
        "schedule_comparison": schedule_diffs,
    }

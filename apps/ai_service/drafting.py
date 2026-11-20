"""Retry transient provider failures once inside the existing ten-second LLM budget."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List

from apps.core_backend.llm.gemini import LLMError, MAX_RETRY_AFTER_SECONDS


def _is_valid_token_int(val: Any) -> bool:
    return type(val) is int and not isinstance(val, bool) and val >= 0


class BudgetedDraftClient:
    """Bounded retry client allocating per-attempt timeouts bounded by an overall deadline.

    Timeout allocation semantics:
      - Overall deadline: `deadline = clock() + budget_seconds` (default 10.0s).
      - Per-attempt allocation: Each attempt receives `min(attempt_timeout_seconds, remaining)`
        where `remaining = deadline - clock()`.
      - Per-phase and blocking caveat: httpx timeouts apply per network phase (connect, read,
        write). Synchronous blocking operations in underlying transports cannot be preemptively
        interrupted mid-operation without OS-level thread/process termination; therefore,
        the deadline strictly bounds the allocated attempt timeouts, rather than providing an
        absolute hard preemptive wall-clock kill guarantee if a synchronous transport call overruns.
      - Default attempt timeout: `attempt_timeout_seconds` defaults to 5.0s.
        Configurable via constructor parameter if explicitly specified.
      - Parameter validation: finite positive numbers (> 0) required for all bounds.
      - Sanitized observability: records attempt stage, http_status (null if unobserved),
        exception_category, latency, and token usage without raw provider bodies or credentials.
    """

    def __init__(
        self,
        client,
        clock=time.monotonic,
        budget_seconds: float = 10.0,
        attempt_timeout_seconds: float = 5.0,
        sleep=time.sleep,
        backoff_seconds: float = 0.25,
        max_attempts: int = 2,
    ):
        if not math.isfinite(budget_seconds) or budget_seconds <= 0:
            raise ValueError(f"budget_seconds must be a finite positive number, got {budget_seconds}")
        if not math.isfinite(attempt_timeout_seconds) or attempt_timeout_seconds <= 0:
            raise ValueError(f"attempt_timeout_seconds must be a finite positive number, got {attempt_timeout_seconds}")
        if not math.isfinite(backoff_seconds) or backoff_seconds < 0:
            raise ValueError(f"backoff_seconds must be a finite non-negative number, got {backoff_seconds}")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError(f"max_attempts must be a positive integer, got {max_attempts}")

        self.client = client
        self.clock = clock
        self.sleep = sleep
        self.budget_seconds = float(budget_seconds)
        self.attempt_timeout_seconds = min(float(attempt_timeout_seconds), self.budget_seconds)
        self.backoff_seconds = float(backoff_seconds)
        self.max_attempts = max_attempts
        self.last_attempts: List[Dict[str, Any]] = []

    def close(self) -> None:
        close_fn = getattr(self.client, "close", None)
        if callable(close_fn):
            close_fn()

    def __enter__(self) -> "BudgetedDraftClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _aggregate_usage(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not attempts:
            return {}
        combined: Dict[str, Any] = {}
        prompt_tokens = 0
        candidate_tokens = 0
        total_tokens = 0
        thought_tokens = 0
        has_prompt = False
        has_candidate = False
        has_thought = False
        is_incomplete = False
        has_invalid = False

        all_attempts_reported_total = True
        at_least_one_attempt_had_tokens = False

        for att in attempts:
            u = att.get("usage")
            # If an attempt was made without valid usage dict (e.g. timeout before response), usage is incomplete
            if not isinstance(u, dict) or not u:
                is_incomplete = True
                all_attempts_reported_total = False
                continue

            for k in ("promptTokenCount", "candidatesTokenCount", "totalTokenCount", "thoughtsTokenCount"):
                if k in u and u[k] is not None and not _is_valid_token_int(u[k]):
                    has_invalid = True
                    is_incomplete = True

            p = u.get("promptTokenCount")
            c = u.get("candidatesTokenCount")
            t = u.get("totalTokenCount")
            th = u.get("thoughtsTokenCount")

            if _is_valid_token_int(p):
                prompt_tokens += p
                has_prompt = True
                at_least_one_attempt_had_tokens = True
            elif p is not None:
                has_invalid = True

            if _is_valid_token_int(c):
                candidate_tokens += c
                has_candidate = True
                at_least_one_attempt_had_tokens = True
            elif c is not None:
                has_invalid = True

            if _is_valid_token_int(t):
                total_tokens += t
                at_least_one_attempt_had_tokens = True
            else:
                all_attempts_reported_total = False
                if t is not None:
                    has_invalid = True

            if _is_valid_token_int(th):
                thought_tokens += th
                has_thought = True
            elif th is not None:
                has_invalid = True

        if has_prompt and not has_invalid:
            combined["promptTokenCount"] = prompt_tokens
        if has_candidate and not has_invalid:
            combined["candidatesTokenCount"] = candidate_tokens
        # NEVER fabricate totalTokenCount from p + c!
        if at_least_one_attempt_had_tokens and all_attempts_reported_total and not has_invalid:
            combined["totalTokenCount"] = total_tokens
        if has_thought and not has_invalid:
            combined["thoughtsTokenCount"] = thought_tokens

        if is_incomplete:
            combined["incomplete"] = True
        if has_invalid:
            combined["has_invalid_fields"] = True
            combined["incomplete"] = True

        return combined

    def _total_transport_latency(self, attempts: List[Dict[str, Any]]) -> float:
        """Sum per-attempt transport durations excluding inter-attempt retry sleeps."""
        return round(sum(att.get("latency_seconds", 0.0) or 0.0 for att in attempts), 4)

    def _total_latency(self, attempts: List[Dict[str, Any]], total_wait_seconds: float = 0.0) -> float:
        """Total operation elapsed seconds including per-attempt transport durations and retry sleeps."""
        return round(self._total_transport_latency(attempts) + max(0.0, float(total_wait_seconds)), 4)

    def _last_metadata(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        for att in reversed(attempts):
            if att.get("metadata"):
                return dict(att["metadata"])
        return {}

    def _retry_delay_seconds(self, error: LLMError, attempt: int, http_status: int | None) -> float | None:
        """Return non-negative sleep duration before retry, or None when retry must be aborted."""
        if getattr(error, "retry_after_invalid", False):
            return None
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            if isinstance(retry_after, bool):
                return None
            try:
                delay = float(retry_after)
            except (TypeError, ValueError, OverflowError):
                return None
            if not math.isfinite(delay) or delay < 0.0 or delay > MAX_RETRY_AFTER_SECONDS:
                return None
            return delay
        if error.code == "llm_rate_limited":
            # 429 without a valid Retry-After may represent exhausted daily/project quota; do not spin.
            return None
        if error.code == "llm_timeout":
            return 0.0
        if http_status in (500, 502, 503, 504):
            return min(self.backoff_seconds * (2 ** attempt), 2.0)
        return 0.0

    def _raise_aggregated_error(
        self,
        error: LLMError,
        attempts: List[Dict[str, Any]],
        att_record: Dict[str, Any],
        total_wait_seconds: float = 0.0,
    ) -> None:
        combined_usage = self._aggregate_usage(attempts)
        transport_lat = self._total_transport_latency(attempts)
        wait_lat = round(max(0.0, float(total_wait_seconds)), 4)
        total_lat = self._total_latency(attempts, wait_lat)
        combined_meta = error.metadata or self._last_metadata(attempts)
        raise LLMError(
            error.code,
            usage=combined_usage,
            metadata=combined_meta,
            latency_seconds=total_lat,
            transport_latency_seconds=transport_lat,
            retry_wait_seconds=wait_lat,
            attempts=attempts,
            stage=att_record["stage"],
            http_status=att_record["http_status"],
            exception_category=att_record["exception_category"],
            retry_after=getattr(error, "retry_after", None),
            retry_after_invalid=getattr(error, "retry_after_invalid", False),
        ) from error

    def _raise_budget_exhausted(
        self,
        attempts: List[Dict[str, Any]],
        cause: Exception | None = None,
        fallback_metadata: Dict[str, Any] | None = None,
        total_wait_seconds: float = 0.0,
    ) -> None:
        transport_lat = self._total_transport_latency(attempts)
        wait_lat = round(max(0.0, float(total_wait_seconds)), 4)
        timeout_err = LLMError(
            "llm_timeout",
            usage=self._aggregate_usage(attempts),
            metadata=fallback_metadata or self._last_metadata(attempts),
            latency_seconds=self._total_latency(attempts, wait_lat),
            transport_latency_seconds=transport_lat,
            retry_wait_seconds=wait_lat,
            attempts=attempts,
            stage="transport",
            http_status=None,
            exception_category="timeout",
        )
        self.last_attempts = attempts
        if cause is not None:
            raise timeout_err from cause
        raise timeout_err

    def generate(self, *args, **kwargs) -> Dict[str, Any]:
        deadline = self.clock() + self.budget_seconds
        attempts: List[Dict[str, Any]] = []
        next_remaining: float | None = None
        total_wait_seconds = 0.0
        retryable_codes = ("llm_timeout", "llm_unavailable", "llm_rate_limited")

        for attempt in range(self.max_attempts):
            remaining = (deadline - self.clock()) if next_remaining is None else next_remaining
            next_remaining = None
            if remaining <= 0:
                self._raise_budget_exhausted(attempts, total_wait_seconds=total_wait_seconds)

            t0 = time.perf_counter()
            timeout_sec = min(self.attempt_timeout_seconds, remaining)
            try:
                result = self.client.generate(*args, timeout_seconds=timeout_sec, **kwargs)
                raw_lat = result.get("latency_seconds")
                lat = raw_lat if raw_lat is not None else round(time.perf_counter() - t0, 4)
                client_att = (result.get("attempts") or [{}])[0]
                att_record = {
                    "attempt_index": attempt,
                    "status": "success",
                    "latency_seconds": lat,
                    "stage": client_att.get("stage", "complete"),
                    "http_status": client_att.get("http_status", None),
                    "exception_category": None,
                    "usage": dict(result.get("usage", {})),
                    "metadata": {
                        "provider": result.get("provider"),
                        "model": result.get("model"),
                        "model_version": result.get("model_version"),
                        "prompt_version": result.get("prompt_version"),
                    },
                }
                attempts.append(att_record)
                self.last_attempts = attempts

                combined_usage = self._aggregate_usage(attempts)
                transport_lat = self._total_transport_latency(attempts)
                wait_lat = round(total_wait_seconds, 4)
                total_lat = self._total_latency(attempts, wait_lat)

                result["attempts"] = attempts
                if combined_usage:
                    result["usage"] = combined_usage
                result["transport_latency_seconds"] = transport_lat
                result["retry_wait_seconds"] = wait_lat
                result["latency_seconds"] = total_lat
                return result

            except LLMError as error:
                lat = error.latency_seconds if error.latency_seconds is not None else round(time.perf_counter() - t0, 4)
                err_att = (error.attempts or [{}])[0]
                att_record = {
                    "attempt_index": attempt,
                    "status": error.code,
                    "latency_seconds": lat,
                    "stage": err_att.get("stage") or getattr(error, "stage", "transport"),
                    "http_status": err_att.get("http_status") if "http_status" in err_att else getattr(error, "http_status", None),
                    "exception_category": err_att.get("exception_category") or getattr(error, "exception_category", None),
                    "usage": dict(error.usage or {}),
                    "metadata": dict(error.metadata or {}),
                }
                attempts.append(att_record)
                self.last_attempts = attempts

                has_next_attempt = (attempt + 1) < self.max_attempts
                if not has_next_attempt or error.code not in retryable_codes:
                    self._raise_aggregated_error(error, attempts, att_record, total_wait_seconds=total_wait_seconds)

                remaining_after = deadline - self.clock()
                if remaining_after <= 0:
                    self._raise_budget_exhausted(
                        attempts,
                        cause=error,
                        fallback_metadata=error.metadata,
                        total_wait_seconds=total_wait_seconds,
                    )

                delay = self._retry_delay_seconds(error, attempt, att_record["http_status"])
                if delay is None or delay >= remaining_after:
                    self._raise_aggregated_error(error, attempts, att_record, total_wait_seconds=total_wait_seconds)

                if delay > 0:
                    self.sleep(delay)
                    after_sleep_remaining = deadline - self.clock()
                    actual_wait = max(delay, remaining_after - after_sleep_remaining)
                    total_wait_seconds += actual_wait
                    next_remaining = min(after_sleep_remaining, remaining_after - delay)
                else:
                    next_remaining = remaining_after

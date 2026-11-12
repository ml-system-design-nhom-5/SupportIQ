"""Retry transient provider failures once inside the existing ten-second LLM budget."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List

from apps.core_backend.llm.gemini import LLMError


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
    ):
        if not math.isfinite(budget_seconds) or budget_seconds <= 0:
            raise ValueError(f"budget_seconds must be a finite positive number, got {budget_seconds}")
        if not math.isfinite(attempt_timeout_seconds) or attempt_timeout_seconds <= 0:
            raise ValueError(f"attempt_timeout_seconds must be a finite positive number, got {attempt_timeout_seconds}")

        self.client = client
        self.clock = clock
        self.budget_seconds = float(budget_seconds)
        self.attempt_timeout_seconds = min(float(attempt_timeout_seconds), self.budget_seconds)
        self.last_attempts: List[Dict[str, Any]] = []

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

    def _total_latency(self, attempts: List[Dict[str, Any]]) -> float:
        return round(sum(att.get("latency_seconds", 0.0) or 0.0 for att in attempts), 4)

    def _last_metadata(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        for att in reversed(attempts):
            if att.get("metadata"):
                return dict(att["metadata"])
        return {}

    def generate(self, *args, **kwargs) -> Dict[str, Any]:
        deadline = self.clock() + self.budget_seconds
        attempts: List[Dict[str, Any]] = []

        for attempt in range(2):
            remaining = deadline - self.clock()
            if remaining <= 0:
                timeout_err = LLMError(
                    "llm_timeout",
                    usage=self._aggregate_usage(attempts),
                    metadata=self._last_metadata(attempts),
                    latency_seconds=self._total_latency(attempts),
                    attempts=attempts,
                    stage="transport",
                    http_status=None,
                    exception_category="timeout",
                )
                self.last_attempts = attempts
                raise timeout_err

            t0 = time.perf_counter()
            timeout_sec = min(self.attempt_timeout_seconds, remaining)
            try:
                result = self.client.generate(*args, timeout_seconds=timeout_sec, **kwargs)
                lat = result.get("latency_seconds") or round(time.perf_counter() - t0, 4)
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
                total_lat = self._total_latency(attempts)

                result["attempts"] = attempts
                if combined_usage:
                    result["usage"] = combined_usage
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

                if attempt or error.code not in ("llm_timeout", "llm_unavailable"):
                    combined_usage = self._aggregate_usage(attempts)
                    total_lat = self._total_latency(attempts)
                    combined_meta = error.metadata or self._last_metadata(attempts)
                    raise LLMError(
                        error.code,
                        usage=combined_usage,
                        metadata=combined_meta,
                        latency_seconds=total_lat,
                        attempts=attempts,
                        stage=att_record["stage"],
                        http_status=att_record["http_status"],
                        exception_category=att_record["exception_category"],
                    ) from error

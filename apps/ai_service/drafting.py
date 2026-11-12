"""Retry transient provider failures once inside the existing ten-second LLM budget."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from apps.core_backend.llm.gemini import LLMError


class BudgetedDraftClient:
    def __init__(self, client, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.last_attempts: List[Dict[str, Any]] = []

    def _aggregate_usage(self, attempts: List[Dict[str, Any]]) -> Dict[str, int]:
        if not attempts:
            return {}
        combined: Dict[str, int] = {}
        prompt_tokens = 0
        candidate_tokens = 0
        total_tokens = 0
        thought_tokens = 0
        has_prompt = False
        has_candidate = False
        has_thought = False

        any_had_total = any(
            isinstance((att.get("usage") or {}).get("totalTokenCount"), int)
            and (att.get("usage") or {}).get("totalTokenCount") >= 0
            for att in attempts
        )

        for att in attempts:
            u = att.get("usage", {}) or {}
            p = u.get("promptTokenCount")
            c = u.get("candidatesTokenCount")
            t = u.get("totalTokenCount")
            th = u.get("thoughtsTokenCount")

            if isinstance(p, int) and p >= 0:
                prompt_tokens += p
                has_prompt = True
            if isinstance(c, int) and c >= 0:
                candidate_tokens += c
                has_candidate = True
            if any_had_total:
                if isinstance(t, int) and t >= 0:
                    total_tokens += t
                elif isinstance(p, int) and p >= 0:
                    total_tokens += p + (c if isinstance(c, int) and c >= 0 else 0)
            if isinstance(th, int) and th >= 0:
                thought_tokens += th
                has_thought = True

        if has_prompt:
            combined["promptTokenCount"] = prompt_tokens
        if has_candidate:
            combined["candidatesTokenCount"] = candidate_tokens
        if any_had_total:
            combined["totalTokenCount"] = total_tokens
        if has_thought:
            combined["thoughtsTokenCount"] = thought_tokens
        return combined

    def _total_latency(self, attempts: List[Dict[str, Any]]) -> float:
        return round(sum(att.get("latency_seconds", 0.0) or 0.0 for att in attempts), 4)

    def _last_metadata(self, attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
        for att in reversed(attempts):
            if att.get("metadata"):
                return dict(att["metadata"])
        return {}

    def generate(self, *args, **kwargs) -> Dict[str, Any]:
        deadline = self.clock() + 10
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
                )
                self.last_attempts = attempts
                raise timeout_err

            t0 = time.perf_counter()
            timeout_sec = min(5, remaining)
            try:
                result = self.client.generate(*args, timeout_seconds=timeout_sec, **kwargs)
                lat = result.get("latency_seconds") or round(time.perf_counter() - t0, 4)
                att_record = {
                    "attempt_index": attempt,
                    "status": "success",
                    "latency_seconds": lat,
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
                att_record = {
                    "attempt_index": attempt,
                    "status": error.code,
                    "latency_seconds": lat,
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
                    ) from error

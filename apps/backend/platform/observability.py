"""Application Monitoring, Observability, Structured Logging, and Metrics for SupportIQ."""

from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import math
import os
import re
import sys
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

# Pre-compiled PII redaction patterns for safe log emission
RE_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
RE_PHONE = re.compile(r"(?:\+?84|0)(?:\s*[\.\-]?\s*\d){9,10}\b")
RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def redact_pii_for_logs(text: str) -> str:
    """Mask any residual personal identifiers from log strings."""
    if not isinstance(text, str):
        return text
    text = RE_EMAIL.sub("[REDACTED_EMAIL]", text)
    text = RE_PHONE.sub("[REDACTED_PHONE]", text)
    text = RE_CARD.sub("[REDACTED_CARD]", text)
    return text


def sanitize_dict_for_logs(data: Any) -> Any:
    """Recursively redact dictionary/list values before structured logging."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(term in k.lower() for term in ("password", "secret", "token", "cookie", "key", "auth")):
                sanitized[k] = "[REDACTED_CREDENTIAL]"
            elif isinstance(v, str):
                sanitized[k] = redact_pii_for_logs(v)
            else:
                sanitized[k] = sanitize_dict_for_logs(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_dict_for_logs(item) for item in data]
    elif isinstance(data, str):
        return redact_pii_for_logs(data)
    return data


class StructuredLogger:
    """JSON-lines structured logger with stage context and correlation IDs."""

    def __init__(self, name: str = "supportiq"):
        self.logger = logging.getLogger(name)
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def log(self, level: str, event: str, trace_id: Optional[str] = None,
            ticket_id: Optional[str] = None, stage: Optional[str] = None,
            duration_ms: Optional[float] = None, error_type: Optional[str] = None,
            error_message: Optional[str] = None, **kwargs: Any) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "event": event,
            "trace_id": trace_id or str(uuid.uuid4()),
        }
        if ticket_id:
            payload["ticket_id"] = ticket_id
        if stage:
            payload["stage"] = stage
        if duration_ms is not None:
            payload["duration_ms"] = round(duration_ms, 2)
        if error_type:
            payload["error_type"] = error_type
        if error_message:
            payload["error_message"] = redact_pii_for_logs(error_message)
        if kwargs:
            payload["context"] = sanitize_dict_for_logs(kwargs)

        log_fn = getattr(self.logger, level.lower(), self.logger.info)
        log_fn(json.dumps(payload, ensure_ascii=False))

    def info(self, event: str, **kwargs: Any) -> None:
        self.log("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self.log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self.log("error", event, **kwargs)


class MetricsRegistry:
    """Thread-safe operational metrics collector with percentile and rate calculations."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.http_requests: Counter = Counter()
            self.http_durations: Dict[str, List[float]] = {}
            self.stage_durations: Dict[str, List[float]] = {}
            self.stage_errors: Counter = Counter()
            self.intent_counts: Counter = Counter()
            self.intent_confidences: List[float] = []
            self.ood_count: int = 0
            self.escalation_counts: Counter = Counter()
            self.retrieval_status_counts: Counter = Counter()
            self.retrieval_durations: List[float] = []
            self.evidence_insufficient_count: int = 0
            self.llm_status_counts: Counter = Counter()
            self.llm_durations: List[float] = []
            self.llm_tokens: Counter = Counter()
            self.citation_failures: int = 0
            self.pii_masked_entities: Counter = Counter()
            self.pii_blocked_count: int = 0
            self.draft_status_counts: Counter = Counter()
            self.human_decisions: Counter = Counter()
            self.db_query_durations: List[float] = []
            self.db_errors: int = 0
            self.start_time = datetime.now(timezone.utc)

    def record_http_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        with self._lock:
            key = f"{method.upper()} {path} {status_code}"
            self.http_requests[key] += 1
            path_key = f"{method.upper()} {path}"
            self.http_durations.setdefault(path_key, []).append(duration_ms)
            if len(self.http_durations[path_key]) > 2000:
                self.http_durations[path_key].pop(0)

    def record_stage(self, stage: str, duration_ms: float, error: Optional[str] = None) -> None:
        with self._lock:
            self.stage_durations.setdefault(stage, []).append(duration_ms)
            if len(self.stage_durations[stage]) > 2000:
                self.stage_durations[stage].pop(0)
            if error:
                self.stage_errors[f"{stage}:{error}"] += 1

    def record_intent(self, intent: str, confidence: float, is_ood: bool = False) -> None:
        with self._lock:
            self.intent_counts[intent] += 1
            self.intent_confidences.append(confidence)
            if len(self.intent_confidences) > 2000:
                self.intent_confidences.pop(0)
            if is_ood:
                self.ood_count += 1

    def record_escalation(self, reason_code: str) -> None:
        with self._lock:
            self.escalation_counts[reason_code] += 1

    def record_retrieval(self, status: str, duration_ms: float, insufficient_evidence: bool = False) -> None:
        with self._lock:
            self.retrieval_status_counts[status] += 1
            self.retrieval_durations.append(duration_ms)
            if len(self.retrieval_durations) > 2000:
                self.retrieval_durations.pop(0)
            if insufficient_evidence:
                self.evidence_insufficient_count += 1

    def record_llm(self, status: str, duration_ms: float, prompt_tokens: int = 0, candidate_tokens: int = 0) -> None:
        with self._lock:
            self.llm_status_counts[status] += 1
            self.llm_durations.append(duration_ms)
            if len(self.llm_durations) > 2000:
                self.llm_durations.pop(0)
            self.llm_tokens["prompt"] += prompt_tokens
            self.llm_tokens["candidates"] += candidate_tokens

    def record_citation_failure(self) -> None:
        with self._lock:
            self.citation_failures += 1

    def record_pii(self, count_by_type: Dict[str, int], blocked: bool = False) -> None:
        with self._lock:
            for entity, count in count_by_type.items():
                self.pii_masked_entities[entity] += count
            if blocked:
                self.pii_blocked_count += 1

    def record_draft(self, status: str) -> None:
        with self._lock:
            self.draft_status_counts[status] += 1

    def record_decision(self, decision: str) -> None:
        with self._lock:
            self.human_decisions[decision] += 1

    def record_db(self, duration_ms: float, error: bool = False) -> None:
        with self._lock:
            self.db_query_durations.append(duration_ms)
            if len(self.db_query_durations) > 2000:
                self.db_query_durations.pop(0)
            if error:
                self.db_errors += 1

    @staticmethod
    def _percentiles(values: List[float]) -> Dict[str, Optional[float]]:
        if not values:
            return {"p50": None, "p95": None, "p99": None}
        s = sorted(values)
        n = len(s)
        p50 = s[int(n * 0.50)]
        p95 = s[min(int(n * 0.95), n - 1)]
        p99 = s[min(int(n * 0.99), n - 1)]
        return {"p50": round(p50, 2), "p95": round(p95, 2), "p99": round(p99, 2)}

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            total_requests = sum(self.http_requests.values())
            error_requests = sum(v for k, v in self.http_requests.items() if k.endswith((" 500", " 502", " 503", " 504")))
            error_rate = error_requests / total_requests if total_requests else 0.0

            all_http_durations = [d for durations in self.http_durations.values() for d in durations]
            total_decisions = sum(self.human_decisions.values())

            return {
                "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
                "overview": {
                    "total_requests": total_requests,
                    "error_requests": error_requests,
                    "error_rate": round(error_rate, 4),
                    "api_latency_ms": self._percentiles(all_http_durations),
                },
                "intents": {
                    "total": sum(self.intent_counts.values()),
                    "distribution": dict(self.intent_counts),
                    "ood_count": self.ood_count,
                    "confidence_percentiles": self._percentiles(self.intent_confidences),
                },
                "escalations": {
                    "total": sum(self.escalation_counts.values()),
                    "by_reason": dict(self.escalation_counts),
                },
                "rag": {
                    "requests": sum(self.retrieval_status_counts.values()),
                    "status": dict(self.retrieval_status_counts),
                    "latency_ms": self._percentiles(self.retrieval_durations),
                    "insufficient_evidence_count": self.evidence_insufficient_count,
                },
                "llm": {
                    "requests": sum(self.llm_status_counts.values()),
                    "status": dict(self.llm_status_counts),
                    "latency_ms": self._percentiles(self.llm_durations),
                    "tokens": dict(self.llm_tokens),
                    "citation_failures": self.citation_failures,
                },
                "privacy": {
                    "masked_entities": dict(self.pii_masked_entities),
                    "blocked_requests": self.pii_blocked_count,
                },
                "drafts": {
                    "total": sum(self.draft_status_counts.values()),
                    "by_status": dict(self.draft_status_counts),
                },
                "decisions": {
                    "total": total_decisions,
                    "by_type": dict(self.human_decisions),
                    "approval_rate": round(self.human_decisions.get("approve", 0) / total_decisions, 4) if total_decisions else None,
                    "edit_rate": round(self.human_decisions.get("edit", 0) / total_decisions, 4) if total_decisions else None,
                    "rejection_rate": round(self.human_decisions.get("reject", 0) / total_decisions, 4) if total_decisions else None,
                },
                "database": {
                    "queries": len(self.db_query_durations),
                    "latency_ms": self._percentiles(self.db_query_durations),
                    "errors": self.db_errors,
                },
                "stages": {
                    stage: self._percentiles(durations)
                    for stage, durations in self.stage_durations.items()
                },
            }

    def to_prometheus(self) -> str:
        snap = self.snapshot()
        lines = [
            "# HELP supportiq_http_requests_total Total HTTP requests received",
            "# TYPE supportiq_http_requests_total counter",
            f"supportiq_http_requests_total {snap['overview']['total_requests']}",
            "# HELP supportiq_http_errors_total Total HTTP 5xx errors",
            "# TYPE supportiq_http_errors_total counter",
            f"supportiq_http_errors_total {snap['overview']['error_requests']}",
            "# HELP supportiq_api_latency_p50_ms 50th percentile API latency in ms",
            "# TYPE supportiq_api_latency_p50_ms gauge",
            f"supportiq_api_latency_p50_ms {snap['overview']['api_latency_ms']['p50'] or 0.0}",
            "# HELP supportiq_api_latency_p95_ms 95th percentile API latency in ms",
            "# TYPE supportiq_api_latency_p95_ms gauge",
            f"supportiq_api_latency_p95_ms {snap['overview']['api_latency_ms']['p95'] or 0.0}",
            "# HELP supportiq_escalations_total Total tickets escalated",
            "# TYPE supportiq_escalations_total counter",
            f"supportiq_escalations_total {snap['escalations']['total']}",
            "# HELP supportiq_llm_requests_total Total LLM invocations",
            "# TYPE supportiq_llm_requests_total counter",
            f"supportiq_llm_requests_total {snap['llm']['requests']}",
            "# HELP supportiq_llm_latency_p95_ms 95th percentile LLM latency in ms",
            "# TYPE supportiq_llm_latency_p95_ms gauge",
            f"supportiq_llm_latency_p95_ms {snap['llm']['latency_ms']['p95'] or 0.0}",
            "# HELP supportiq_citation_failures_total Total citation verification failures",
            "# TYPE supportiq_citation_failures_total counter",
            f"supportiq_citation_failures_total {snap['llm']['citation_failures']}",
            "# HELP supportiq_evidence_insufficient_total Total insufficient evidence queries",
            "# TYPE supportiq_evidence_insufficient_total counter",
            f"supportiq_evidence_insufficient_total {snap['rag']['insufficient_evidence_count']}",
            "# HELP supportiq_pii_masked_total Total PII entities masked",
            "# TYPE supportiq_pii_masked_total counter",
            f"supportiq_pii_masked_total {sum(snap['privacy']['masked_entities'].values())}",
        ]
        for reason, count in snap["escalations"]["by_reason"].items():
            lines.append(f'supportiq_escalations_by_reason_total{{reason="{reason}"}} {count}')
        for intent, count in snap["intents"]["distribution"].items():
            lines.append(f'supportiq_intents_total{{intent="{intent}"}} {count}')
        return "\n".join(lines) + "\n"


class ErrorTracker:
    """In-memory recent error ring buffer for real-time triage and diagnosis."""

    def __init__(self, capacity: int = 100) -> None:
        self.capacity = capacity
        self.errors: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record_error(self, stage: str, error_type: str, message: str,
                     trace_id: Optional[str] = None, ticket_id: Optional[str] = None,
                     stack_trace: Optional[str] = None, **details: Any) -> None:
        with self._lock:
            entry = {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "error_type": error_type,
                "message": redact_pii_for_logs(message),
                "trace_id": trace_id,
                "ticket_id": ticket_id,
                "stack_trace": redact_pii_for_logs(stack_trace) if stack_trace else None,
                "details": sanitize_dict_for_logs(details),
            }
            self.errors.appendleft(entry)

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.errors)[:limit]


# Global singleton instances
logger = StructuredLogger("supportiq")
metrics = MetricsRegistry()
error_tracker = ErrorTracker(capacity=100)


@contextmanager
def trace_stage(stage: str, trace_id: Optional[str] = None, ticket_id: Optional[str] = None, **context: Any):
    """Context manager for tracing execution duration and error recording."""
    t0 = time.perf_counter()
    logger.info(f"stage.{stage}.started", trace_id=trace_id, ticket_id=ticket_id, stage=stage, **context)
    error_occurred = None
    try:
        yield
    except Exception as exc:
        error_occurred = exc
        duration_ms = (time.perf_counter() - t0) * 1000
        metrics.record_stage(stage, duration_ms, error=type(exc).__name__)
        error_tracker.record_error(
            stage=stage,
            error_type=type(exc).__name__,
            message=str(exc),
            trace_id=trace_id,
            ticket_id=ticket_id,
            **context,
        )
        logger.error(
            f"stage.{stage}.failed",
            trace_id=trace_id,
            ticket_id=ticket_id,
            stage=stage,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error_message=str(exc),
            **context,
        )
        raise
    else:
        duration_ms = (time.perf_counter() - t0) * 1000
        metrics.record_stage(stage, duration_ms)
        logger.info(
            f"stage.{stage}.completed",
            trace_id=trace_id,
            ticket_id=ticket_id,
            stage=stage,
            duration_ms=duration_ms,
            **context,
        )

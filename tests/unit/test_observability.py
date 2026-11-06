import json
import pytest
from apps.backend.platform.observability import (
    MetricsRegistry,
    ErrorTracker,
    StructuredLogger,
    redact_pii_for_logs,
    sanitize_dict_for_logs,
    trace_stage,
)


def test_redact_pii_for_logs():
    text = "User john.doe@example.com with phone 0912345678 and card 4111 2222 3333 4444 called."
    redacted = redact_pii_for_logs(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_CARD]" in redacted
    assert "john.doe@example.com" not in redacted
    assert "0912345678" not in redacted
    assert "4111 2222 3333 4444" not in redacted


def test_sanitize_dict_for_logs():
    data = {
        "session_token": "secret123",
        "api_key": "secret456",
        "user_email": "test@example.com",
        "nested": {"password": "secret", "note": "call 0987654321"},
    }
    sanitized = sanitize_dict_for_logs(data)
    assert sanitized["session_token"] == "[REDACTED_CREDENTIAL]"
    assert sanitized["api_key"] == "[REDACTED_CREDENTIAL]"
    assert sanitized["user_email"] == "[REDACTED_EMAIL]"
    assert sanitized["nested"]["password"] == "[REDACTED_CREDENTIAL]"
    assert "[REDACTED_PHONE]" in sanitized["nested"]["note"]


def test_metrics_registry_snapshot_and_prometheus():
    reg = MetricsRegistry()
    reg.record_http_request("GET", "/v1/shop/products", 200, 15.5)
    reg.record_http_request("POST", "/v1/shop/tickets", 500, 120.2)
    reg.record_intent("order_tracking", 0.95, is_ood=False)
    reg.record_intent("out_of_domain", 0.40, is_ood=True)
    reg.record_escalation("low_confidence")
    reg.record_retrieval("success", 25.0, insufficient_evidence=False)
    reg.record_retrieval("no_match", 12.0, insufficient_evidence=True)
    reg.record_llm("draft_ready", 850.0, prompt_tokens=100, candidate_tokens=50)
    reg.record_citation_failure()
    reg.record_pii({"EMAIL": 1, "PHONE": 1}, blocked=False)
    reg.record_draft("draft_ready")
    reg.record_decision("approve")

    snap = reg.snapshot()
    assert snap["overview"]["total_requests"] == 2
    assert snap["overview"]["error_requests"] == 1
    assert snap["overview"]["error_rate"] == 0.5
    assert snap["intents"]["total"] == 2
    assert snap["intents"]["ood_count"] == 1
    assert snap["escalations"]["total"] == 1
    assert snap["rag"]["requests"] == 2
    assert snap["rag"]["insufficient_evidence_count"] == 1
    assert snap["llm"]["requests"] == 1
    assert snap["llm"]["citation_failures"] == 1
    assert snap["privacy"]["masked_entities"] == {"EMAIL": 1, "PHONE": 1}
    assert snap["decisions"]["approval_rate"] == 1.0

    prom = reg.to_prometheus()
    assert "supportiq_http_requests_total 2" in prom
    assert "supportiq_http_errors_total 1" in prom
    assert "supportiq_escalations_total 1" in prom
    assert 'supportiq_escalations_by_reason_total{reason="low_confidence"} 1' in prom
    assert 'supportiq_intents_total{intent="order_tracking"} 1' in prom


def test_error_tracker():
    tracker = ErrorTracker(capacity=5)
    tracker.record_error("llm", "TimeoutError", "LLM timeout after 10s", trace_id="tr-1")
    tracker.record_error("retrieval", "IndexError", "Index error on query 0987654321", trace_id="tr-2")

    recent = tracker.list_recent()
    assert len(recent) == 2
    assert recent[0]["stage"] == "retrieval"
    assert recent[0]["trace_id"] == "tr-2"
    assert "[REDACTED_PHONE]" in recent[0]["message"]
    assert recent[1]["stage"] == "llm"


def test_trace_stage():
    with trace_stage("unit_test_stage", trace_id="test-trace"):
        pass

    with pytest.raises(ValueError):
        with trace_stage("failing_stage", trace_id="test-trace"):
            raise ValueError("Test failure error with phone 0912345678")

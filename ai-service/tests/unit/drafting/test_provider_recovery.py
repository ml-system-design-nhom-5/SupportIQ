from __future__ import annotations

import json
from pathlib import Path
import httpx
import pytest

from apps.ai_service.drafting import BudgetedDraftClient
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError


def _make_evidence() -> list[dict]:
    kb = json.loads(Path("data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8"))
    doc = next(d for d in kb if d["document_id"] == "POL-SHIP-004" and str(d["version"]) == "1.0")
    return [doc]


def _success_payload(answer: str = "Please call 1900 6035 for shipping support. [S1]", usage: dict | None = None) -> dict:
    body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "answerable": True,
                                    "answer": answer,
                                    "citations": ["S1"],
                                    "is_clarification": False,
                                }
                            )
                        }
                    ]
                },
            }
        ],
        "modelVersion": "gemini-3.1-flash-lite",
    }
    if usage is not None:
        body["usageMetadata"] = usage
    return body


def test_transient_503_recovers_with_bounded_backoff_and_reuses_http_client():
    clock_state = [0.0]
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        clock_state[0] += 0.2
        if len(seen_requests) == 1:
            return httpx.Response(
                503,
                json={
                    "error": {"code": 503, "message": "Overloaded"},
                    "usageMetadata": {"promptTokenCount": 120},
                },
            )
        return httpx.Response(
            200,
            json=_success_payload(
                usage={"promptTokenCount": 120, "candidatesTokenCount": 40, "totalTokenCount": 160}
            ),
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    gemini = GeminiDraftClient(api_key="test-key", http_client=http_client)
    budgeted = BudgetedDraftClient(gemini, clock=fake_clock, sleep=fake_sleep)

    result = budgeted.generate("What is the shipping hotline?", "shipping_inquiry", _make_evidence())

    assert "1900 6035" in result["body"]
    assert len(seen_requests) == 2
    assert len(sleep_calls) == 1
    assert 0.0 < sleep_calls[0] <= 2.0
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["status"] == "llm_unavailable"
    assert result["attempts"][0]["http_status"] == 503
    assert result["attempts"][1]["status"] == "success"
    assert result["attempts"][1]["http_status"] == 200
    assert result["usage"]["promptTokenCount"] == 240
    assert result["usage"]["candidatesTokenCount"] == 40
    assert "totalTokenCount" not in result["usage"]

    # Subsequent request reuses the same http_client instance without closing it
    result_2 = budgeted.generate("What is the shipping hotline?", "shipping_inquiry", _make_evidence())
    assert "1900 6035" in result_2["body"]
    assert len(seen_requests) == 3
    assert gemini._http is http_client
    assert not http_client.is_closed
    budgeted.close()
    assert not http_client.is_closed
    http_client.close()


def test_429_with_retry_after_within_budget_waits_and_recovers():
    clock_state = [0.0]
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        clock_state[0] += 0.25
        if len(seen_requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "1.5"},
                json={
                    "error": {"code": 429, "message": "Rate limited"},
                    "usageMetadata": {"promptTokenCount": 90},
                },
            )
        return httpx.Response(
            200,
            json=_success_payload(
                usage={"promptTokenCount": 90, "candidatesTokenCount": 30, "totalTokenCount": 120}
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http_client:
        gemini = GeminiDraftClient(api_key="test-key", http_client=http_client)
        budgeted = BudgetedDraftClient(gemini, clock=fake_clock, sleep=fake_sleep)
        result = budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert "1900 6035" in result["body"]
    assert len(seen_requests) == 2
    assert sleep_calls == [1.5]
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["status"] == "llm_rate_limited"
    assert result["attempts"][0]["http_status"] == 429
    assert result["attempts"][1]["status"] == "success"
    assert result["usage"]["promptTokenCount"] == 180
    assert result["usage"]["candidatesTokenCount"] == 30


@pytest.mark.parametrize("status,expected_code", [(429, "llm_rate_limited"), (503, "llm_unavailable")])
def test_retry_after_exceeding_remaining_budget_fails_fast_without_sleeping(status: int, expected_code: str):
    clock_state = [0.0]
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        clock_state[0] += 0.3
        return httpx.Response(
            status,
            headers={"Retry-After": "15"},
            json={"error": {"code": status, "message": "Wait longer than budget"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http_client:
        gemini = GeminiDraftClient(api_key="test-key", http_client=http_client)
        budgeted = BudgetedDraftClient(gemini, clock=fake_clock, sleep=fake_sleep, budget_seconds=10.0)
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    err = exc_info.value
    assert err.code == expected_code
    assert err.http_status == status
    assert err.retry_after == 15.0
    assert len(seen_requests) == 1
    assert sleep_calls == []
    assert len(err.attempts) == 1


@pytest.mark.parametrize(
    "status,expected_code",
    [
        (400, "llm_request_rejected"),
        (401, "llm_auth_error"),
        (403, "llm_auth_error"),
        (404, "llm_model_unavailable"),
        (413, "llm_request_rejected"),
        (422, "llm_request_rejected"),
    ],
)
def test_permanent_4xx_errors_fail_immediately_without_retry(status: int, expected_code: str):
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        if len(seen_requests) > 1:
            raise AssertionError(f"Permanent HTTP {status} must not be retried")
        return httpx.Response(
            status,
            json={"error": {"code": status, "message": "SECRET_BODY_SHOULD_NOT_LEAK"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http_client:
        gemini = GeminiDraftClient(api_key="super-secret-api-key", http_client=http_client)
        budgeted = BudgetedDraftClient(gemini, sleep=lambda s: sleep_calls.append(s))
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    err = exc_info.value
    assert err.code == expected_code
    assert err.http_status == status
    assert len(seen_requests) == 1
    assert sleep_calls == []
    assert len(err.attempts) == 1
    assert "SECRET_BODY_SHOULD_NOT_LEAK" not in repr(err)
    assert "super-secret-api-key" not in repr(err)


def test_exhausted_deadline_skips_second_call_and_preserves_attempt_accounting():
    clock_state = [0.0]
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def fake_clock() -> float:
        return clock_state[0]

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        clock_state[0] += 10.2  # Consumes beyond the 10.0s total budget
        return httpx.Response(
            503,
            json={
                "error": {"code": 503, "message": "Slow 503 SECRET_BODY"},
                "usageMetadata": {"promptTokenCount": 250},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as http_client:
        gemini = GeminiDraftClient(api_key="super-secret-api-key", http_client=http_client)
        budgeted = BudgetedDraftClient(gemini, clock=fake_clock, sleep=lambda s: sleep_calls.append(s))
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    err = exc_info.value
    assert err.code == "llm_timeout"
    assert len(seen_requests) == 1
    assert sleep_calls == []
    assert len(err.attempts) == 1
    assert err.attempts[0]["http_status"] == 503
    assert err.usage["promptTokenCount"] == 250
    assert "totalTokenCount" not in err.usage
    assert "SECRET_BODY" not in str(err.metadata)
    assert "super-secret-api-key" not in str(err.attempts)


def test_owned_http_client_preserves_httpx_defaults_reuses_and_closes_only_owned(monkeypatch):
    created_clients: list[httpx.Client] = []
    call_count = 0

    def transport_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json=_success_payload(
                usage={"promptTokenCount": 50, "candidatesTokenCount": 10, "totalTokenCount": 60}
            ),
        )

    real_client_cls = httpx.Client

    def tracking_client(*args, **kwargs):
        # Preserve default httpx trust_env/pool behavior (no forced trust_env=False override)
        assert "trust_env" not in kwargs
        kwargs["transport"] = httpx.MockTransport(transport_handler)
        c = real_client_cls(*args, **kwargs)
        created_clients.append(c)
        return c

    monkeypatch.setattr("apps.core_backend.llm.gemini.httpx.Client", tracking_client)

    gemini = GeminiDraftClient(api_key="dummy-key")
    budgeted = BudgetedDraftClient(gemini)

    res1 = budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())
    res2 = budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert "1900 6035" in res1["body"]
    assert "1900 6035" in res2["body"]
    assert call_count == 2
    assert len(created_clients) == 1
    assert created_clients[0]._trust_env is True
    assert not created_clients[0].is_closed

    budgeted.close()
    assert created_clients[0].is_closed

    # Caller-injected http_client retains caller ownership across close()
    injected = real_client_cls(transport=httpx.MockTransport(transport_handler))
    gemini_injected = GeminiDraftClient(api_key="dummy-key", http_client=injected)
    budgeted_injected = BudgetedDraftClient(gemini_injected)
    budgeted_injected.generate("Hotline?", "shipping_inquiry", _make_evidence())
    budgeted_injected.close()
    assert not injected.is_closed
    injected.close()


def test_http_date_and_delta_retry_after_defensive_parsing():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from apps.core_backend.llm.gemini import _parse_retry_after

    future_dt = datetime.fromtimestamp(1_700_000_010, tz=timezone.utc)
    resp_http_date = httpx.Response(503, headers={"Retry-After": format_datetime(future_dt, usegmt=True)})
    assert _parse_retry_after(resp_http_date, now_ts=1_700_000_000.0) == pytest.approx(10.0)

    # Past HTTP-date -> negative delta rejected
    resp_past = httpx.Response(503, headers={"Retry-After": format_datetime(future_dt - timedelta(seconds=20), usegmt=True)})
    assert _parse_retry_after(resp_past, now_ts=1_700_000_000.0) is None

    # Far-future oversize HTTP-date (> 86400s) rejected
    resp_far = httpx.Response(503, headers={"Retry-After": format_datetime(future_dt + timedelta(days=5), usegmt=True)})
    assert _parse_retry_after(resp_far, now_ts=1_700_000_000.0) is None

    # Reject NaN, inf, negative, non-numeric garbage, and oversize numeric delta-seconds
    for bad_val in ("NaN", "inf", "-inf", "-1", "-0.5", "999999", "not-a-number", ""):
        assert _parse_retry_after(httpx.Response(429, headers={"Retry-After": bad_val})) is None

    assert _parse_retry_after(httpx.Response(429, headers={"Retry-After": "0"})) == 0.0
    assert _parse_retry_after(httpx.Response(429, headers={"Retry-After": "2.5"})) == pytest.approx(2.5)

    resp_retry_info = httpx.Response(429)
    err_body = {
        "error": {
            "code": 429,
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "2.5s"}],
        }
    }
    assert _parse_retry_after(resp_retry_info, err_body) == pytest.approx(2.5)


@pytest.mark.parametrize("headers", [{}, {"Retry-After": "-2"}, {"Retry-After": "NaN"}, {"Retry-After": "999999"}])
def test_429_without_valid_retry_after_never_spins_or_sleeps(headers: dict):
    sleep_calls: list[float] = []
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            429,
            headers=headers,
            json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        budgeted = BudgetedDraftClient(
            GeminiDraftClient(api_key="test-key", http_client=http_client),
            sleep=lambda s: sleep_calls.append(s),
        )
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    err = exc_info.value
    assert err.code == "llm_rate_limited"
    assert len(seen_requests) == 1
    assert sleep_calls == []
    assert len(err.attempts) == 1


def test_wait_counted_in_deadline_and_no_sleep_after_last_allowable_attempt():
    # Even if a sleep stub does not advance the clock, wait duration is counted against deadline
    sleep_calls: list[float] = []
    recorded_timeouts: list[float] = []

    class WaitCountingClient:
        def __init__(self):
            self.calls = 0

        def generate(self, *args, timeout_seconds=None, **kwargs):
            recorded_timeouts.append(timeout_seconds)
            self.calls += 1
            if self.calls == 1:
                raise LLMError("llm_rate_limited", http_status=429, retry_after=1.5)
            raise LLMError("llm_rate_limited", http_status=429, retry_after=1.0)

    client = WaitCountingClient()
    budgeted = BudgetedDraftClient(
        client,
        clock=lambda: 0.0,  # Frozen clock proves wait still deducts from remaining budget
        sleep=lambda s: sleep_calls.append(s),
        budget_seconds=4.0,
        attempt_timeout_seconds=4.0,
        max_attempts=2,
    )
    with pytest.raises(LLMError) as exc_info:
        budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    err = exc_info.value
    assert err.code == "llm_rate_limited"
    assert recorded_timeouts == [4.0, 2.5]  # 4.0 - 1.5s Retry-After wait = 2.5s remaining
    assert sleep_calls == [1.5]  # No sleep after final attempt (attempt 1)
    assert len(err.attempts) == 2


def test_schema_and_citation_errors_are_not_retried():
    for bad_payload, expected_code in [
        ("not-json", "llm_invalid_response"),
        ({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}, "llm_invalid_response"),
        (
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "answerable": True,
                                            "answer": "Please call 1900 6035 [S99].",
                                            "citations": ["S99"],
                                            "is_clarification": False,
                                        }
                                    )
                                }
                            ]
                        },
                    }
                ]
            },
            "llm_invalid_citations",
        ),
    ]:
        calls = 0
        sleeps: list[float] = []

        def handler(request: httpx.Request, body=bad_payload) -> httpx.Response:
            nonlocal calls
            calls += 1
            if isinstance(body, str):
                return httpx.Response(200, text=body)
            return httpx.Response(200, json=body)

        with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
            budgeted = BudgetedDraftClient(
                GeminiDraftClient(api_key="test-key", http_client=http_client),
                sleep=lambda s: sleeps.append(s),
            )
            with pytest.raises(LLMError) as exc_info:
                budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

        assert exc_info.value.code == expected_code
        assert calls == 1
        assert sleeps == []


def test_http_408_and_stale_keepalive_remote_protocol_error_recover_within_budget():
    clock_state = [0.0]
    sleep_calls: list[float] = []
    calls = 0

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    def handler_408(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        clock_state[0] += 0.5
        if calls == 1:
            return httpx.Response(408, json={"error": {"code": 408, "message": "Request Timeout"}})
        return httpx.Response(
            200,
            json=_success_payload(
                usage={"promptTokenCount": 80, "candidatesTokenCount": 20, "totalTokenCount": 100}
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler_408), trust_env=False) as http_client:
        budgeted = BudgetedDraftClient(
            GeminiDraftClient(api_key="test-key", http_client=http_client),
            clock=fake_clock,
            sleep=fake_sleep,
        )
        res = budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert "1900 6035" in res["body"]
    assert calls == 2
    assert sleep_calls == []  # 408 maps to llm_timeout, so no extra backoff sleep added
    assert res["attempts"][0]["status"] == "llm_timeout"
    assert res["attempts"][0]["http_status"] == 408

    # RemoteProtocolError (e.g. stale keepalive reset) recovers on retry with bounded backoff
    proto_calls = 0
    proto_sleeps: list[float] = []

    def handler_proto(request: httpx.Request) -> httpx.Response:
        nonlocal proto_calls
        proto_calls += 1
        if proto_calls == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.", request=request)
        return httpx.Response(
            200,
            json=_success_payload(
                usage={"promptTokenCount": 80, "candidatesTokenCount": 20, "totalTokenCount": 100}
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(handler_proto), trust_env=False) as http_client:
        budgeted = BudgetedDraftClient(
            GeminiDraftClient(api_key="test-key", http_client=http_client),
            clock=fake_clock,
            sleep=lambda s: proto_sleeps.append(s),
        )
        res_proto = budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert "1900 6035" in res_proto["body"]
    assert proto_calls == 2
    assert res_proto["attempts"][0]["status"] == "llm_unavailable"
    assert res_proto["attempts"][0]["exception_category"] == "http_error"


def test_elapsed_accounting_includes_retry_waits_without_double_counting_on_success_and_failure():
    clock_state = [0.0]
    sleep_calls: list[float] = []

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    class TimedClient:
        def __init__(self, fail_both: bool = False):
            self.calls = 0
            self.fail_both = fail_both

        def generate(self, *args, timeout_seconds=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                clock_state[0] += 0.3
                raise LLMError("llm_unavailable", http_status=503, latency_seconds=0.3)
            clock_state[0] += 0.4
            if self.fail_both:
                raise LLMError("llm_unavailable", http_status=503, latency_seconds=0.4)
            return {"body": "Recovered [S1]", "latency_seconds": 0.4, "attempts": [{"stage": "complete", "http_status": 200}]}

    # 1. Success after 503 + backoff wait
    budgeted_ok = BudgetedDraftClient(TimedClient(fail_both=False), clock=fake_clock, sleep=fake_sleep, backoff_seconds=0.25)
    res = budgeted_ok.generate("Hotline?", "shipping_inquiry", _make_evidence())
    assert sleep_calls == [0.25]
    assert res["attempts"][0]["latency_seconds"] == pytest.approx(0.3)
    assert res["attempts"][1]["latency_seconds"] == pytest.approx(0.4)
    assert res["transport_latency_seconds"] == pytest.approx(0.7)
    assert res["retry_wait_seconds"] == pytest.approx(0.25)
    assert res["latency_seconds"] == pytest.approx(0.95)
    assert clock_state[0] == pytest.approx(0.95)  # Matches total elapsed with zero double counting

    # 2. Failure (503 -> 503) exposes total elapsed including wait and per-attempt transport durations
    clock_state[0] = 0.0
    sleep_calls.clear()
    budgeted_fail = BudgetedDraftClient(TimedClient(fail_both=True), clock=fake_clock, sleep=fake_sleep, backoff_seconds=0.25)
    with pytest.raises(LLMError) as exc_info:
        budgeted_fail.generate("Hotline?", "shipping_inquiry", _make_evidence())
    err = exc_info.value
    assert sleep_calls == [0.25]
    assert err.attempts[0]["latency_seconds"] == pytest.approx(0.3)
    assert err.attempts[1]["latency_seconds"] == pytest.approx(0.4)
    assert err.transport_latency_seconds == pytest.approx(0.7)
    assert err.retry_wait_seconds == pytest.approx(0.25)
    assert err.latency_seconds == pytest.approx(0.95)


def test_exhausted_budget_with_wait_exposes_total_elapsed_and_transport_split():
    clock_state = [0.0]
    sleep_calls: list[float] = []

    def fake_clock() -> float:
        return clock_state[0]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock_state[0] += seconds

    class SlowRetryingClient:
        def __init__(self):
            self.calls = 0

        def generate(self, *args, timeout_seconds=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                clock_state[0] += 0.6
                raise LLMError("llm_unavailable", http_status=503, retry_after=0.5, latency_seconds=0.6)
            clock_state[0] += 0.5
            raise LLMError("llm_timeout", latency_seconds=0.5)

    budgeted = BudgetedDraftClient(
        SlowRetryingClient(),
        clock=fake_clock,
        sleep=fake_sleep,
        budget_seconds=1.5,
        attempt_timeout_seconds=1.0,
    )
    with pytest.raises(LLMError) as exc_info:
        budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())
    err = exc_info.value
    assert sleep_calls == [0.5]
    assert err.attempts[0]["latency_seconds"] == pytest.approx(0.6)
    assert err.attempts[1]["latency_seconds"] == pytest.approx(0.5)
    assert err.transport_latency_seconds == pytest.approx(1.1)
    assert err.retry_wait_seconds == pytest.approx(0.5)
    assert err.latency_seconds == pytest.approx(1.6)


def test_retry_info_requires_documented_type_and_hard_quota_429_never_retries():
    from apps.core_backend.llm.gemini import _parse_retry_after

    # Arbitrary @type must NOT be accepted as RetryInfo
    non_retry_info_body = {
        "error": {
            "code": 429,
            "details": [{"@type": "type.googleapis.com/other.CustomDetail", "retryDelay": "1.5s"}],
        }
    }
    assert _parse_retry_after(httpx.Response(429), non_retry_info_body) is None

    # Known hard daily/billing quota 429 must NEVER retry even if RetryInfo or Retry-After is present
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "1.0"},
            json={
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "You exceeded your current quota for requests per day.",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                        },
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1s"},
                    ],
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        budgeted = BudgetedDraftClient(
            GeminiDraftClient(api_key="test-key", http_client=http_client),
            sleep=lambda s: sleeps.append(s),
        )
        with pytest.raises(LLMError) as exc_info:
            budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert exc_info.value.code == "llm_rate_limited"
    assert calls == 1
    assert sleeps == []


@pytest.mark.parametrize("bad_retry_after", ["not-a-number", object(), True, float("nan"), float("inf"), -1.0, 999999.0])
def test_malformed_injected_retry_after_fails_closed_without_crashing(bad_retry_after):
    calls = 0
    sleeps: list[float] = []

    class MalformedRetryAfterClient:
        def generate(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise LLMError("llm_rate_limited", http_status=429, retry_after=bad_retry_after)

    budgeted = BudgetedDraftClient(MalformedRetryAfterClient(), sleep=lambda s: sleeps.append(s))
    with pytest.raises(LLMError) as exc_info:
        budgeted.generate("Hotline?", "shipping_inquiry", _make_evidence())

    assert exc_info.value.code == "llm_rate_limited"
    assert calls == 1
    assert sleeps == []

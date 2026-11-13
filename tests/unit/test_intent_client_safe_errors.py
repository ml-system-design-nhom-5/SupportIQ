"""Regression tests verifying IntentClient never leaks exception or raw error secrets."""

import json
import httpx
import pytest

from apps.core_backend.intent.client import IntentClient


FAKE_SECRET_TOKEN = "SECRET_TOKEN_XYZ_987"
FAKE_SECRET_PASS = "SUPER_SECRET_PASS_456"
FAKE_API_KEY = "sk-live-secret-api-key-999"
FAKE_SECRET_URL = f"https://svc:{FAKE_SECRET_PASS}@ml.internal/predict?api_key={FAKE_API_KEY}"


def _assert_no_secrets(prediction) -> None:
    dumped = json.dumps(prediction.model_dump(), sort_keys=True)
    for secret in (FAKE_SECRET_TOKEN, FAKE_SECRET_PASS, FAKE_API_KEY, FAKE_SECRET_URL):
        assert secret not in dumped, f"Secret leaked into IntentPrediction: {dumped}"


def _make_mock_client(handler, *, base_url: str = "http://ml-service", expected_model_version: str = "v1.0.0") -> IntentClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return IntentClient(
        base_url=base_url,
        expected_model_version=expected_model_version,
        http_client=http_client,
    )


def test_timeout_exception_does_not_leak_url_or_secrets():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"Read timed out for {FAKE_SECRET_URL}", request=request)

    client = _make_mock_client(handler, base_url=f"https://svc:{FAKE_SECRET_PASS}@ml.internal")
    pred = client.classify_intent("Where is my order?")

    assert pred.intent == "unknown"
    assert pred.confidence == 0.0
    assert pred.failure_code == "ml_timeout"
    assert pred.error == "ML inference timed out"
    _assert_no_secrets(pred)


def test_connect_and_generic_exceptions_do_not_leak_secrets():
    def connect_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"Connect failed: {FAKE_SECRET_URL}", request=request)

    client_conn = _make_mock_client(connect_handler)
    pred_conn = client_conn.classify_intent("Where is my order?")

    assert pred_conn.intent == "unknown"
    assert pred_conn.failure_code == "ml_error"
    assert pred_conn.error == "ML inference failed (ConnectError)"
    _assert_no_secrets(pred_conn)

    def runtime_handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"Unexpected upstream token {FAKE_SECRET_TOKEN}")

    client_rt = _make_mock_client(runtime_handler)
    pred_rt = client_rt.classify_intent("Where is my order?")

    assert pred_rt.intent == "unknown"
    assert pred_rt.failure_code == "ml_error"
    assert pred_rt.error == "ML inference failed (RuntimeError)"
    _assert_no_secrets(pred_rt)


@pytest.mark.parametrize(
    "handler",
    [
        lambda req: httpx.Response(200, content=f"<html>{FAKE_SECRET_TOKEN}</html>".encode("utf-8")),
        lambda req: httpx.Response(
            200,
            json={"intent": FAKE_SECRET_TOKEN, "confidence": "nan", "model_version": "v1.0.0"},
        ),
        lambda req: httpx.Response(
            200,
            json={"intent": "   ", "confidence": 0.9, "model_version": "v1.0.0"},
        ),
    ],
)
def test_value_error_and_invalid_json_do_not_leak_secrets(handler):
    client = _make_mock_client(handler)
    pred = client.classify_intent("Return policy?")

    assert pred.intent == "unknown"
    assert pred.failure_code == "invalid_model_output"
    assert pred.error == "Invalid inference payload"
    _assert_no_secrets(pred)


def test_value_error_raised_inside_transport_does_not_leak_secret():
    def handler(request: httpx.Request) -> httpx.Response:
        raise ValueError(f"Malformed secret {FAKE_SECRET_TOKEN}")

    client = _make_mock_client(handler)
    pred = client.classify_intent("Return policy?")

    assert pred.intent == "unknown"
    assert pred.failure_code == "invalid_model_output"
    assert pred.error == "Invalid inference payload"
    _assert_no_secrets(pred)


def test_http_status_error_with_secret_body_stays_bounded_and_typed():
    def html_503_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            text=f"<html>Upstream error for {FAKE_SECRET_URL} token={FAKE_SECRET_TOKEN}</html>",
        )

    pred_503 = _make_mock_client(html_503_handler).classify_intent("Help")
    assert pred_503.failure_code == "ml_error"
    assert pred_503.error == "HTTP 503: ml_error"
    _assert_no_secrets(pred_503)

    def header_503_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            headers={"X-SupportIQ-Error-Code": "ml_unavailable"},
            text=f"secret={FAKE_SECRET_TOKEN}",
        )

    pred_header = _make_mock_client(header_503_handler).classify_intent("Help")
    assert pred_header.failure_code == "ml_unavailable"
    assert pred_header.error == "HTTP 503: ml_unavailable"
    _assert_no_secrets(pred_header)

    def body_detail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={"detail": {"error_code": "ml_unavailable", "debug": FAKE_SECRET_TOKEN}},
        )

    pred_body = _make_mock_client(body_detail_handler).classify_intent("Help")
    assert pred_body.failure_code == "ml_unavailable"
    assert pred_body.error == "HTTP 502: ml_unavailable"
    _assert_no_secrets(pred_body)

    def timeout_status_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, text=f"Gateway timeout {FAKE_API_KEY}")

    pred_504 = _make_mock_client(timeout_status_handler).classify_intent("Help")
    assert pred_504.failure_code == "ml_timeout"
    assert pred_504.error == "HTTP 504: ml_timeout"
    _assert_no_secrets(pred_504)


def test_version_mismatch_and_200_error_payload_do_not_leak_secrets():
    def mismatch_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"intent": "return_policy", "confidence": 0.9, "model_version": f"v2-{FAKE_SECRET_TOKEN}"},
        )

    pred_mismatch = _make_mock_client(mismatch_handler).classify_intent("Return?")
    assert pred_mismatch.intent == "unknown"
    assert pred_mismatch.failure_code == "ml_error"
    assert pred_mismatch.error is not None and "version mismatch" in pred_mismatch.error.lower()
    _assert_no_secrets(pred_mismatch)

    def error_200_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "intent": "unknown",
                "confidence": 0.0,
                "margin": 0.0,
                "model_version": "v1.0.0",
                "error": f"Upstream leaked {FAKE_SECRET_TOKEN}",
                "failure_code": "ml_unavailable",
            },
        )

    pred_200_err = _make_mock_client(error_200_handler).classify_intent("Return?")
    assert pred_200_err.failure_code == "ml_unavailable"
    assert pred_200_err.error == "ML inference reported failure: ml_unavailable"
    _assert_no_secrets(pred_200_err)


def test_valid_200_prediction_preserves_normal_behavior():
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "intent": "return_policy",
                "confidence": 0.91,
                "margin": 0.42,
                "model_version": "v1.0.0",
                "score_kind": "calibrated_temperature",
            },
        )

    pred = _make_mock_client(ok_handler).classify_intent("How do returns work?")
    assert pred.intent == "return_policy"
    assert pred.confidence == 0.91
    assert pred.margin == 0.42
    assert pred.model_version == "v1.0.0"
    assert pred.error is None
    assert pred.failure_code is None

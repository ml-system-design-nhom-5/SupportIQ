import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from services.ml_inference.app import app, container, ModelContainer
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.schemas import IntentPrediction

# Populate a mock model inside container for unit tests so we don't load heavy torch weights in unit tests
@pytest.fixture(autouse=True)
def mock_container_model():
    container.model = MagicMock()
    container.tokenizer = MagicMock()
    container.id2label = {i: f"label_{i}" for i in range(46)}
    container.id2label[0] = "track_order"
    container.id2label[1] = "cancel_order"
    container.model_version = "v1.0.0"
    container.model_checksum = "fake_sha256"
    container.tokenizer_checksum = "fake_tok_sha256"

client = TestClient(app)

def test_health_and_readiness_endpoints():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json()["ready"] is True
    assert "model_version" in res.json()


def test_predict_success_format():
    with patch.object(container, "predict") as mock_predict:
        mock_predict.return_value = {
            "intent": "track_order",
            "confidence": 0.95,
            "margin": 0.80,
            "top_k": [{"intent": "track_order", "probability": 0.95}],
            "score_kind": "uncalibrated_softmax",
            "model_version": "v1.0.0",
            "model_checksum": "fake_sha",
            "tokenizer_checksum": "fake_tok_sha",
        }
        payload = {
            "text": "Where is my order #12345?",
            "request_id": "req-001",
            "expected_model_version": "v1.0.0"
        }
        res = client.post("/predict", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["request_id"] == "req-001"
        assert data["intent"] == "track_order"
        assert data["confidence"] == 0.95
        assert data["margin"] == 0.80
        assert len(data["top_k"]) == 1
        assert data["score_kind"] == "uncalibrated_softmax"
        assert data["model_version"] == "v1.0.0"


def test_model_version_mismatch():
    payload = {
        "text": "Hello",
        "request_id": "req-002",
        "expected_model_version": "v999.0.0"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 400
    assert "version mismatch" in res.json()["detail"].lower()


def test_ml_failure_never_returns_regex_prediction():
    """Client must return typed error or raise exception, never fabricate regex confidence."""
    intent_client = IntentClient(base_url="http://testservice")

    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = Exception("Service unavailable")
        mock_post.return_value = mock_response

        pred = intent_client.classify_intent("Where is my order?", request_id="req-err")
        assert pred.error is not None
        assert pred.confidence == 0.0
        assert pred.intent == "unknown"


def test_wrong_labels_mapping_fails_validation():
    bad_container = ModelContainer()
    bad_container.model = MagicMock()
    bad_container.tokenizer = MagicMock()
    bad_container.id2label = {0: "single_label"}
    assert bad_container.is_ready() is False

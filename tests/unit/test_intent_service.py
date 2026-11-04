import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from services.ml_inference.app import (
    app,
    container,
    ModelContainer,
    EXPECTED_MANIFEST,
    EXPECTED_46_LABELS,
)
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.schemas import IntentPrediction

# Populate a mock model inside container for unit tests
@pytest.fixture(autouse=True)
def mock_container_model():
    container.model = MagicMock()
    container.tokenizer = MagicMock()
    # Continuous keys 0..45 matching bijection of 46 standard labels
    container.id2label = {i: label for i, label in enumerate(sorted(list(EXPECTED_46_LABELS)))}
    container.verified_model_version = "v1.0.0"
    container.model_checksum = EXPECTED_MANIFEST["weights_sha256"]
    container.tokenizer_checksum = EXPECTED_MANIFEST["tokenizer_sha256"]

client = TestClient(app)

def test_health_and_readiness_endpoints():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = client.get("/ready")
    assert res.status_code == 200
    assert res.json()["ready"] is True
    assert res.json()["model_version"] == "v1.0.0"


def test_predict_success_format():
    with patch.object(container, "predict") as mock_predict:
        mock_predict.return_value = {
            "intent": "track_order",
            "confidence": 0.95,
            "margin": 0.80,
            "top_k": [{"intent": "track_order", "probability": 0.95}],
            "score_kind": "uncalibrated_softmax",
            "model_version": "v1.0.0",
            "model_checksum": EXPECTED_MANIFEST["weights_sha256"],
            "tokenizer_checksum": EXPECTED_MANIFEST["tokenizer_sha256"],
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


def test_client_rejects_mismatched_response_version():
    """Client must verify response model version matches expected version."""
    intent_client = IntentClient(base_url="http://testservice", expected_model_version="v1.0.0")

    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Server returned 200 but wrong model version
        mock_response.json.return_value = {
            "intent": "track_order",
            "confidence": 0.95,
            "model_version": "wrong_revision_v2",
        }
        mock_post.return_value = mock_response

        pred = intent_client.classify_intent("Where is my order?")
        assert pred.error is not None
        assert "version mismatch" in pred.error.lower()
        assert pred.confidence == 0.0


def test_duplicate_or_invalid_label_mapping_fails_bijection():
    """Duplicate labels (e.g. all set to return_policy) must fail bijection check."""
    bad_container = ModelContainer()
    bad_container.model = MagicMock()
    bad_container.tokenizer = MagicMock()
    bad_container.verified_model_version = "v1.0.0"
    # Duplicate mapping
    bad_container.id2label = {i: "return_policy" for i in range(46)}
    assert bad_container.validate_label_bijection() is False
    assert bad_container.is_ready() is False

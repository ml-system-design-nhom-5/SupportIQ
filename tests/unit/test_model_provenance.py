import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.ml_inference.app import (
    ModelContainer,
    EXPECTED_MANIFEST,
    EXPECTED_46_LABELS,
    app,
    container,
)


@pytest.fixture
def clean_env(monkeypatch):
    """Ensure dev fallback is not enabled via environment."""
    monkeypatch.delenv("SUPPORTIQ_DEV_FALLBACK_MODEL", raising=False)


def test_missing_model_directory_fails_closed(clean_env):
    """If the model directory does not exist, container must fail closed without fallback."""
    mc = ModelContainer()
    nonexistent = Path(tempfile.gettempdir()) / "nonexistent_model_dir_12345"
    if nonexistent.exists():
        nonexistent.rmdir()

    mc.load(nonexistent)

    assert mc.is_ready() is False
    assert getattr(mc, "verified", False) is False
    assert getattr(mc, "model_mode", "unavailable") == "unavailable"
    assert mc.verified_model_version is None
    assert mc.model_checksum is None
    assert mc.tokenizer_checksum is None
    with pytest.raises(RuntimeError, match="not loaded, verified, or ready"):
        mc.predict("Where is my order?")


@pytest.mark.parametrize("missing_file", ["model.safetensors", "tokenizer.json", "config.json"])
def test_missing_individual_artifact_fails_closed_by_default(clean_env, missing_file):
    """If any required file is missing in an existing model directory, fail closed by default."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        # Create all files except missing_file
        all_files = {
            "model.safetensors": b"dummy_weights",
            "tokenizer.json": b"dummy_tokenizer",
            "config.json": json.dumps({
                "id2label": {str(i): lbl for i, lbl in enumerate(sorted(EXPECTED_46_LABELS))}
            }).encode("utf-8"),
        }
        for name, content in all_files.items():
            if name != missing_file:
                (dir_path / name).write_bytes(content)

        mc = ModelContainer()
        mc.load(dir_path)

        assert mc.is_ready() is False
        assert getattr(mc, "verified", False) is False
        assert getattr(mc, "model_mode", "unavailable") == "unavailable"
        assert mc.verified_model_version is None
        assert mc.model_checksum is None
        assert mc.tokenizer_checksum is None
        with pytest.raises(RuntimeError, match="not loaded, verified, or ready"):
            mc.predict("Where is my order?")


def test_artifact_checksum_mismatch_fails_closed(clean_env):
    """If artifacts exist but checksums do not match pinned release manifest, fail closed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        (dir_path / "model.safetensors").write_bytes(b"tampered_weights")
        (dir_path / "tokenizer.json").write_bytes(b"tampered_tokenizer")
        (dir_path / "config.json").write_text(json.dumps({
            "id2label": {str(i): lbl for i, lbl in enumerate(sorted(EXPECTED_46_LABELS))}
        }), encoding="utf-8")

        mc = ModelContainer()
        mc.load(dir_path)

        assert mc.is_ready() is False
        assert getattr(mc, "verified", False) is False
        assert getattr(mc, "model_mode", "unavailable") == "unavailable"
        assert mc.model_checksum is None
        assert mc.tokenizer_checksum is None
        assert mc.verified_model_version is None
        with pytest.raises(RuntimeError, match="not loaded, verified, or ready"):
            mc.predict("Where is my order?")


def test_explicit_demo_fallback_independent_identity_and_no_fabricated_hashes(monkeypatch):
    """When dev fallback is explicitly enabled, it must have independent identity,
    no fabricated artifact hashes, cannot be verified, and cannot certify trained readiness."""
    monkeypatch.setenv("SUPPORTIQ_DEV_FALLBACK_MODEL", "true")
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        mc = ModelContainer()
        mc.load(dir_path)

        assert mc._is_dev_fallback is True
        assert getattr(mc, "model_mode", None) == "heuristic_demo"
        assert getattr(mc, "verified", True) is False
        # Must NOT masquerade as verified trained release version
        assert mc.verified_model_version is None
        assert mc.model_version != EXPECTED_MANIFEST["model_version"]
        # Must NOT fabricate artifact hashes
        assert mc.model_checksum is None
        assert mc.tokenizer_checksum is None
        # Cannot certify trained readiness
        assert mc.is_trained_ready() is False


def test_explicit_demo_fallback_predict_never_returns_calibrated_probability(monkeypatch):
    """Fallback predict must never return calibrated_probability or fabricated hashes."""
    monkeypatch.setenv("SUPPORTIQ_DEV_FALLBACK_MODEL", "true")
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        mc = ModelContainer()
        mc.load(dir_path)

        res = mc.predict("Where is my order?", calibrated=True)
        assert res["score_kind"] != "calibrated_probability"
        assert res["model_checksum"] is None
        assert res["tokenizer_checksum"] is None
        assert res["model_mode"] == "heuristic_demo"
        assert res["verified"] is False
        assert res["model_version"] != EXPECTED_MANIFEST["model_version"]


def test_trained_model_provenance_success():
    """Mock a verified trained model and check provenance fields."""
    mc = ModelContainer()
    mc.model = MagicMock()
    mc.tokenizer = MagicMock()
    mc.id2label = {i: label for i, label in enumerate(sorted(EXPECTED_46_LABELS))}
    mc.verified_model_version = EXPECTED_MANIFEST["model_version"]
    mc.model_version = EXPECTED_MANIFEST["model_version"]
    mc.model_checksum = EXPECTED_MANIFEST["weights_sha256"]
    mc.tokenizer_checksum = EXPECTED_MANIFEST["tokenizer_sha256"]
    mc.model_mode = "trained"
    mc.verified = True
    mc._is_dev_fallback = False

    assert mc.is_ready() is True
    assert mc.is_trained_ready() is True
    assert mc.verified is True
    assert mc.model_mode == "trained"


def test_api_ready_and_predict_provenance(monkeypatch):
    """FastAPI endpoints must expose additive provenance metadata."""
    client = TestClient(app)

    # In mock trained mode:
    container.model = MagicMock()
    container.tokenizer = MagicMock()
    container.id2label = {i: label for i, label in enumerate(sorted(EXPECTED_46_LABELS))}
    container.verified_model_version = "v1.0.0"
    container.model_version = "v1.0.0"
    container.model_checksum = EXPECTED_MANIFEST["weights_sha256"]
    container.tokenizer_checksum = EXPECTED_MANIFEST["tokenizer_sha256"]
    container.model_mode = "trained"
    container.verified = True
    container._is_dev_fallback = False

    res = client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["ready"] is True
    assert data["model_version"] == "v1.0.0"
    assert data.get("model_mode") == "trained"
    assert data.get("verified") is True
    assert data.get("trained_ready") is True

    # Reject mismatched expected_model_version:
    res = client.post("/predict", json={
        "text": "Where is my order?",
        "expected_model_version": "v9.9.9"
    })
    assert res.status_code == 400

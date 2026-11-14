from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.ai_service import main


FIT2_MODEL_DIR = "artifacts/models/candidates/reconstructed-fit2-supcon-20261113"
FIT2_MANIFEST_PATH = f"{FIT2_MODEL_DIR}/calibration_manifest.json"
FIT2_WEIGHTS_SHA256 = "f695b1fe514aba81aafc968823047d496b03474a0b47199c65eaac6bd93c6dfa"
FIT2_CALIBRATION_SHA256 = "782c88db3fcd80615c3dceabbdb96ea2be7aa769119201f94229535becc7ae39"


def test_ai_settings_defaults_remain_unpinned():
    settings = main.AiSettings(_env_file=None)
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.supportiq_model_dir is None
    assert settings.supportiq_calibration_manifest_path is None
    assert settings.supportiq_max_live_llm_requests is None
    assert settings.supportiq_llm_max_attempts is None


def test_allowlisted_transport_hard_caps_live_requests(monkeypatch):
    transport = main.AllowListedTransport(max_requests=2)
    sent_urls = []

    def fake_handle(request):
        sent_urls.append(str(request.url))
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(transport.transport, "handle_request", fake_handle)
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/x:generateContent")

    assert transport.handle_request(req).status_code == 200
    assert transport.handle_request(req).status_code == 200
    assert transport.request_count == 2

    with pytest.raises(httpx.RequestError, match="Live LLM budget exhausted"):
        transport.handle_request(req)

    assert len(sent_urls) == 2
    assert transport.request_count == 2


@pytest.mark.real_model
def test_gateway_loads_original_fit2_with_local_override(monkeypatch):
    monkeypatch.setattr(
        "apps.core_backend.retrieval.adapter.RetrievalAdapter",
        lambda **kwargs: SimpleNamespace(index=object(), eligible_versions=[]),
    )
    settings = main.AiSettings(
        _env_file=None,
        supportiq_enable_llm=False,
        supportiq_model_dir=FIT2_MODEL_DIR,
        supportiq_calibration_manifest_path=FIT2_MANIFEST_PATH,
        supportiq_max_live_llm_requests=2,
        supportiq_llm_max_attempts=1,
    )
    monkeypatch.setattr(main, "AiSettings", lambda: settings)

    with TestClient(main.create_app()) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        ready_json = ready.json()
        assert ready_json["model_version"] == "fit2-supcon-energy-boundary-v1"
        assert ready_json["model_checksum"] == FIT2_WEIGHTS_SHA256
        assert ready_json["calibration_checksum"] == FIT2_CALIBRATION_SHA256
        assert ready_json["model_verified"] is True
        assert ready_json["live_llm_requests_made"] == 0
        assert ready_json["max_live_llm_requests"] == 2

        versions = client.get("/v1/asset-versions").json()["versions"]
        assert versions["model_version"] == "fit2-supcon-energy-boundary-v1"
        assert versions["model_checksum"] == FIT2_WEIGHTS_SHA256
        assert versions["calibration_checksum"] == FIT2_CALIBRATION_SHA256
        assert Path(FIT2_MANIFEST_PATH).exists()

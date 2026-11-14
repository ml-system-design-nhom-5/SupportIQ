from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr


def test_gateway_versions_identify_actual_prompt_and_engine_source(monkeypatch):
    from apps.ai_service import main
    from apps.core_backend.llm.gemini import PROMPT_VERSION
    model = SimpleNamespace(load=lambda: None, is_ready=lambda: True, model_checksum='weights',
                            verified_model_version='test', model_mode='trained', verified=True)
    monkeypatch.setattr('apps.ml_inference.app.ModelContainer', lambda: model)
    monkeypatch.setattr('apps.core_backend.retrieval.adapter.RetrievalAdapter',
                        lambda **kwargs: SimpleNamespace(index=object(), eligible_versions=[]))
    monkeypatch.setattr(main, 'AiSettings', lambda: SimpleNamespace(supportiq_enable_llm=False,
                        gemini_api_key=SecretStr(''), gemini_model='gemini-3.1-flash-lite'))
    with TestClient(main.create_app()) as client:
        response = client.get('/v1/asset-versions')
        assert response.status_code == 200
        versions = response.json()['versions']
    assert versions['prompt_version'] == PROMPT_VERSION
    assert versions['engine_version'].startswith('sha256:')

    # A routing implementation change must change the release identity, even
    # when weights, policy JSON and KB documents are identical.
    original_read = main.Path.read_bytes
    def changed_engine(path):
        content = original_read(path)
        return content + b'\n# changed implementation\n' if path.name == 'engine.py' else content
    monkeypatch.setattr(main.Path, 'read_bytes', changed_engine)
    with TestClient(main.create_app()) as client:
        changed = client.get('/v1/asset-versions').json()['versions']
    assert changed['release_id'] != versions['release_id']

"""Offline provider fixtures and test profile configuration.
Ensures tests never call external network services unless explicitly opted-in via --run-live.
"""
import json
import httpx
import pytest

from apps.core_backend.llm.gemini import GeminiDraftClient


def pytest_configure(config):
    basetemp = config.getoption("basetemp", default=None)
    if basetemp:
        from pathlib import Path
        Path(basetemp).parent.mkdir(parents=True, exist_ok=True)


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests requiring valid external credentials and network egress",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="requires --run-live option and valid credentials")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture
def fake_llm():
    def handler(request):
        return httpx.Response(200, json={"modelVersion": "gemini-2.5-flash", "candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "answerable": True, "answer": "Standard Return Policy: Return within 30 days. [S1]",
                "citations": ["S1"]})}]}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        yield GeminiDraftClient(api_key="offline-test-key", model="gemini-2.5-flash", http_client=transport)

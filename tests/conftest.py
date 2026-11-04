"""Offline provider fixtures: tests never need credentials or a paid API call."""
import json

import httpx
import pytest

from apps.core_backend.llm.gemini import GeminiDraftClient


@pytest.fixture
def fake_llm():
    def handler(request):
        return httpx.Response(200, json={"modelVersion": "gemini-2.5-flash", "candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "answerable": True, "answer": "Standard Return Policy: Return within 30 days. [S1]",
                "citations": ["S1"]})}]}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        yield GeminiDraftClient(api_key="offline-test-key", model="gemini-2.5-flash", http_client=transport)

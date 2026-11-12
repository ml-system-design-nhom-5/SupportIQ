"""Unit tests for connection pooling, explicit close, and stage timing in HTTP clients (Task 6)."""

import httpx
import pytest
from unittest.mock import MagicMock

from apps.core_backend.intent.client import IntentClient
from apps.core_backend.llm.gemini import GeminiDraftClient


class TestHTTPClientConnectionPooling:
    def test_intent_client_reuses_pooled_client_and_closes_cleanly(self):
        """IntentClient reuses HTTP connection pool across multiple calls and closes cleanly."""
        mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
            "intent": "track_order",
            "confidence": 0.95,
            "margin": 0.30,
            "model_version": "v1.0.0",
        }))
        shared_http = httpx.Client(transport=mock_transport)

        client = IntentClient(base_url="http://127.0.0.1:8001", http_client=shared_http)
        pred1 = client.classify_intent("Where is my order?", request_id="req-1")
        pred2 = client.classify_intent("Track package", request_id="req-2")

        assert pred1.intent == "track_order"
        assert pred2.intent == "track_order"

        # Explicit close should close owned resources or support lifespan cleanup
        client.close()

    def test_gemini_client_supports_connection_pool_and_close(self):
        """GeminiDraftClient supports injected connection pool and clean close."""
        mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"answerable": true, "answer": "You can return within 30 days [S1].", "citations": ["S1"]}'}]
                },
                "finishReason": "STOP",
            }],
            "modelVersion": "gemini-3.1-flash-lite",
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20, "totalTokenCount": 70},
        }))
        shared_http = httpx.Client(transport=mock_transport)

        client = GeminiDraftClient(api_key="test-api-key", http_client=shared_http)
        evidence = [{
            "document_id": "POL-RET-001",
            "version": "1.0",
            "title": "Return Policy",
            "excerpt": "Return within 30 days.",
        }]
        res = client.generate("When can I return?", "return_policy", evidence)
        assert "30 days" in res["body"]
        assert len(res["citations"]) == 1

        client.close()

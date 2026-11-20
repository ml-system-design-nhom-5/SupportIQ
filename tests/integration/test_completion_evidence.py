"""Integration tests for verified evidence grounding, citation tracing, and sanitized export (Task 5)."""

import hashlib
import json
from unittest.mock import MagicMock
import pytest

from apps.core_backend.llm.gemini import build_grounded_sources, GeminiDraftClient
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction


class TestEndToEndEvidenceGrounding:
    def test_runner_constructs_unified_sources_with_order_facts(self, tmp_path):
        """PipelineRunner passes unified S1..Sn sources with policy and verified order facts to LLM client."""
        store = PersistentStore(db_path=str(tmp_path / "orch_grounding.sqlite3"))

        mock_intent = MagicMock()
        mock_intent.classify_intent.return_value = IntentPrediction(
            intent="return_product",
            confidence=0.95,
            margin=0.40,
            model_version="v1.0",
        )

        mock_commerce = MagicMock()
        mock_commerce.lookup_order.return_value = {
            "authorized": True,
            "order": {
                "order_id": "ORD-1001",
                "order_status": "Shipping",
                "carrier": "GHN Express",
                "can_cancel": False,
            },
        }

        mock_retrieval = MagicMock()
        mock_retrieval.retrieve.return_value = {
            "status": "success",
            "evidence": [
                {
                    "source_type": "policy",
                    "document_id": "POL-RET-001",
                    "title": "Return Policy",
                    "version": "2.0",
                    "excerpt": "Return items within 30 days.",
                    "content_hash": hashlib.sha256("Return items within 30 days.".encode("utf-8")).hexdigest(),
                }
            ],
        }

        captured_sources = []
        class SpyLLMClient:
            configured = True
            def generate(self, question, intent, evidence, business_context=None):
                sources = build_grounded_sources(evidence, business_context, provenance={"intent": intent})
                captured_sources.extend(sources)
                return {
                    "body": "Items may be returned within 30 days [S1]. Your order is currently Shipping [S2].",
                    "citations": [
                        {"source_id": "S1", "document_id": "POL-RET-001", "version": "2.0"},
                        {"source_id": "S2", "document_id": "ORD-1001", "version": "facts"},
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 40},
                }

        runner = PipelineRunner(
            intent_client=mock_intent,
            commerce_adapter=mock_commerce,
            retrieval_adapter=mock_retrieval,
            store=store,
            llm_client=SpyLLMClient(),
        )

        ctx = RoutingContext(
            ticket_customer_id="cust-1",
            extracted_slots={"order_id": "ORD-1001"},
            is_personal_lookup=True,
        )
        res = runner.run("Can I return order ORD-1001?", context=ctx, run_id="run-ground-1")

        assert res["action"] == "retrieve_draft"
        assert res["draft_body"] is not None
        assert len(captured_sources) == 2
        assert captured_sources[0]["source_id"] == "S1"
        assert captured_sources[0]["source_type"] == "policy"
        assert captured_sources[1]["source_id"] == "S2"
        assert captured_sources[1]["source_type"] == "order_facts"
        assert captured_sources[1]["document_id"] == "ORD-1001"

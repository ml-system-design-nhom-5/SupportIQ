"""Unit tests for grounded sources, fact isolation, and claim relevance (Task 5)."""

import hashlib
import json
import pytest

from apps.core_backend.llm.gemini import build_grounded_sources, GeminiDraftClient, LLMError
from pipeline.evaluation.assess_system import evaluate_claim_annotations


class TestGroundedSourcesBuilder:
    def test_build_grounded_sources_unifies_policy_and_order_facts(self):
        """build_grounded_sources assigns sequential S1..Sn IDs to policy and order facts with SHA-256."""
        policy_evidence = [
            {
                "document_id": "POL-RET-001",
                "version": "2.0",
                "title": "Return Policy",
                "excerpt": "Return items within 30 days.",
                "content_hash": hashlib.sha256("Return items within 30 days.".encode("utf-8")).hexdigest(),
            }
        ]
        authorized_facts = {
            "order_id": "ORD-1001",
            "order_status": "Shipping",
            "carrier": "GHN Express",
            "estimated_delivery": "Within 2 days",
            "customer_phone": "0912345678",  # Should be filtered out
            "customer_email": "test@example.com",  # Should be filtered out
            "secret_token": "secret12345678901234567890",  # Should be filtered out
        }
        provenance = {"caller_role": "agent"}

        sources = build_grounded_sources(policy_evidence, authorized_facts, provenance)

        assert len(sources) == 2
        # First source: policy
        s1 = sources[0]
        assert s1["source_id"] == "S1"
        assert s1["source_type"] == "policy"
        assert s1["document_id"] == "POL-RET-001"
        assert s1["version"] == "2.0"
        assert "Return items within 30 days" in s1["excerpt"]
        assert len(s1["sha256"]) == 64

        # Second source: order facts
        s2 = sources[1]
        assert s2["source_id"] == "S2"
        assert s2["source_type"] == "order_facts"
        assert s2["document_id"] == "ORD-1001"
        assert "Shipping" in s2["excerpt"]
        assert "GHN Express" in s2["excerpt"]
        # Ensure private fields are NOT leaked into excerpt
        assert "0912345678" not in s2["excerpt"]
        assert "test@example.com" not in s2["excerpt"]
        assert "secret12345678901234567890" not in s2["excerpt"]
        assert len(s2["sha256"]) == 64

    def test_build_grounded_sources_handles_none_order_facts(self):
        """When authorized_facts is None, only policy sources S1..Sn are built."""
        policy_evidence = [
            {
                "document_id": "POL-SHIP-001",
                "version": "1.0",
                "title": "Shipping Schedule",
                "excerpt": "Standard shipping is $5.00.",
                "content_hash": hashlib.sha256("Standard shipping is $5.00.".encode("utf-8")).hexdigest(),
            }
        ]
        sources = build_grounded_sources(policy_evidence, None, provenance={})
        assert len(sources) == 1
        assert sources[0]["source_id"] == "S1"
        assert sources[0]["source_type"] == "policy"


class TestRelevanceScoringAndGroundingVerification:
    def test_relevance_categories_computed_distinct_from_grounding(self):
        """evaluate_claim_annotations tracks draft relevance (fully_answers/partial/off_topic) distinctly."""
        draft_text = "You can return your item within 30 days [S1]. Your order is currently shipping [S2]."
        draft_hash = hashlib.sha256(draft_text.encode("utf-8")).hexdigest()

        annotations = [
            {
                "reviewer": "expert_reviewer_1",
                "reviewer_type": "human",
                "case_id": "case-01",
                "draft_sha256": draft_hash,
                "relevance": "fully_answers",
                "claims": [
                    {
                        "claim_id": "c1",
                        "claim_text": "Return within 30 days",
                        "citation": "S1",
                        "verdict": "supported",
                    },
                    {
                        "claim_id": "c2",
                        "claim_text": "Order is shipping",
                        "citation": "S2",
                        "verdict": "supported",
                    },
                ],
            }
        ]
        expected_hashes = {"case-01": draft_hash}
        res = evaluate_claim_annotations(annotations, expected_hashes)

        assert res["status"] == "pass"
        assert res["supported_claims_ratio"] == 1.0
        assert res.get("relevance_counts", {}).get("fully_answers") == 1

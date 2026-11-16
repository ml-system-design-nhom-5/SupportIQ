"""Claim relevance is graded apart from grounding (moved from the Gemini tests of `main`)."""

import hashlib

from tests.annotation_fixtures import reviewed_annotations

from pipeline.evaluation.assess_system import evaluate_claim_annotations


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
        res = evaluate_claim_annotations(reviewed_annotations(annotations), expected_hashes)

        assert res["status"] == "pass"
        assert res["supported_claims_ratio"] == 1.0
        assert res.get("relevance_counts", {}).get("fully_answers") == 1

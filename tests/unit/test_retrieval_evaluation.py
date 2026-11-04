import pytest
from pipeline.evaluation.evaluate_retrieval import score_retrieval

def test_score_retrieval_perfect_match():
    cases = [
        {"id": "q1", "is_answerable": True, "gold_doc_ids": ["DOC-1:1.0", "DOC-2:1.0"]},
    ]
    retrieved = [
        {"id": "q1", "documents": [
            {"doc_id": "DOC-1", "version": "1.0"},
            {"doc_id": "DOC-2", "version": "1.0"},
            {"doc_id": "DOC-3", "version": "1.0"}
        ]}
    ]
    metrics = score_retrieval(cases, retrieved)
    assert metrics["recall_at_3"] == 1.0
    assert metrics["hit_at_3"] == 1.0
    assert metrics["false_answer_rate"] == "N/A"


def test_score_retrieval_rejects_wrong_version():
    """P2: Returning wrong version of gold document yields 0 recall."""
    cases = [
        {"id": "q1", "is_answerable": True, "gold_doc_ids": ["DOC-1:2.0"]},
    ]
    retrieved = [
        # Returned version 1.0 instead of gold version 2.0
        {"id": "q1", "documents": [{"doc_id": "DOC-1", "version": "1.0"}]}
    ]
    metrics = score_retrieval(cases, retrieved)
    assert metrics["recall_at_3"] == 0.0
    assert metrics["hit_at_3"] == 0.0


def test_score_retrieval_raises_on_missing_case():
    """P2: Missing prediction for a test case raises ValueError."""
    cases = [
        {"id": "q1", "is_answerable": True, "gold_doc_ids": ["DOC-1:1.0"]},
        {"id": "q2", "is_answerable": True, "gold_doc_ids": ["DOC-2:1.0"]},
    ]
    retrieved = [
        {"id": "q1", "documents": [{"doc_id": "DOC-1", "version": "1.0"}]}
    ]
    with pytest.raises(ValueError, match="Missing prediction result"):
        score_retrieval(cases, retrieved)

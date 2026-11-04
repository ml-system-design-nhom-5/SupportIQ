import pytest
from pipeline.evaluation.evaluate_retrieval import score_retrieval

def test_score_retrieval_perfect_match():
    cases = [
        {"id": "q1", "is_answerable": True, "gold_doc_ids": ["DOC-1", "DOC-2"]},
    ]
    retrieved = [
        {"id": "q1", "documents": [{"doc_id": "DOC-1"}, {"doc_id": "DOC-2"}, {"doc_id": "DOC-3"}]}
    ]
    metrics = score_retrieval(cases, retrieved)
    assert metrics["recall_at_3"] == 1.0
    assert metrics["hit_at_3"] == 1.0
    assert metrics["false_answer_rate"] == "N/A"


def test_score_retrieval_unanswerable_rejection():
    cases = [
        {"id": "q_ood", "is_answerable": False, "gold_doc_ids": []},
    ]
    # Correctly returned empty documents
    retrieved = [
        {"id": "q_ood", "documents": []}
    ]
    metrics = score_retrieval(cases, retrieved)
    assert metrics["unanswerable_count"] == 1
    assert metrics["false_answer_rate"] == 0.0

    # Incorrectly returned documents for unanswerable query -> false answer
    bad_retrieved = [
        {"id": "q_ood", "documents": [{"doc_id": "DOC-1"}]}
    ]
    bad_metrics = score_retrieval(cases, bad_retrieved)
    assert bad_metrics["false_answer_rate"] == 1.0

import uuid
import pytest
from src.modules.llm.validator import validate_llm_output, InvalidLlmOutputError
from src.modules.llm.client import compute_attempt_timeout

def test_validate_llm_output_rejects_foreign_citations_and_urls():
    run_id = uuid.uuid4()
    allowed = {"cit_kb_1", "cit_ord_1"}

    # Valid output passes
    valid = validate_llm_output(
        '{"body": "Orders ship within 2 business days [cit_kb_1].", "citation_ids": ["cit_kb_1"]}',
        allowed_citation_ids=allowed,
        run_id=run_id,
    )
    assert valid.citation_ids == ["cit_kb_1"]

    # Hallucinated citation ID fails
    with pytest.raises(InvalidLlmOutputError):
        validate_llm_output(
            '{"body": "Refund approved.", "citation_ids": ["cit_fake_99"]}',
            allowed_citation_ids=allowed,
            run_id=run_id,
        )

    # Embedded external URL fails
    with pytest.raises(InvalidLlmOutputError):
        validate_llm_output(
            '{"body": "Visit https://evil.example.com to claim refund.", "citation_ids": ["cit_kb_1"]}',
            allowed_citation_ids=allowed,
            run_id=run_id,
        )

def test_compute_attempt_timeout_respects_8s_cap_and_remaining_budget():
    assert compute_attempt_timeout(remaining_budget_sec=10.5) == 8.0
    assert compute_attempt_timeout(remaining_budget_sec=4.2) == 4.2

"""Unit tests verifying fixture factories produce valid contracts and checksums."""

from pathlib import Path
from tests.fixtures.factories import make_system_case, write_suite_fixture, make_human_annotation


def test_make_system_case_defaults_valid():
    case = make_system_case(case_id="case-001")
    assert case.id == "case-001"
    assert case.expected.actions == ["retrieve_draft"]
    assert case.expected.draft_expected is True


def test_make_system_case_must_escalate_consistent():
    case = make_system_case(case_id="case-esc-001", must_escalate=True)
    assert case.id == "case-esc-001"
    assert case.expected.must_escalate is True
    assert case.expected.actions == ["escalate"]
    assert case.expected.draft_expected is False


def test_write_suite_fixture_produces_real_hashes(tmp_path):
    cases = [{"id": "c1", "primary_slice": "supported", "text": "Hi", "context": {"ticket_customer_id": "cust-1"}, "expected": {"actions": ["escalate"]}}]
    kb = [{"doc_id": "KB-1", "document_id": "KB-1", "version": "1.0", "status": "approved", "approved_by": "lead", "approved_at": "2026-01-01T00:00:00Z", "valid_from": "2026-01-01T00:00:00Z", "allowed_roles": ["agent"]}]
    suite = write_suite_fixture(tmp_path, cases, kb)
    assert suite["manifest_file"].exists()
    assert suite["cases_file"].exists()
    assert suite["kb_file"].exists()

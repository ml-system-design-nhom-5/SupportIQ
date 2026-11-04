from datetime import datetime, timezone
import pytest
from apps.core_backend.retrieval.importer import (
    PolicyDocument,
    PolicyMetadata,
    PolicyVersion,
    import_policies,
    eligible_versions,
    detect_rule_conflicts,
)

def test_metadata_importer_valid_approved_passes(tmp_path):
    policies_data = [
        {
            "doc_id": "POL-TEST-001",
            "category": "return_refund",
            "title": "Standard Return",
            "content": "You can return items within 30 days.",
            "version": "1.0",
            "is_active": True,
            "tags": ["return"]
        }
    ]
    metadata_data = {
        "POL-TEST-001:1.0": {
            "status": "approved",
            "approved_by": "qa_lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer", "staff"],
            "policy_key": "return_window",
            "rule_assertions": [{"key": "return_window", "value": 30, "unit": "days", "condition": "all"}]
        }
    }
    report = import_policies(policies_data, metadata_data)
    assert report["imported_count"] == 1
    assert len(report["eligible"]) == 1
    assert report["quarantined_count"] == 0

    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    eligible = eligible_versions(report["eligible"], role="customer", as_of=now)
    assert len(eligible) == 1
    assert eligible[0].doc_id == "POL-TEST-001"


def test_metadata_importer_excludes_inactive_or_expired():
    policies_data = [
        {
            "doc_id": "POL-INACT-001",
            "category": "return_refund",
            "title": "Inactive policy",
            "content": "Old rules",
            "version": "1.0",
            "is_active": False,
            "tags": []
        },
        {
            "doc_id": "POL-EXP-002",
            "category": "return_refund",
            "title": "Expired policy",
            "content": "Expired rules",
            "version": "1.0",
            "is_active": True,
            "tags": []
        }
    ]
    metadata_data = {
        "POL-INACT-001:1.0": {
            "status": "approved",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["customer"]
        },
        "POL-EXP-002:1.0": {
            "status": "approved",
            "valid_from": "2025-01-01T00:00:00Z",
            "valid_to": "2025-12-31T23:59:59Z",
            "allowed_roles": ["customer"]
        }
    }
    report = import_policies(policies_data, metadata_data)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    eligible = eligible_versions(report["eligible"], role="customer", as_of=now)
    assert len(eligible) == 0


def test_conflict_detection_overlapping_conditions():
    """Rules with same key and overlapping conditions but conflicting values must raise conflict."""
    rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "tiki_trading"}},
        {"key": "return_window", "value": 7, "condition": {"seller": "marketplace"}},
    ]
    # Different sellers -> not a conflict
    assert detect_rule_conflicts(rules) is False

    conflicting_rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "tiki_trading"}},
        {"key": "return_window", "value": 14, "condition": {"seller": "tiki_trading"}},
    ]
    # Same seller, same key, different values -> CONFLICT!
    assert detect_rule_conflicts(conflicting_rules) is True

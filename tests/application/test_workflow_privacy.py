"""Distinct workflow and privacy tests exercising egress protection and guardrails."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.backend.tickets.privacy import pseudonymize, restore, luhn_checksum_valid
from apps.backend.tickets.service import allowed_actions, order_context


def test_egress_allowlist_order_context():
    """Verify that order_context allowlists only safe summary fields and excludes PII/identifiers."""
    fake_order = SimpleNamespace(
        payload={
            "order_id": "ORD-1001",
            "customer_name": "Nguyen Van A",
            "phone": "+84901234567",
            "shipping_address": "123 Le Loi Street, Ben Nghe, District 1, HCMC",
            "credit_card": "4532-0151-1283-0366",
            "transaction_id": "TXN-999888",
            "order_status": "shipped",
            "order_total": {"amount_minor": 1402000, "currency": "VND"},
            "shipping_cost": {"amount_minor": 30000, "currency": "VND"},
            "shipment": {
                "tracking_code": "GIAO12345678",
                "shipment_status": "in_transit",
                "courier": "FastShip",
            },
            "refund": {
                "refund_status": "under_review",
                "refund_amount": {"amount_minor": 500000, "currency": "VND"},
            },
        }
    )

    context = order_context(fake_order)

    # Allowed fields MUST be present
    assert context["order_status"] == "shipped"
    assert context["order_total"] == {"amount_minor": 1402000, "currency": "VND"}
    assert context["shipping_cost"] == {"amount_minor": 30000, "currency": "VND"}
    assert context["shipment_status"] == "in_transit"
    assert context["refund_status"] == "under_review"
    assert context["refund_amount"] == {"amount_minor": 500000, "currency": "VND"}

    # Prohibited PII and raw transaction identifiers MUST NOT leak
    forbidden_keys = {
        "customer_name",
        "phone",
        "shipping_address",
        "credit_card",
        "transaction_id",
        "tracking_code",
        "courier",
    }
    assert not (forbidden_keys & context.keys())


def test_pseudonymization_payload_helper():
    """Helper coverage only; this test does not invoke backend jobs or an HTTP transport."""
    known_customer_data = {
        "NAME": ["Tran Van Bao"],
        "PHONE": ["+84912345678"],
        "ORDER_ID": ["ORD-5544"],
        "TRACKING_ID": ["TRK-987654"],
    }

    raw_message = (
        "Hello, I am Tran Van Bao. I ordered ORD-5544. "
        "My phone is +84912345678 and shipping address is 45 Nguyen Thi Minh Khai Street, District 3. "
        "I paid using Visa 4532015112830366 and email is tran.bao@example.com. "
        "I also typed literal text [NAME_1] in my message."
    )

    # Explicit offline unit opt-out (no external transport; validates known/regex masking without spaCy)
    pseudonymized, mapping = pseudonymize(raw_message, known_customer_data, require_ner=False)

    # Transport egress payload simulation
    egress_payload = {
        "message": pseudonymized,
        "as_of": "2026-11-12T00:00:00Z",
    }

    # Verify no raw PII appears in the egress message
    assert "Tran Van Bao" not in egress_payload["message"]
    assert "+84912345678" not in egress_payload["message"]
    assert "ORD-5544" not in egress_payload["message"]
    assert "4532015112830366" not in egress_payload["message"]
    assert "tran.bao@example.com" not in egress_payload["message"]
    assert "Nguyen Thi Minh Khai Street" not in egress_payload["message"]

    # Verify expected placeholders are present
    assert "[NAME_1]" in egress_payload["message"]
    assert "[PHONE_1]" in egress_payload["message"]
    assert "[ORDER_ID_1]" in egress_payload["message"]
    assert "[CARD_1]" in egress_payload["message"]
    assert "[EMAIL_1]" in egress_payload["message"]
    assert "[ADDRESS_1]" in egress_payload["message"]

    # Customer-authored literal placeholder is protected and restored
    restored = restore(pseudonymized, mapping)
    assert restored == raw_message


def test_pseudonymization_recall_limitations_on_unstructured_slang(monkeypatch):
    """Document recall limitation: highly informal non-standard vernacular addresses without street markers.
    
    Standard regex/NER may miss obscure colloquial Vietnamese directions lacking standard administrative keywords.
    """
    monkeypatch.setattr("apps.backend.tickets.privacy._get_spacy_nlp", lambda: None)
    known = {}
    colloquial_input = "Giao cho tui o sau nha ba bay cho cau sat cu"
    # Explicit offline opt-out (require_ner=False) for regex recall-limit check
    pseudonymized, mapping = pseudonymize(colloquial_input, known, require_ner=False)
    # Because there are no street keywords or standard NER entities, it passes as regular text.
    # We assert this behavior to explicitly record the documented recall boundary.
    assert "[ADDRESS_1]" not in pseudonymized


def test_retry_policy_enforcement_aligns_with_spec():
    """Verify that allowed_actions only permits retry for transient failures, not draft_ready."""
    staff = SimpleNamespace(role="staff")
    ticket_open = SimpleNamespace(status="open", is_authority_required=False)

    # 1. Ready draft: retry_suggestion MUST NOT be offered (spec: no gratuitous regenerate feature)
    ready_suggestion = SimpleNamespace(
        payload={
            "analysis_status": "ready",
            "draft_status": "draft_ready",
            "reason_codes": [],
        }
    )
    actions = allowed_actions(ticket_open, staff, ready_suggestion)
    assert "retry_suggestion" not in actions
    assert "correct_intent" in actions
    assert "send_reply" in actions

    # 2. Transient failure (unavailable / llm_unavailable): retry_suggestion MUST be offered
    unavailable_suggestion = SimpleNamespace(
        payload={
            "analysis_status": "ready",
            "draft_status": "llm_unavailable",
            "reason_codes": ["llm_timeout"],
        }
    )
    actions = allowed_actions(ticket_open, staff, unavailable_suggestion)
    assert "retry_suggestion" in actions

    # 3. Permanent privacy failure (pseudonymization_failed): retry_suggestion NOT offered
    privacy_failed_suggestion = SimpleNamespace(
        payload={
            "analysis_status": "unavailable",
            "draft_status": "unavailable",
            "reason_codes": ["pseudonymization_failed"],
        }
    )
    actions = allowed_actions(ticket_open, staff, privacy_failed_suggestion)
    assert "retry_suggestion" not in actions


def test_authority_case_workflow_restrictions():
    """Verify authority case action restrictions: staff cannot send_reply; manager can."""
    ticket_authority = SimpleNamespace(status="open", is_authority_required=True)
    ready_suggestion = SimpleNamespace(
        payload={
            "analysis_status": "ready",
            "draft_status": "draft_ready",
            "reason_codes": [],
        }
    )

    staff = SimpleNamespace(role="staff")
    manager = SimpleNamespace(role="manager")

    staff_actions = allowed_actions(ticket_authority, staff, ready_suggestion)
    assert "send_reply" not in staff_actions
    assert "submit_reply_proposal" in staff_actions
    assert "escalate" in staff_actions

    manager_actions = allowed_actions(ticket_authority, manager, ready_suggestion)
    assert "send_reply" in manager_actions

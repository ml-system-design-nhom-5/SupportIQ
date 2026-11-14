from types import SimpleNamespace

from apps.backend.tickets.service import allowed_actions


def test_ready_draft_does_not_offer_transient_failure_retry():
    ticket = SimpleNamespace(status="open", is_authority_required=False)
    actor = SimpleNamespace(role="staff")
    suggestion = SimpleNamespace(payload={"analysis_status": "ready", "draft_status": "draft_ready"})
    # Stakeholder decision: regeneration is separate from retrying a failed request.
    assert "retry_suggestion" not in allowed_actions(ticket, actor, suggestion)


def test_pending_draft_cannot_be_retried():
    ticket = SimpleNamespace(status="open", is_authority_required=False)
    actor = SimpleNamespace(role="staff")
    suggestion = SimpleNamespace(payload={"analysis_status": "ready", "draft_status": "pending"})
    assert "retry_suggestion" not in allowed_actions(ticket, actor, suggestion)

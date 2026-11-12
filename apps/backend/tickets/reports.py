from collections import Counter
from sqlalchemy import select

from apps.backend.platform.models import AuditEntry, Suggestion, Ticket


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    return round(ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower), 1)


def report(session, start_at, end_at):
    tickets = session.scalars(select(Ticket)).all()
    suggestions = session.scalars(select(Suggestion).where(Suggestion.completed_at >= start_at, Suggestion.completed_at < end_at)).all()
    events = session.scalars(select(AuditEntry).where(AuditEntry.occurred_at >= start_at, AuditEntry.occurred_at < end_at)).all()
    decisions = Counter(event.data["decision"] for event in events if event.event_type == "decision.recorded")
    total = sum(decisions.values())
    escalations = Counter(reason for event in events if event.event_type == "ticket.escalated" for reason in event.data["staff_reason_codes"])
    outcomes = Counter(suggestion.payload["draft_status"] for suggestion in suggestions if suggestion.payload["draft_status"] != "cancelled")
    errors = sum(suggestion.payload["analysis_status"] == "unavailable" or suggestion.payload["draft_status"] in ("unavailable", "llm_unavailable") for suggestion in suggestions)
    costs = [suggestion.payload["llm_usage"].get("cost_micro_usd", 0) for suggestion in suggestions if suggestion.payload.get("llm_usage")]
    latency = lambda part: {name: percentile([suggestion.payload.get("step_latency_ms", {}).get(part) for suggestion in suggestions if suggestion.payload.get("step_latency_ms", {}).get(part) is not None], q) for name, q in (("p50", .5), ("p95", .95))}
    return {"period": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
            "ticket_counts": {mode: {"created": sum(start_at <= ticket.created_at < end_at and ticket.handling_mode == mode for ticket in tickets), "closed": sum(bool(ticket.closed_at and start_at <= ticket.closed_at < end_at and ticket.handling_mode == mode) for ticket in tickets)} for mode in ("assisted", "manual")},
            "draft_decisions": {decision: {"count": decisions[decision], "share": decisions[decision] / total if total else 0} for decision in ("approve", "edit", "reject")},
            "escalations": dict(escalations), "ai_outcomes": dict(outcomes), "ai_error_rate": errors / len(suggestions) if suggestions else 0,
            "end_to_end_latency_ms": {name: percentile([(suggestion.completed_at - next(ticket.created_at for ticket in tickets if ticket.ticket_id == suggestion.ticket_id)).total_seconds() * 1000 for suggestion in suggestions if suggestion.payload["trigger"] == "ticket_created"], q) for name, q in (("p50", .5), ("p95", .95))},
            "suggestion_latency_ms": {"analysis": latency("analysis"), "draft": latency("draft")},
            "llm_cost_micro_usd": {"total": sum(costs), "average": sum(costs) / len(costs) if costs else None},
            "handling_time_ms": {mode: {"p50": percentile([(ticket.closed_at - ticket.handling_started_at).total_seconds() * 1000 for ticket in tickets if ticket.handling_mode == mode and ticket.closed_at and ticket.handling_started_at and start_at <= ticket.closed_at < end_at], .5)} for mode in ("assisted", "manual")}}

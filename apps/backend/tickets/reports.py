from collections import Counter
from datetime import timezone
from sqlalchemy import and_, or_, select

from apps.backend.platform.database import ensure_utc
from apps.backend.platform.models import AuditEntry, Suggestion, Ticket


def percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    return round(ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (position - lower), 1)


def _utc(dt):
    return ensure_utc(dt).astimezone(timezone.utc) if dt is not None else None


def _llm_cost_summary(suggestions):
    known_total = 0
    known_count = 0
    unknown_count = 0
    for suggestion in suggestions:
        payload = suggestion.payload or {}
        usage = payload.get("llm_usage")
        called_llm = (
            usage is not None
            or bool(payload.get("llm_metadata"))
            or payload.get("draft_status") == "llm_unavailable"
        )
        if not called_llm:
            continue
        cost = usage.get("cost_micro_usd") if isinstance(usage, dict) else None
        incomplete = isinstance(usage, dict) and bool(usage.get("usage_incomplete") or usage.get("cost_incomplete"))
        if isinstance(cost, int) and not isinstance(cost, bool) and cost >= 0 and not incomplete:
            known_total += cost
            known_count += 1
        else:
            unknown_count += 1
    known_average = known_total / known_count if known_count else None
    complete = unknown_count == 0
    return {
        "total": known_total if complete else None,
        "known_total": known_total,
        "average": known_average if complete else None,
        "known_average": known_average,
        "known_count": known_count,
        "unknown_count": unknown_count,
    }


def report(session, start_at, end_at):
    start_utc = _utc(start_at)
    end_utc = _utc(end_at)
    suggestions = session.scalars(select(Suggestion).where(Suggestion.completed_at >= start_utc, Suggestion.completed_at < end_utc)).all()
    events = session.scalars(select(AuditEntry).where(AuditEntry.occurred_at >= start_utc, AuditEntry.occurred_at < end_utc)).all()
    suggestion_ticket_ids = {suggestion.ticket_id for suggestion in suggestions if suggestion.payload.get("trigger") == "ticket_created"}
    ticket_filters = [
        and_(Ticket.created_at >= start_utc, Ticket.created_at < end_utc),
        and_(Ticket.closed_at.is_not(None), Ticket.closed_at >= start_utc, Ticket.closed_at < end_utc),
    ]
    if suggestion_ticket_ids:
        ticket_filters.append(Ticket.ticket_id.in_(suggestion_ticket_ids))
    tickets = session.scalars(select(Ticket).where(or_(*ticket_filters))).all()
    ticket_created_at = {ticket.ticket_id: _utc(ticket.created_at) for ticket in tickets}
    decisions = Counter(event.data["decision"] for event in events if event.event_type == "decision.recorded")
    total = sum(decisions.values())
    escalations = Counter(reason for event in events if event.event_type == "ticket.escalated" for reason in event.data["staff_reason_codes"])
    outcomes = Counter(suggestion.payload["draft_status"] for suggestion in suggestions if suggestion.payload["draft_status"] != "cancelled")
    errors = sum(suggestion.payload["analysis_status"] == "unavailable" or suggestion.payload["draft_status"] in ("unavailable", "llm_unavailable") for suggestion in suggestions)
    latency = lambda part: {name: percentile([suggestion.payload.get("step_latency_ms", {}).get(part) for suggestion in suggestions if suggestion.payload.get("step_latency_ms", {}).get(part) is not None], q) for name, q in (("p50", .5), ("p95", .95))}
    e2e = [
        (_utc(suggestion.completed_at) - ticket_created_at[suggestion.ticket_id]).total_seconds() * 1000
        for suggestion in suggestions
        if suggestion.payload["trigger"] == "ticket_created" and suggestion.ticket_id in ticket_created_at
    ]
    return {"period": {"start_at": ensure_utc(start_at).isoformat(), "end_at": ensure_utc(end_at).isoformat()},
            "ticket_counts": {mode: {"created": sum(ticket.handling_mode == mode and start_utc <= _utc(ticket.created_at) < end_utc for ticket in tickets), "closed": sum(bool(ticket.closed_at and ticket.handling_mode == mode and start_utc <= _utc(ticket.closed_at) < end_utc) for ticket in tickets)} for mode in ("assisted", "manual")},
            "draft_decisions": {decision: {"count": decisions[decision], "share": decisions[decision] / total if total else 0} for decision in ("approve", "edit", "reject")},
            "escalations": dict(escalations), "ai_outcomes": dict(outcomes), "ai_error_rate": errors / len(suggestions) if suggestions else 0,
            "end_to_end_latency_ms": {name: percentile(e2e, q) for name, q in (("p50", .5), ("p95", .95))},
            "suggestion_latency_ms": {"analysis": latency("analysis"), "draft": latency("draft")},
            "llm_cost_micro_usd": _llm_cost_summary(suggestions),
            "handling_time_ms": {mode: {"p50": percentile([(_utc(ticket.closed_at) - _utc(ticket.handling_started_at)).total_seconds() * 1000 for ticket in tickets if ticket.handling_mode == mode and ticket.closed_at and ticket.handling_started_at and start_utc <= _utc(ticket.closed_at) < end_utc], .5)} for mode in ("assisted", "manual")}}

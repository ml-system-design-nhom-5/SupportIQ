from copy import deepcopy
from difflib import SequenceMatcher
import re
import uuid

from sqlalchemy import select, text

from apps.backend.commerce import order_view, require_order
from apps.backend.platform.database import Problem, audit, utcnow, ensure_utc
from apps.backend.platform.models import Account, CustomerMessage, Order, Suggestion, SuggestionJob, Ticket
from apps.backend.platform.observability import metrics
from apps.core_backend.safety import has_authority_request
from .privacy import PLACEHOLDER, pseudonymize, restore

STAFF_REASONS = {"wrong_intent", "wrong_source", "unsupported_claim", "kb_gap", "missing_case_info", "tone_or_clarity", "case_exception", "other"}
INTENTS = {"add_product", "availability", "availability_in_store", "availability_online", "cancel_order", "change_account", "change_order", "close_account", "customer_service", "damaged_delivery", "delivery_issue", "delivery_time", "exchange_product", "exchange_product_in_store", "human_agent", "missing_item", "open_account", "order_history", "pay", "payment_issue", "payment_methods", "product_information", "product_issue", "recover_password", "refund_policy", "refund_status", "remove_product", "request_invoice", "request_refund", "request_right_to_rectification", "return_policy", "return_product", "return_product_in_store", "return_product_online", "sales_period", "shipping_costs", "store_location", "store_opening_hours", "submit_feedback", "submit_product_feedback", "submit_product_idea", "technical_issue", "track_delivery", "track_order", "use_app", "wrong_item"}
SENSITIVE_ACTION_INTENTS = {"cancel_order", "request_refund", "return_product", "payment_issue"}
AUTHORITY_ROLES = ("admin", "manager")


def require_ticket(session, ticket_id, customer_id=None, lock=False):
    query = select(Ticket).where(Ticket.ticket_id == ticket_id)
    if lock:
        query = query.with_for_update()
    ticket = session.scalar(query)
    if not ticket or customer_id is not None and ticket.customer_id != customer_id:
        raise Problem(404, "not-found", "This support request was not found.")
    return ticket


def shop_ticket(session, ticket):
    return {"ticket_id": ticket.ticket_id, "order_id": ticket.order_id,
            "message": session.get(CustomerMessage, ticket.ticket_id).body,
            "created_at": ensure_utc(ticket.created_at).isoformat(), "customer_status": "replied" if ticket.reply else "received",
            "reply": {"body": ticket.reply["body"], "sent_at": ticket.reply["sent_at"]} if ticket.reply else None}


def order_context(order):
    data = order.payload
    context = {key: data[key] for key in ("order_status", "order_total", "shipping_cost")}
    context["shipment_status"] = data["shipment"]["shipment_status"]
    if data.get("refund"):
        context.update({key: data["refund"][key] for key in ("refund_status", "refund_amount")})
    return context


def suggestion_view(suggestion):
    if suggestion is None:
        return None
    payload = deepcopy(suggestion.payload)
    mapping = suggestion.pseudonym_map
    if payload.get("draft"):
        payload["draft"]["text"] = restore(payload["draft"]["text"], mapping)
        for segment in payload["draft"].get("segments", []):
            segment["text"] = restore(segment["text"], mapping)
    if payload.get("staff_note"):
        payload["staff_note"] = restore(payload["staff_note"], mapping)
    return payload


def pending(suggestion):
    return suggestion and (suggestion.payload.get("analysis_status") == "pending" or suggestion.payload.get("draft_status") == "pending")


def allowed_actions(ticket, actor, suggestion):
    if ticket.status == "closed" or actor.role == "staff" and ticket.status != "open":
        return []
    actions = []
    if ticket.status == "open":
        if suggestion and (suggestion.payload.get("analysis_status") == "ready" or suggestion.payload.get("intent_override")):
            actions.append("correct_intent")
        if suggestion and suggestion.payload.get("draft_status") in ("unavailable", "llm_unavailable") and "pseudonymization_failed" not in suggestion.payload.get("reason_codes", []):
            actions.append("retry_suggestion")
        if actor.role == "staff":
            actions.append("submit_reply_proposal")
        if actor.role in ("staff", "admin"):
            actions.append("escalate")
    own_pending_proposal = ticket.status == "awaiting_approval" and (ticket.proposal or {}).get("actor_account_id") == actor.account_id
    if not pending(suggestion) and not own_pending_proposal and (actor.role in AUTHORITY_ROLES or not ticket.is_authority_required):
        actions.append("send_reply")
    return actions


def create_suggestion(session, ticket, settings, trace_id, intent_override=None, trigger="ticket_created"):
    if intent_override is not None and intent_override not in INTENTS:
        raise Problem(422, "invalid-request", "Choose a recognized intent.")
    previous = session.get(Suggestion, ticket.current_suggestion_id) if ticket.current_suggestion_id else None
    if previous:
        data = dict(previous.payload)
        for name in ("analysis_status", "draft_status"):
            if data.get(name) == "pending":
                data[name] = "cancelled"
        previous.payload = data
    orders = session.scalars(select(Order).where(Order.customer_id == ticket.customer_id)).all()
    known = {"NAME": [order.payload.get("customer_name") for order in orders], "PHONE": [order.payload.get("phone") for order in orders],
             "ORDER_ID": [order.order_id for order in orders], "TRACKING_ID": [order.payload["shipment"].get("tracking_code") for order in orders],
             "TRANSACTION_ID": [order.payload.get("transaction_id") for order in orders]}
    customer_account=session.scalar(select(Account).where(Account.customer_id==ticket.customer_id))
    if customer_account:
        known.setdefault('NAME',[]).append(customer_account.display_name)
        known.setdefault('EMAIL',[]).append(customer_account.email)
        known.setdefault('PHONE',[]).append(customer_account.phone)
        known.setdefault('ADDRESS',[]).append(customer_account.address)
    try:
        message, mapping = pseudonymize(
            session.get(CustomerMessage, ticket.ticket_id).body,
            known,
            require_ner=bool(settings.ai_service_base_url) or bool(getattr(settings, "require_privacy_ner", True)),
        )
        privacy_failed = False
    except ValueError:
        message, mapping, privacy_failed = "", {}, True
    identifier = str(uuid.uuid4())
    now = utcnow()
    available = bool(settings.ai_service_base_url) and not privacy_failed
    payload = {"suggestion_id": identifier, "trigger": trigger, "intent_override": intent_override, "created_at": now.isoformat(),
               "analysis_status": "pending" if available else "unavailable", "draft_status": "pending" if available else "unavailable",
               "reason_codes": [] if available else ["pseudonymization_failed" if privacy_failed else "ai_service_unavailable"],
               "warnings": [], "trace_id": trace_id, "versions": None, "step_latency_ms": {}}
    request_payload = {"message": message, "order_context": order_context(require_order(session, ticket.order_id)) if ticket.order_id else {}, "as_of": ensure_utc(ticket.created_at).isoformat()}
    if intent_override:
        request_payload["intent_override"] = intent_override
    suggestion = Suggestion(suggestion_id=identifier, ticket_id=ticket.ticket_id, created_at=now, completed_at=None if available else now,
                            payload=payload, request_payload=request_payload, pseudonym_map=mapping)
    session.add(suggestion)
    session.flush()
    if available:
        session.add(SuggestionJob(suggestion_id=identifier))
    ticket.current_suggestion_id = identifier
    body_text = (session.get(CustomerMessage, ticket.ticket_id).body if session.get(CustomerMessage, ticket.ticket_id) else "")
    if intent_override in SENSITIVE_ACTION_INTENTS or has_authority_request(body_text):
        ticket.is_authority_required = True
    metrics.record_pii({"entities": len(mapping)}, blocked=privacy_failed)
    audit(session, "message.pseudonymized", None, trace_id, ticket.ticket_id, outcome="failed" if privacy_failed else "ready", pseudonym_count=len(mapping))
    return payload


def create_ticket(session, actor, order_id, message, settings, trace_id):
    if not order_id:
        mentioned = set(re.findall(r'\bORD-[A-Za-z0-9]+\b', message, re.I))
        owned = session.scalars(select(Order).where(Order.customer_id == actor.customer_id)).all()
        matches = [order.order_id for order in owned if order.order_id.upper() in {value.upper() for value in mentioned}]
        if len(matches) == 1:
            order_id = matches[0]
    if order_id:
        require_order(session, order_id, actor.customer_id)
    if session.bind and session.bind.dialect.name == "postgresql":
        number = session.scalar(text("SELECT nextval('ticket_number_seq')"))
    else:
        max_id = session.scalar(text("SELECT MAX(CAST(SUBSTR(ticket_id, 5) AS INTEGER)) FROM tickets"))
        number = (max_id or 1000) + 1
    message_requires_authority = has_authority_request(message)
    ticket = Ticket(ticket_id=f"TCK-{number}", customer_id=actor.customer_id, order_id=order_id, created_at=utcnow(), status="open", handling_mode="assisted", is_authority_required=message_requires_authority)
    session.add(ticket)
    session.flush()
    session.add(CustomerMessage(ticket_id=ticket.ticket_id, body=message))
    session.flush()
    create_suggestion(session, ticket, settings, trace_id)
    audit(session, "ticket.created", actor.account_id, trace_id, ticket.ticket_id)
    return shop_ticket(session, ticket)


def summary(session, ticket):
    account = session.scalar(select(Account).where(Account.customer_id == ticket.customer_id))
    suggestion = session.get(Suggestion, ticket.current_suggestion_id) if ticket.current_suggestion_id else None
    data = suggestion.payload if suggestion else {}
    return {"ticket_id": ticket.ticket_id, "created_at": ensure_utc(ticket.created_at).isoformat(), "status": ticket.status, "handling_mode": ticket.handling_mode,
            "is_authority_required": ticket.is_authority_required, "handling_started_at": ensure_utc(ticket.handling_started_at).isoformat() if ticket.handling_started_at else None,
            "customer": {"display_name": account.display_name}, "excerpt": session.get(CustomerMessage, ticket.ticket_id).body[:150],
            "draft_status": data.get("draft_status"), "intent": (data.get("analysis") or {}).get("intent")}


def workspace(session, ticket, actor):
    result = summary(session, ticket)
    suggestion = session.get(Suggestion, ticket.current_suggestion_id) if ticket.current_suggestion_id else None
    result.update({"message": {"body": session.get(CustomerMessage, ticket.ticket_id).body, "created_at": ensure_utc(ticket.created_at).isoformat()},
                   "order": order_view(require_order(session, ticket.order_id), internal=True) if ticket.order_id else None,
                   "other_orders": [order_view(order) for order in session.scalars(select(Order).where(Order.customer_id == ticket.customer_id, Order.order_id != ticket.order_id))],
                   "suggestion": suggestion_view(suggestion), "proposal": ticket.proposal, "escalation": ticket.escalation,
                   "reply": ticket.reply, "allowed_actions": allowed_actions(ticket, actor, suggestion)})
    return result


def reason_check(reasons, note, required=False):
    if required and not reasons or not set(reasons) <= STAFF_REASONS:
        raise Problem(422, "invalid-request", "Choose at least one valid reason.")
    if "other" in reasons and not (note or "").strip():
        raise Problem(422, "invalid-request", "Add a note for Other.")


def validate_reply(ticket, suggestion, body):
    if PLACEHOLDER.search(body["body"]):
        raise Problem(422, "invalid-request", "Replace personal-data placeholders before sending.")
    if pending(suggestion):
        raise Problem(409, "suggestion-pending", "The AI is still working on this ticket.")
    basis = body["basis"]
    data = suggestion.payload if suggestion else {}
    if body.get("suggestion_id") and body["suggestion_id"] != ticket.current_suggestion_id:
        raise Problem(409, "suggestion-superseded", "This draft was replaced. Reload the ticket; your text is kept.")
    if basis in ("ai_draft", "rejected_ai_draft"):
        if data.get("draft_status") != "draft_ready" or body.get("suggestion_id") != ticket.current_suggestion_id:
            raise Problem(422, "invalid-request", "This reply needs the current AI draft.")
        if basis == "ai_draft" and not {warning["warning_id"] for warning in data.get("warnings", [])} <= set(body.get("acknowledged_warning_ids") or []):
            raise Problem(422, "invalid-request", "Acknowledge every warning before sending.")
        reason_check(body.get("staff_reason_codes") or [], body.get("note"), basis == "rejected_ai_draft")
    elif basis == "no_ai_draft":
        if data.get("draft_status") == "draft_ready" and ticket.handling_mode != "manual":
            raise Problem(422, "invalid-request", "Review or reject the current draft before sending.")
    elif basis == "reply_proposal":
        if ticket.status != "awaiting_approval" or not ticket.proposal or ticket.proposal["proposal_id"] != body.get("proposal_id"):
            raise Problem(422, "invalid-request", "This proposal is no longer current.")


def act(session, actor, ticket_id, action, body, settings, trace_id):
    ticket = require_ticket(session, ticket_id, lock=True)
    suggestion = session.get(Suggestion, ticket.current_suggestion_id) if ticket.current_suggestion_id else None
    if ticket.status == "closed":
        raise Problem(409, "invalid-ticket-state", "A colleague already sent the reply.")
    if actor.role == "staff" and ticket.status != "open":
        raise Problem(403, "forbidden", "This ticket requires administrator authority.")
    if action == "suggestions":
        override = body.get("intent_override")
        if ticket.status != "open":
            raise Problem(409, "invalid-ticket-state", "Only open tickets can receive a new suggestion.")
        actions = allowed_actions(ticket, actor, suggestion)
        if override and "correct_intent" not in actions:
            raise Problem(409 if pending(suggestion) else 422, "suggestion-pending" if pending(suggestion) else "invalid-request", "Wait until an intent is available before correcting it.")
        if not override and "retry_suggestion" not in actions:
            raise Problem(422, "invalid-request", "There is no failed suggestion to retry.")
        if not override and suggestion and suggestion.payload.get("intent_override"):
            override = suggestion.payload.get("intent_override")
        result = create_suggestion(session, ticket, settings, trace_id, override, "intent_override" if override else "retry")
        if override:
            audit(session, "intent.overridden", actor.account_id, trace_id, ticket.ticket_id, chosen_intent=override)
        return result
    if action == "escalations":
        if actor.role not in ("staff", "admin"):
            raise Problem(403, "forbidden", "Only staff or administrators can escalate open tickets.")
        if ticket.status != "open":
            raise Problem(409, "invalid-ticket-state", "Only open tickets can be escalated.")
        if body.get("suggestion_id") and body["suggestion_id"] != ticket.current_suggestion_id:
            raise Problem(409, "suggestion-superseded", "Reload the current suggestion before escalating.")
        reason_check(body["staff_reason_codes"], body.get("note"), required=True)
        result = {"escalation_id": str(uuid.uuid4()), **body, "by": actor.display_name, "created_at": utcnow().isoformat()}
        ticket.status, ticket.escalation = "escalated", result
        for code in body["staff_reason_codes"]:
            metrics.record_escalation(code)
        audit(session, "ticket.escalated", actor.account_id, trace_id, ticket.ticket_id, staff_reason_codes=body["staff_reason_codes"])
        return result
    if action == "replies" and actor.role == "staff" and ticket.is_authority_required:
        raise Problem(403, "authority-required", "An administrator must send the reply. Submit it for approval.")
    if action == "reply-proposals" and actor.role != "staff":
        raise Problem(403, "forbidden", "Only staff submit proposals for approval.")
    if action == "replies" and (ticket.status == "awaiting_approval" or body.get("basis") == "reply_proposal") and (ticket.proposal or {}).get("actor_account_id") == actor.account_id:
        raise Problem(403, "self-approval-forbidden", "You cannot approve your own reply proposal.")
    validate_reply(ticket, suggestion, body)
    if action == "reply-proposals":
        if body["basis"] == "reply_proposal":
            raise Problem(422, "invalid-request", "A proposal cannot be based on another proposal.")
        result = {"proposal_id": str(uuid.uuid4()), **body, "by": actor.display_name, "actor_account_id": actor.account_id, "created_at": utcnow().isoformat()}
        ticket.status, ticket.proposal = "awaiting_approval", result
        audit(session, "reply_proposal.submitted", actor.account_id, trace_id, ticket.ticket_id, proposal_id=result["proposal_id"])
        return result
    result = {"reply_id": str(uuid.uuid4()), "body": body["body"], "sent_at": utcnow().isoformat(), "by": actor.display_name}
    ticket.status, ticket.reply, ticket.closed_at = "closed", result, utcnow()
    origin = ticket.proposal if body["basis"] == "reply_proposal" else body
    decision = None
    canonical = (suggestion_view(suggestion) or {}).get("draft", {}).get("text", "")
    normalize = lambda value: value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if origin["basis"] == "ai_draft":
        decision = "approve" if normalize(canonical) == normalize(body["body"]) else "edit"
    elif origin["basis"] == "rejected_ai_draft":
        decision = "reject"
    audit(session, "reply.sent", actor.account_id, trace_id, ticket.ticket_id, reply_id=result["reply_id"], basis=body["basis"])
    if decision:
        metrics.record_decision(decision)
        audit(session, "decision.recorded", actor.account_id, trace_id, ticket.ticket_id, decision=decision,
              suggestion_id=ticket.current_suggestion_id, change_ratio=1 - SequenceMatcher(None, normalize(canonical), normalize(body["body"])).ratio(),
              staff_reason_codes=origin.get("staff_reason_codes") or [])
    return result

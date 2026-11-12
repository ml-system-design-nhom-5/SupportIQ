"""Leased PostgreSQL jobs; late results never replace a newer suggestion."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
import threading
import time
import uuid

import httpx
from sqlalchemy import or_, select

from apps.backend.platform.database import audit, utcnow, ensure_utc
from apps.backend.platform.models import Suggestion, SuggestionJob, Ticket
from apps.backend.platform.observability import metrics, logger

AI_REASONS = {"low_confidence", "signal_disagreement", "out_of_scope_intent", "human_agent_requested", "requires_authority", "no_valid_document", "only_expired_documents", "conflicting_sources", "missing_information", "source_review_overdue", "grounding_failed", "llm_unavailable", "llm_invalid_output", "budget_exceeded"}
DRAFT_STATES = {"draft_ready", "abstained", "escalation_recommended", "llm_unavailable"}


def validate_analysis(data):
    intent = data["intent"]
    if not isinstance(intent["label"], str) or not 0 <= intent["probability"] <= 1 or intent["confidence_band"] not in ("high", "medium", "low"):
        raise ValueError("Invalid analysis")
    if not set(data["routing"]["reason_codes"]) <= AI_REASONS or data["routing"]["recommendation"] not in ("draft", "abstain", "escalate"):
        raise ValueError("Invalid routing")
    for name in ("alternatives", "documents", "warnings"):
        if not isinstance(data[name], list):
            raise ValueError("Invalid analysis list")
    if not isinstance(data["versions"], dict) or not data["versions"].get("release_id"):
        raise ValueError("Missing provenance")
    return data


class SuggestionWorker:
    def __init__(self, database, settings):
        self.database, self.settings = database, settings
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.settings.ai_service_base_url:
            self.thread = threading.Thread(target=self.run, daemon=True, name="suggestion-jobs")
            self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=12)

    def run(self):
        while not self.stop_event.is_set():
            try:
                claimed = self.claim()
                if claimed:
                    self.process(*claimed)
                    continue
            except Exception:
                # Retry through the durable lease; exception text may contain confidential SQL parameters.
                pass
            self.stop_event.wait(self.settings.job_poll_interval_ms / 1000)

    def claim(self, suggestion_id=None):
        with self.database.transaction() as session:
            query = select(SuggestionJob).where(SuggestionJob.finished.is_(False), or_(SuggestionJob.lease_until.is_(None), SuggestionJob.lease_until < utcnow()))
            if suggestion_id:
                query = query.where(SuggestionJob.suggestion_id == suggestion_id)
            job = session.scalar(query.with_for_update(skip_locked=True).limit(1))
            if job is None:
                return None
            suggestion = session.get(Suggestion, job.suggestion_id)
            ticket = session.get(Ticket, suggestion.ticket_id)
            if ticket.current_suggestion_id != suggestion.suggestion_id:
                job.finished = True
                return None
            if job.attempts >= 3:
                data = dict(suggestion.payload)
                for part in ("analysis_status", "draft_status"):
                    if data[part] == "pending":
                        data[part] = "unavailable"
                data["reason_codes"] = list(set(data.get("reason_codes", [])) | {"ai_service_unavailable"})
                data["staff_note"] = "The AI service is unavailable after retries. Review the customer message and order records to write a reply manually."
                suggestion.payload, suggestion.completed_at, job.finished = data, utcnow(), True
                return None
            job.attempts += 1
            job.lease_token = str(uuid.uuid4())
            job.lease_until = utcnow() + timedelta(milliseconds=self.settings.job_lease_ms)
            return suggestion.suggestion_id, job.lease_token, suggestion.request_payload

    def process(self, identifier, token, payload):
        def fetch(part):
            budget = self.settings.ai_service_analysis_timeout_ms if part == "analysis" else self.settings.ai_service_draft_timeout_ms
            started = time.perf_counter()
            try:
                endpoint = "analyses" if part == "analysis" else "drafts"
                with httpx.Client(timeout=budget / 1000, trust_env=False) as client:
                    response = client.post(self.settings.ai_service_base_url.rstrip("/") + "/v1/" + endpoint, json=payload)
                    response.raise_for_status()
                    result = response.json()
                if part == "analysis":
                    validate_analysis(result)
                else:
                    if result["status"] not in DRAFT_STATES or not set(result["reason_codes"]) <= AI_REASONS:
                        raise ValueError("Invalid draft outcome")
                    validate_analysis(result["analysis"])
                    if result["status"] == "draft_ready":
                        paragraphs = {}
                        last_index = -1
                        for segment in result["draft"]["segments"]:
                            index = segment["paragraph_index"]
                            if not isinstance(segment["text"], str) or index < last_index:
                                raise ValueError("Invalid draft segments")
                            last_index = index
                            paragraphs.setdefault(index, []).append(segment["text"])
                        result["draft"]["text"] = "\n\n".join(" ".join(parts) for parts in paragraphs.values())
                        if not result["draft"]["text"].strip():
                            raise ValueError("Empty draft")
                        for citation in result["draft"]["citations"]:
                            if citation["source_type"] == "order_context":
                                citation["value"] = payload["order_context"][citation["field"]]
                return part, result, round((time.perf_counter() - started) * 1000)
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                return part, None, round((time.perf_counter() - started) * 1000)
        # 1. Fetch analysis first
        part, analysis_res, latency = fetch("analysis")
        if analysis_res is None:
            # AI service failed on analysis: fail closed to manual fallback immediately without waiting for draft timeout
            self.store(identifier, token, "analysis", None, latency)
            synthesized_draft = {
                "status": "unavailable",
                "reason_codes": ["ai_service_unavailable"],
                "staff_note": "The AI service is unavailable. Review the customer message and order records to write a reply manually.",
                "versions": {},
                "step_latency_ms": {},
                "mask_count_by_type": {}
            }
            self.store(identifier, token, "draft", synthesized_draft, 0)
            return

        self.store(identifier, token, part, analysis_res, latency)

        # 2. If analysis abstained or escalated, avoid redundant model inference and LLM call
        if analysis_res.get("routing", {}).get("recommendation") != "draft":
            rec = analysis_res["routing"]["recommendation"]
            codes = analysis_res["routing"]["reason_codes"]
            synthesized_draft = {
                "analysis": analysis_res,
                "status": "escalation_recommended" if rec == "escalate" else "abstained",
                "reason_codes": codes,
                "versions": analysis_res.get("versions", {}),
                "step_latency_ms": analysis_res.get("step_latency_ms", {}),
                "mask_count_by_type": {}
            }
            if "low_confidence" in codes:
                synthesized_draft["staff_note"] = "The model score or margin is below the routing threshold. Confirm or correct the intent before drafting."
            self.store(identifier, token, "draft", synthesized_draft, 0)
            return

        # 3. Otherwise execute draft
        part, draft_res, latency = fetch("draft")
        if draft_res is None:
            synthesized_draft = {
                "analysis": analysis_res,
                "status": "unavailable",
                "reason_codes": ["ai_service_unavailable"],
                "staff_note": "Draft generation is unavailable. Review the retrieved sources and write a reply manually.",
                "versions": analysis_res.get("versions", {}),
                "step_latency_ms": {},
                "mask_count_by_type": {}
            }
            self.store(identifier, token, "draft", synthesized_draft, latency)
            return

        self.store(identifier, token, part, draft_res, latency)

    def store(self, identifier, token, part, result, latency_ms):
        with self.database.transaction() as session:
            # Match the workflow's ticket→suggestion locking order to avoid deadlocks.
            snapshot = session.get(Suggestion, identifier)
            ticket = session.scalar(select(Ticket).where(Ticket.ticket_id == snapshot.ticket_id).with_for_update())
            job = session.scalar(select(SuggestionJob).where(SuggestionJob.suggestion_id == identifier).with_for_update())
            if ticket.current_suggestion_id != identifier or job.lease_token != token or (job.lease_until and ensure_utc(job.lease_until) <= utcnow()):
                return
            suggestion = session.get(Suggestion, identifier)
            data = dict(suggestion.payload)
            data["step_latency_ms"] = {**data.get("step_latency_ms", {}), part: latency_ms}
            if result is None:
                if part == "analysis" and data.get("analysis_status") == "ready":
                    return
                data["analysis_status" if part == "analysis" else "draft_status"] = "unavailable"
                data["reason_codes"] = list(set(data.get("reason_codes", [])) | {"ai_service_unavailable"})
                if "staff_note" not in data or not data["staff_note"]:
                    data["staff_note"] = "The AI service is unavailable. Review the customer message and order records to write a reply manually."
            else:
                analysis = result.get("analysis") if part == "draft" else result
                if analysis:
                    data.update(analysis_status="ready", analysis=analysis, versions=analysis.get("versions"))
                if part == "draft":
                    data.update(draft_status=result["status"], reason_codes=result["reason_codes"], warnings=(analysis or {}).get("warnings", []), staff_note=result.get("staff_note"))
                    if result.get("draft"):
                        data["draft"] = result["draft"]
                    data["llm_usage"] = result.get("llm_usage")
                    if result.get("llm_metadata"):
                        data["llm_metadata"] = result.get("llm_metadata")
                    data["failure_code"] = result.get("failure_code")
                    data["step_latency_ms"] = {**data["step_latency_ms"], **result.get("step_latency_ms", {})}
                codes = set((analysis or {}).get("routing", {}).get("reason_codes", [])) | set(result.get("reason_codes", []))
                if "requires_authority" in codes:
                    ticket.is_authority_required = True
            suggestion.payload = data
            if data["analysis_status"] != "pending" and data["draft_status"] != "pending":
                suggestion.completed_at, job.finished = utcnow(), True
            metrics.record_stage(part, latency_ms)
            if result is not None:
                if part == "analysis":
                    intent_obj = result.get("intent") or {}
                    metrics.record_intent(intent_obj.get("label", "unknown"), float(intent_obj.get("probability", 0.0)), is_ood="out_of_scope_intent" in (result.get("routing") or {}).get("reason_codes", []))
                elif part == "draft":
                    metrics.record_draft(result.get("status", "unknown"))
                    llm_usage = result.get("llm_usage") or {}
                    metrics.record_llm(result.get("status", "unknown"), latency_ms, prompt_tokens=llm_usage.get("input_tokens", 0) or 0, candidate_tokens=llm_usage.get("output_tokens", 0) or 0)
                    if "grounding_failed" in (result.get("reason_codes") or []):
                        metrics.record_citation_failure()
            audit(session, "suggestion.part_completed", None, data["trace_id"], ticket.ticket_id,
                  suggestion_id=identifier, part=part, status=data["analysis_status" if part == "analysis" else "draft_status"], latency_ms=latency_ms)

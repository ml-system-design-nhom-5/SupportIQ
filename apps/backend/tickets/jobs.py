"""Leased PostgreSQL jobs; late results never replace a newer suggestion."""

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import timedelta
import threading
import time
import uuid

import httpx
from sqlalchemy import or_, select

_REAL_HTTPX_CLIENT = httpx.Client


def _positive_int(value, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return default

from apps.backend.platform.database import audit, utcnow, ensure_utc
from apps.backend.platform.models import Suggestion, SuggestionJob, Ticket
from apps.backend.platform.observability import metrics
from .privacy import validate_egress_payload

_BOUNDED_REMOTE_FAULT_CODES = frozenset({
    "ai_service_unavailable",
    "ml_timeout",
    "ml_error",
    "ml_unavailable",
    "encoder_unavailable",
    "encoder_failure",
    "encoder_failed",
})

AI_REASONS = {
    "low_confidence", "signal_disagreement", "out_of_scope_intent", "human_agent_requested",
    "requires_authority", "no_valid_document", "only_expired_documents", "conflicting_sources",
    "missing_information", "insufficient_evidence", "source_review_overdue", "grounding_failed",
    "llm_unavailable", "llm_invalid_output", "budget_exceeded",
    "ai_service_unavailable", "ml_timeout", "ml_error", "ml_unavailable",
    "encoder_unavailable", "encoder_failure", "encoder_failed",
    "llm_timeout", "llm_rate_limited", "llm_insufficient_evidence",
    "selective_rejected", "low_margin", "invalid_model_output", "explicit_human_request",
}
DRAFT_STATES = {"draft_ready", "abstained", "escalation_recommended", "llm_unavailable"}


def _classify_http_failure(exc: Exception) -> dict:
    """Map transport/HTTP errors strictly to bounded fault codes without exposing raw text."""
    if isinstance(exc, httpx.TimeoutException):
        return {"failure_code": "ml_timeout", "reason_codes": ["ml_timeout", "ai_service_unavailable"]}

    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        header_code = exc.response.headers.get("X-SupportIQ-Error-Code")
        body_code = None
        body_codes: list[str] = []
        try:
            payload = exc.response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else None
            if isinstance(detail, dict):
                raw_code = detail.get("error_code") or detail.get("code")
                if isinstance(raw_code, str) and raw_code in _BOUNDED_REMOTE_FAULT_CODES:
                    body_code = raw_code
                raw_list = detail.get("reason_codes")
                if isinstance(raw_list, list):
                    body_codes = [c for c in raw_list if isinstance(c, str) and c in _BOUNDED_REMOTE_FAULT_CODES]
        except Exception:
            pass

        chosen = None
        if isinstance(header_code, str) and header_code in _BOUNDED_REMOTE_FAULT_CODES:
            chosen = header_code
        elif body_code:
            chosen = body_code
        elif exc.response.status_code == 504:
            chosen = "ml_timeout"

        if chosen == "ml_timeout":
            return {"failure_code": "ml_timeout", "reason_codes": list(dict.fromkeys(["ml_timeout", *body_codes, "ai_service_unavailable"]))}
        if chosen in ("encoder_failure", "encoder_failed"):
            return {"failure_code": "encoder_failure", "reason_codes": list(dict.fromkeys(["encoder_failure", "encoder_failed", *body_codes, "ai_service_unavailable"]))}
        if chosen in ("ml_error", "ml_unavailable", "encoder_unavailable"):
            return {"failure_code": chosen, "reason_codes": list(dict.fromkeys([chosen, *body_codes, "ai_service_unavailable"]))}

    return {"failure_code": "ai_service_unavailable", "reason_codes": ["ai_service_unavailable"]}


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
    def __init__(self, database, settings, http_client=None):
        self.database, self.settings = database, settings
        self.stop_event = threading.Event()
        self.thread = None
        self._concurrency = _positive_int(getattr(settings, "job_concurrency", 4), 4)
        self._poll_interval_ms = _positive_int(getattr(settings, "job_poll_interval_ms", 500), 500)
        self._lease_ms = _positive_int(getattr(settings, "job_lease_ms", 20_000), 20_000)
        self._injected_http_client = http_client
        self._client_lock = threading.Lock()
        self._owned_http_client = None
        self._owned_client_factory = None

    def start(self):
        if self.settings.ai_service_base_url:
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.run, daemon=True, name="suggestion-jobs")
            self.thread.start()

    @staticmethod
    def _close_client_safely(client) -> None:
        try:
            client.close()
        except Exception:
            pass

    def _close_http_clients(self) -> None:
        with self._client_lock:
            client = self._owned_http_client
            self._owned_http_client = None
            self._owned_client_factory = None
        if client is not None:
            self._close_client_safely(client)

    def close(self):
        self.stop_event.set()
        if self.thread:
            analysis_ms = _positive_int(getattr(self.settings, "ai_service_analysis_timeout_ms", 3_000), 3_000)
            draft_ms = _positive_int(getattr(self.settings, "ai_service_draft_timeout_ms", 11_000), 11_000)
            join_timeout = max(12.0, (analysis_ms + draft_ms) / 1000 + 2.0)
            self.thread.join(timeout=join_timeout)
        if not self.thread or not self.thread.is_alive():
            self._close_http_clients()

    def _post_ai(self, endpoint: str, payload: dict, budget_ms: int) -> dict:
        url = self.settings.ai_service_base_url.rstrip("/") + "/v1/" + endpoint
        timeout_s = budget_ms / 1000
        if self._injected_http_client is not None:
            response = self._injected_http_client.post(url, json=payload, timeout=timeout_s)
            response.raise_for_status()
            return response.json()

        factory = httpx.Client
        non_pooled_client = None
        with self._client_lock:
            if self._owned_http_client is not None and (
                self._owned_client_factory is not factory
                or getattr(self._owned_http_client, "is_closed", False)
            ):
                self._close_client_safely(self._owned_http_client)
                self._owned_http_client = None
                self._owned_client_factory = None
            if self._owned_http_client is None:
                if factory is _REAL_HTTPX_CLIENT:
                    limits = httpx.Limits(
                        max_connections=max(10, self._concurrency * 2),
                        max_keepalive_connections=max(5, self._concurrency),
                    )
                    candidate = factory(timeout=timeout_s, trust_env=False, limits=limits)
                else:
                    candidate = factory(timeout=timeout_s, trust_env=False)
                if isinstance(candidate, _REAL_HTTPX_CLIENT):
                    self._owned_http_client = candidate
                    self._owned_client_factory = factory
                else:
                    non_pooled_client = candidate
            pooled_client = self._owned_http_client

        if pooled_client is not None:
            response = pooled_client.post(url, json=payload, timeout=timeout_s)
            response.raise_for_status()
            return response.json()

        with non_pooled_client as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def _process_claimed(self, identifier, token, payload):
        try:
            self.process(identifier, token, payload)
        except Exception:
            # Retry through the durable lease; avoid crashing executor or stopping sibling jobs.
            pass

    def run(self):
        in_flight: set[Future] = set()
        poll_s = self._poll_interval_ms / 1000
        with ThreadPoolExecutor(max_workers=self._concurrency, thread_name_prefix="suggestion-jobs") as executor:
            try:
                while not self.stop_event.is_set():
                    done = {fut for fut in in_flight if fut.done()}
                    in_flight -= done

                    while len(in_flight) < self._concurrency and not self.stop_event.is_set():
                        try:
                            claimed = self.claim()
                        except Exception:
                            # Retry through the durable lease; exception text may contain confidential SQL parameters.
                            break
                        if not claimed:
                            break
                        in_flight.add(executor.submit(self._process_claimed, *claimed))

                    if self.stop_event.is_set():
                        break

                    if len(in_flight) >= self._concurrency:
                        wait(in_flight, timeout=min(0.05, poll_s), return_when=FIRST_COMPLETED)
                    else:
                        self.stop_event.wait(poll_s)
            finally:
                for fut in list(in_flight):
                    if not fut.done():
                        fut.cancel()
        self._close_http_clients()

    def claim(self, suggestion_id=None):
        while True:
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
                    if suggestion_id:
                        return None
                    continue
                if job.attempts >= 3:
                    data = dict(suggestion.payload)
                    for part in ("analysis_status", "draft_status"):
                        if data[part] == "pending":
                            data[part] = "unavailable"
                    data["reason_codes"] = list(set(data.get("reason_codes", [])) | {"ai_service_unavailable"})
                    data["staff_note"] = "The AI service is unavailable after retries. Review the customer message and order records to write a reply manually."
                    suggestion.payload, suggestion.completed_at, job.finished = data, utcnow(), True
                    if suggestion_id:
                        return None
                    continue
                job.attempts += 1
                job.lease_token = str(uuid.uuid4())
                job.lease_until = utcnow() + timedelta(milliseconds=self._lease_ms)
                return suggestion.suggestion_id, job.lease_token, suggestion.request_payload

    def process(self, identifier, token, payload):
        strict_ner = bool(getattr(self.settings, "require_privacy_ner", True))
        try:
            validate_egress_payload(payload, require_ner=strict_ner)
        except ValueError:
            self.store(
                identifier,
                token,
                "analysis",
                None,
                0,
                failure_info={"failure_code": "pseudonymization_failed", "reason_codes": ["pseudonymization_failed"]},
            )
            synthesized_draft = {
                "status": "unavailable",
                "failure_code": "pseudonymization_failed",
                "reason_codes": ["pseudonymization_failed"],
                "staff_note": "Customer data could not be safely pseudonymized for AI processing. Review the ticket and respond manually.",
                "versions": {},
                "step_latency_ms": {},
                "mask_count_by_type": {},
            }
            self.store(identifier, token, "draft", synthesized_draft, 0)
            return

        def fetch(part):
            budget = self.settings.ai_service_analysis_timeout_ms if part == "analysis" else self.settings.ai_service_draft_timeout_ms
            started = time.perf_counter()
            try:
                endpoint = "analyses" if part == "analysis" else "drafts"
                result = self._post_ai(endpoint, payload, budget)
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
                                fields = citation.get("fields")
                                if fields is not None:
                                    if (
                                        not isinstance(fields, list)
                                        or not fields
                                        or any(not isinstance(field_name, str) or field_name not in payload["order_context"] for field_name in fields)
                                    ):
                                        raise ValueError("Invalid order_context citation fields")
                                    citation["values"] = {field_name: payload["order_context"][field_name] for field_name in fields}
                                if "field" in citation:
                                    field_name = citation["field"]
                                    if not isinstance(field_name, str) or (fields is not None and field_name not in fields):
                                        raise ValueError("Invalid order_context citation field")
                                    citation["value"] = payload["order_context"][field_name]
                                elif not fields:
                                    raise ValueError("Invalid order_context citation")
                return part, result, round((time.perf_counter() - started) * 1000), None
            except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
                return part, None, round((time.perf_counter() - started) * 1000), _classify_http_failure(exc)
        # 1. Fetch analysis first
        part, analysis_res, latency, failure_info = fetch("analysis")
        if analysis_res is None:
            # AI service failed on analysis: fail closed to manual fallback immediately without waiting for draft timeout
            self.store(identifier, token, "analysis", None, latency, failure_info=failure_info)
            failure_code = (failure_info or {}).get("failure_code", "ai_service_unavailable")
            reason_codes = list((failure_info or {}).get("reason_codes") or ["ai_service_unavailable"])
            staff_note = (
                "The AI request timed out. Review the customer message and order records to write a reply manually."
                if failure_code == "ml_timeout"
                else "The AI service is unavailable. Review the customer message and order records to write a reply manually."
            )
            synthesized_draft = {
                "status": "unavailable",
                "failure_code": failure_code,
                "reason_codes": reason_codes,
                "staff_note": staff_note,
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
            if rec == 'escalate':
                synthesized_draft['staff_note'] = 'Escalate this request to authorized staff to resolve the policy or authority issue before replying.'
            elif "low_confidence" in codes:
                synthesized_draft["staff_note"] = "The model score or margin is below the routing threshold. Confirm or correct the intent before drafting."
            self.store(identifier, token, "draft", synthesized_draft, 0)
            return

        # 3. Otherwise execute draft
        if self.stop_event.is_set():
            return
        part, draft_res, latency, failure_info = fetch("draft")
        if draft_res is None:
            failure_code = (failure_info or {}).get("failure_code", "ai_service_unavailable")
            reason_codes = list((failure_info or {}).get("reason_codes") or ["ai_service_unavailable"])
            synthesized_draft = {
                "analysis": analysis_res,
                "status": "unavailable",
                "failure_code": failure_code,
                "reason_codes": reason_codes,
                "staff_note": "Draft generation is unavailable. Review the retrieved sources and write a reply manually.",
                "versions": analysis_res.get("versions", {}),
                "step_latency_ms": {},
                "mask_count_by_type": {}
            }
            self.store(identifier, token, "draft", synthesized_draft, latency)
            return

        self.store(identifier, token, part, draft_res, latency)

    def store(self, identifier, token, part, result, latency_ms, failure_info=None):
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
                fail_codes = (failure_info or {}).get("reason_codes") or ["ai_service_unavailable"]
                fail_code = (failure_info or {}).get("failure_code") or data.get("failure_code") or "ai_service_unavailable"
                data["analysis_status" if part == "analysis" else "draft_status"] = "unavailable"
                data["reason_codes"] = list(dict.fromkeys([*data.get("reason_codes", []), *fail_codes]))
                data["failure_code"] = fail_code
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

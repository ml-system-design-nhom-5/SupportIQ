"""Translate existing verified assets into the application AI contract without ticket state."""

import copy
from datetime import datetime
import math
import re
import time

from apps.core_backend.llm.gemini import (
    ORDER_CONTEXT_ALLOWED_FIELDS,
    ORDER_CONTEXT_ALLOWED_SET,
    build_grounded_sources,
    extract_order_facts,
)
from apps.core_backend.safety import (
    FACTUAL_COMMITMENT,
    PLACEHOLDER,
    SENSITIVE_AUTHORITY_PATTERN,
    classify_retrieval_fault,
    evaluate_text_safety,
    find_draft_grounding_violation,
    has_uncovered_cross_border_shipping,
    policy_scope_requires_review,
    validate_generated_draft,
    validate_snapshot_sources,
)


class Engine:
    def __init__(self, model, retriever, llm, versions, policy):
        self.model, self.retriever, self.llm, self.versions, self.policy = model, retriever, llm, versions, policy

    def _policy_scope_requires_review(self, message, evidence):
        """Reject adjacent policy evidence for explicitly unsupported policy scopes."""
        return policy_scope_requires_review(message, evidence, self.retriever.eligible_versions)

    @staticmethod
    def _extract_llm_usage_and_metadata(raw_source: dict) -> tuple[dict, dict]:
        raw_usage = raw_source.get("usage", {}) or {}
        llm_usage = {}
        if "promptTokenCount" in raw_usage and raw_usage["promptTokenCount"] is not None:
            llm_usage["input_tokens"] = raw_usage["promptTokenCount"]
        if "candidatesTokenCount" in raw_usage and raw_usage["candidatesTokenCount"] is not None:
            llm_usage["output_tokens"] = raw_usage["candidatesTokenCount"]
        if "totalTokenCount" in raw_usage and raw_usage["totalTokenCount"] is not None:
            llm_usage["total_tokens"] = raw_usage["totalTokenCount"]
        elif "input_tokens" in llm_usage and "output_tokens" in llm_usage:
            llm_usage["total_tokens_partial"] = llm_usage["input_tokens"] + llm_usage["output_tokens"]
        if "thoughtsTokenCount" in raw_usage and raw_usage["thoughtsTokenCount"] is not None:
            llm_usage["thought_tokens"] = raw_usage["thoughtsTokenCount"]

        llm_metadata = {}
        for meta_key, gen_key in (
            ("provider", "provider"),
            ("model", "model"),
            ("model_version", "model_version"),
            ("prompt_version", "prompt_version"),
        ):
            if raw_source.get(gen_key):
                llm_metadata[meta_key] = raw_source[gen_key]
        if "attempts" in raw_source and raw_source["attempts"]:
            llm_metadata["attempts"] = list(raw_source["attempts"])
        return llm_usage, llm_metadata

    def _analyse(self, request):
        started = time.perf_counter()
        prediction = self.model.predict(request["message"])
        override = request.get("intent_override")
        label = override or prediction["intent"]
        probability = 1.0 if override else prediction["confidence"]
        threshold = self.policy.get("confidence_thresholds", {}).get(label, self.policy["default_confidence_threshold"])
        low = not override and (probability < threshold or prediction.get("margin", 0) < self.policy.get("margin_thresholds", {}).get(label, self.policy.get("default_margin_threshold", .1)))
        codes = []
        if low:
            codes.append("low_confidence")
        selective_accepted = prediction.get("selective_accepted")
        rejected_flag = prediction.get("rejected_by_experimental_adapter")
        rejector_decision = prediction.get("rejector_decision")
        selective_rejected = (
            (selective_accepted is False)
            or (rejected_flag is True)
            or (isinstance(rejector_decision, str) and rejector_decision.lower() == "reject")
        )
        if not override and selective_rejected:
            if "low_confidence" not in codes:
                codes.append("low_confidence")
            if "out_of_scope_intent" not in codes:
                codes.append("out_of_scope_intent")
        all_46_labels = set(self.policy.get("all_46_labels", []))
        recognized_outside_scope = (
            label in all_46_labels and label not in self.policy["supported_12_intents"]
        )
        if label not in self.policy["supported_12_intents"]:
            if "out_of_scope_intent" not in codes:
                codes.append("out_of_scope_intent")
        text_safety = evaluate_text_safety(request["message"])
        if label == "human_agent" or text_safety["human_agent_requested"]:
            if "human_agent_requested" not in codes:
                codes.append("human_agent_requested")

        # Escalated intents outside product scope explicitly requested in customer message
        explicit_outside_scope_action = text_safety["outside_product_scope"]
        if explicit_outside_scope_action or text_safety["tax_ood"]:
            if "out_of_scope_intent" not in codes:
                codes.append("out_of_scope_intent")

        candidates = [item.model_dump() if hasattr(item, "model_dump") else item for item in prediction.get("top_k", [])]
        if not override and candidates:
            probs = [item.get("probability", 0) for item in candidates]
            if len(probs) >= 2 and sum(probs) > 0:
                norm_probs = [p / sum(probs) for p in probs]
                entropy = -sum(p * math.log2(p) for p in norm_probs if p > 0)
                max_entropy = math.log2(len(probs))
                norm_entropy = entropy / max_entropy if max_entropy > 0 else 0
                if norm_entropy > 0.85 or (norm_entropy > 0.70 and probability < 0.60):
                    if "low_confidence" not in codes:
                        codes.append("low_confidence")
                    if "out_of_scope_intent" not in codes:
                        codes.append("out_of_scope_intent")
        explicit_authority = bool(text_safety["requires_authority"])
        sensitive = (
            label in self.policy.get("sensitive_action_intents", [])
            or prediction.get("intent") in self.policy.get("sensitive_action_intents", [])
            or any(
                item.get("intent") in self.policy.get("sensitive_action_intents", [])
                and item.get("probability", 0) >= self.policy.get("default_margin_threshold", 0.1)
                for item in candidates
            )
            or explicit_authority
        )
        if sensitive:
            if "requires_authority" not in codes:
                codes.append("requires_authority")
        retrieved = self.retriever.retrieve(request["message"], label, role="agent", current_time=datetime.fromisoformat(request["as_of"].replace("Z", "+00:00")))
        evidence = retrieved.get("evidence", [])
        warnings = []
        retrieval_fault_codes = classify_retrieval_fault(retrieved)
        is_retrieval_fault = bool(retrieval_fault_codes)
        if retrieval_fault_codes:
            for fault_code in retrieval_fault_codes:
                if fault_code not in codes:
                    codes.append(fault_code)
            scope_review = self._policy_scope_requires_review(request["message"], evidence)
        else:
            if retrieved.get("has_conflict"):
                codes.append("conflicting_sources")
                warnings.append("Retrieved knowledge base sources contain conflicting policy terms. Staff review required.")
            # Knowledge evidence validation: rely on retriever's configured relevance threshold (0.55 default),
            # avoiding dual hidden thresholds or artificial safe-by-refusal.
            retrieval_threshold = getattr(self.retriever, "relevance_threshold", 0.55)
            uncovered_delivery = has_uncovered_cross_border_shipping(request["message"], evidence)
            has_scores = any(item.get("score") is not None for item in evidence)
            max_evidence_score = max((item.get("score") or 0.0) for item in evidence if item.get("score") is not None) if has_scores else 1.0
            ret_reasons = set(retrieved.get("reason_codes", []))
            if "only_expired_documents" in ret_reasons and "only_expired_documents" not in codes:
                codes.append("only_expired_documents")
            if not evidence or uncovered_delivery or (has_scores and max_evidence_score < retrieval_threshold) or "below_relevance_threshold" in ret_reasons:
                if "no_valid_document" not in codes:
                    codes.append("no_valid_document")
            scope_review = self._policy_scope_requires_review(request["message"], evidence)
            if scope_review and "insufficient_evidence" not in codes:
                codes.append("insufficient_evidence")
        documents = []
        for index, item in enumerate(evidence, 1):
            original = next((document for document in self.retriever.eligible_versions if document.doc_id == item["document_id"] and str(document.version) == str(item["version"])), None)
            documents.append({"document_id": item["document_id"], "version": str(item["version"]), "title": item["title"],
                              "snippet": item["excerpt"], "score": item.get("score"), "rank": index, "validity": "valid",
                              "effective_from": str(original.metadata.valid_from) if original else None,
                              "effective_to": str(original.metadata.valid_to) if original and original.metadata.valid_to else None})
        recommendation = (
            "escalate"
            if (
                "human_agent_requested" in codes
                or explicit_authority
                or scope_review
                or is_retrieval_fault
                or recognized_outside_scope
                or explicit_outside_scope_action
            )
            else "abstain"
            if set(codes) & {"low_confidence", "out_of_scope_intent", "no_valid_document", "conflicting_sources"}
            else "draft"
        )
        routing_payload = {"recommendation": recommendation, "reason_codes": codes}
        for rej_key in (
            "selective_accepted",
            "selective_score",
            "selective_threshold",
            "rejected_by_experimental_adapter",
            "rejector_decision",
        ):
            if rej_key in prediction and prediction[rej_key] is not None:
                routing_payload[rej_key] = prediction[rej_key]
        analysis = {"intent": {"label": label, "probability": probability, "confidence_band": "low" if (low or "low_confidence" in codes) else "high" if probability >= .9 else "medium", "source": "staff" if override else "model", "score_kind": "staff_choice" if override else prediction.get("score_kind", "unknown"), "model_mode": "override" if override else prediction.get("model_mode", "unknown"), "verified": False if override else bool(prediction.get("verified", False))},
                    "alternatives": [{"label": item["intent"], "probability": item["probability"], "confidence_band": "low"} for item in candidates if item["intent"] != label][:4],
                    "is_in_scope": label in self.policy["supported_12_intents"], "documents": documents,
                    "routing": routing_payload, "warnings": warnings, "versions": self.versions,
                    "step_latency_ms": {"analysis": round((time.perf_counter() - started) * 1000)}}
        return analysis, evidence

    def analyse(self, request):
        return self._analyse(request)[0]

    def draft(self, request):
        analysis, evidence = self._analyse(request)
        codes = analysis["routing"]["reason_codes"]
        result = {"analysis": analysis, "reason_codes": codes, "versions": self.versions, "step_latency_ms": analysis["step_latency_ms"], "mask_count_by_type": {}}
        if analysis["routing"]["recommendation"] != "draft":
            result["status"] = "escalation_recommended" if analysis["routing"]["recommendation"] == "escalate" else "abstained"
            if result['status'] == 'escalation_recommended':
                result['staff_note'] = 'Escalate this request to authorized staff to resolve the policy or authority issue before replying.'
            elif "low_confidence" in codes:
                result["staff_note"] = "The model score or margin is below the routing threshold. Confirm or correct the intent before drafting."
            return result
        authoritative_evidence = copy.deepcopy(evidence)
        raw_order_context = request.get("order_context")
        supplied_facts = extract_order_facts(
            raw_order_context,
            allowed_fields=ORDER_CONTEXT_ALLOWED_SET,
            include_order_identifiers=False,
        )
        supplied_fields = [field for field in ORDER_CONTEXT_ALLOWED_FIELDS if field in supplied_facts]
        validated_order_input = {
            key: copy.deepcopy(raw_order_context[key]) if isinstance(raw_order_context[key], dict) else supplied_facts[key]
            for key in supplied_facts
        }
        authoritative_sources = build_grounded_sources(
            authoritative_evidence,
            validated_order_input or None,
            include_order_identifiers=True,
        )
        try:
            # The client receives only isolated retrieval evidence and identifier-free allow-listed order fields.
            generated = self.llm.generate(
                request["message"],
                analysis["intent"]["label"],
                copy.deepcopy(authoritative_evidence),
                business_context=copy.deepcopy(validated_order_input),
            )
        except Exception as error:
            code = getattr(error, 'code', 'llm_unavailable')
            failure = 'grounding_failed' if code in ('llm_insufficient_evidence', 'llm_invalid_citations') else 'llm_invalid_output' if code in ('llm_invalid_response',) else 'llm_unavailable'
            err_result = {
                **result,
                "status": "escalation_recommended" if code == 'llm_insufficient_evidence' else "llm_unavailable",
                "reason_codes": list(set(codes) | {failure} | ({'insufficient_evidence'} if code == 'llm_insufficient_evidence' else set())),
                "failure_code": code if code.startswith("llm_") else "llm_unavailable",
                "staff_note": "The LLM timed out after a bounded retry. Try AI again or use the retrieved sources to write a reply." if code == "llm_timeout" else "Draft generation is unavailable. Review the retrieved sources and write a reply manually.",
            }
            if code == 'llm_insufficient_evidence':
                err_result['staff_note'] = 'The retrieved sources cannot answer this request. Escalate for policy clarification before replying.'
            err_usage_dict = getattr(error, "usage", {}) or {}
            err_meta_dict = getattr(error, "metadata", {}) or {}
            err_latency = getattr(error, "latency_seconds", None)
            err_attempts = getattr(error, "attempts", []) or []
            if err_usage_dict or err_meta_dict or err_attempts:
                err_bundle = {"usage": err_usage_dict, "attempts": err_attempts, **err_meta_dict}
                err_usage, err_metadata = self._extract_llm_usage_and_metadata(err_bundle)
                if err_usage:
                    err_result["llm_usage"] = err_usage
                if err_metadata:
                    err_result["llm_metadata"] = err_metadata
            if err_latency is not None:
                err_result["step_latency_ms"] = {
                    **analysis["step_latency_ms"],
                    "llm": round(err_latency * 1000),
                }
            return err_result

        # Preserve complete LLM usage and provenance even if post-generation grounding fails
        llm_usage, llm_metadata = self._extract_llm_usage_and_metadata(generated)
        result["step_latency_ms"] = {**analysis["step_latency_ms"], "llm": round(generated.get("latency_seconds", 0) * 1000)}
        result["llm_usage"] = llm_usage
        if llm_metadata:
            result["llm_metadata"] = llm_metadata

        text = generated.get("body")
        if not isinstance(text, str) or not text.strip():
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
        allowed_placeholders = {match.group() for match in PLACEHOLDER.finditer(request["message"])}
        if any(match.group() not in allowed_placeholders for match in PLACEHOLDER.finditer(text)):
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"llm_invalid_output"})}

        observed_input_snapshot = generated.get("input_snapshot")
        if not validate_snapshot_sources(observed_input_snapshot, authoritative_sources, require_snapshot=True):
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}

        is_clarification = bool(generated.get("is_clarification", False))
        if find_draft_grounding_violation(
            request["message"],
            text,
            authoritative_sources,
            allow_clarification_questions=is_clarification,
        ) is not None:
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}

        if "citations" in generated:
            valid_draft, _, _ = validate_generated_draft(
                request["message"],
                generated,
                authoritative_sources,
                allow_clarification_questions=is_clarification,
            )
            if not valid_draft:
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}

        sources = {str(source.get("source_id") or source.get("id")): source for source in authoritative_sources}
        citations, segments = {}, []
        for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", text.strip())):
            source_ids = re.findall(r"\[(S\d+)\]", paragraph)
            citation_ids = []
            for identifier in source_ids:
                if identifier not in sources:
                    return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
                source = sources[identifier]
                src_type = source.get("source_type")
                if src_type == "policy":
                    doc_id = str(source.get("document_id") or "")
                    doc_ver = str(source.get("version") or "")
                    if not doc_id or not doc_ver:
                        return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
                    citations[identifier] = {"citation_id": identifier, "source_type": "kb_document", "document_id": doc_id, "version": doc_ver, "snippet": source.get("excerpt", "")}
                    citation_ids.append(identifier)
                elif src_type == "order_facts" and supplied_fields:
                    cit_entry = {
                        "citation_id": identifier,
                        "source_type": "order_context",
                        "fields": list(supplied_fields),
                    }
                    if len(supplied_fields) == 1:
                        cit_entry["field"] = supplied_fields[0]
                    citations[identifier] = cit_entry
                    citation_ids.append(identifier)
                else:
                    return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
            if source_ids and not citation_ids:
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
            segments.append({"segment_id": f"segment-{paragraph_index}", "paragraph_index": paragraph_index,
                             "text": re.sub(r"\s*\[S\d+\]", "", paragraph).strip(), "citation_ids": list(dict.fromkeys(citation_ids))})
        if not segments or not citations:
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
        final_codes = list(set(codes) | ({"missing_information"} if is_clarification else set()))
        staff_note = (
            "Customer request lacks required details. A polite clarification draft has been prepared with relevant policy citations for review."
            if is_clarification
            else "Review every claim against its cited source. AI output is supporting information; a person decides what to send."
        )
        return {**result, "status": "draft_ready", "reason_codes": final_codes, "draft": {"segments": segments, "citations": list(citations.values())},
                "staff_note": staff_note}

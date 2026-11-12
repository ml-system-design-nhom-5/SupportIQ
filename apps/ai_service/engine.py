"""Translate existing verified assets into the application AI contract without ticket state."""

from datetime import datetime
import math
import re
import time

PLACEHOLDER = re.compile(r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]")
# Structural heuristic for detecting uncited financial, duration, or policy commitments in short segments.
# NOTE: This regex is a heuristic safety gate only; it does not establish semantic entailment or comprehensive
# factual detection. Human review remains mandatory for all outgoing replies.
FACTUAL_COMMITMENT = re.compile(r"(\$\s*\d+|\b\d+\s*(days?|business days?|hours?|weeks?|months?)\b|\b(refund|refunded|refunds|return window|fee|fees|warranty)\b)", re.I)

# Regulatory, dispute, financial, and policy exception keywords requiring manager authority
SENSITIVE_AUTHORITY_PATTERN = re.compile(
    r"\b("
    r"fraud(?:ulent)?|defraud(?:ed)?"
    r"|lawsuit|legal\s+(?:action|dispute|claim)|attorney|lawyer|court"
    r"|chargeback|dispute[ds]?"
    r"|unauthorized(?:\s+(?:transaction|payment|charge|debit|deduction|activity|use|withdrawal))?"
    r"|not\s+authorized"
    r"|(?:policy|refund|return|order|warranty)\s+exception"
    r"|(?:make|request|grant|demand|ask\s+for|need|want|seek)\s+(?:an?\s+)?exception"
    r"|exception\s+(?:request|to|clause)"
    r")\b",
    re.I,
)


class Engine:
    def __init__(self, model, retriever, llm, versions, policy):
        self.model, self.retriever, self.llm, self.versions, self.policy = model, retriever, llm, versions, policy

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
        if label not in self.policy["supported_12_intents"]:
            codes.append("out_of_scope_intent")
        if label == "human_agent" or re.search(r"\b(human\s+agent|real\s+person|live\s+agent|human\s+operator|talk\s+to\s+a\s+human)\b", request["message"], re.I):
            if "human_agent_requested" not in codes:
                codes.append("human_agent_requested")

        # Escalated intents outside product scope explicitly requested in customer message
        if re.search(r"\b(close\s+(?:my\s+)?account|delete\s+(?:my\s+)?account)\b", request["message"], re.I):
            if "out_of_scope_intent" not in codes:
                codes.append("out_of_scope_intent")

        # External postal pickup scheduling is an escalated intent (return_product_online) outside product scope.
        # Note: In-app Tiki courier pickup (POL-RET-002) is fully supported and must NOT be blocked.
        if re.search(r"\b(?:schedule|book|arrange)\s+(?:a\s+)?postal\s+pickup\b|\bpostal\s+pickup\b", request["message"], re.I):
            if "out_of_scope_intent" not in codes:
                codes.append("out_of_scope_intent")

        # Out-of-domain false positives on tax returns (vs retail product return policy)
        if re.search(r"\b(?:tax\s+return|income\s+tax|corporate\s+tax)\b", request["message"], re.I):
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
        sensitive = (
            label in self.policy.get("sensitive_action_intents", [])
            or prediction.get("intent") in self.policy.get("sensitive_action_intents", [])
            or any(
                item.get("intent") in self.policy.get("sensitive_action_intents", [])
                and item.get("probability", 0) >= self.policy.get("default_margin_threshold", 0.1)
                for item in candidates
            )
            or bool(SENSITIVE_AUTHORITY_PATTERN.search(request["message"]))
        )
        if sensitive:
            if "requires_authority" not in codes:
                codes.append("requires_authority")
        retrieved = self.retriever.retrieve(request["message"], label, role="agent", current_time=datetime.fromisoformat(request["as_of"].replace("Z", "+00:00")))
        evidence = retrieved.get("evidence", [])
        warnings = []
        if retrieved.get("has_conflict"):
            codes.append("conflicting_sources")
            warnings.append("Retrieved knowledge base sources contain conflicting policy terms. Staff review required.")
        # Knowledge evidence validation: rely on retriever's configured relevance threshold (0.55 default),
        # avoiding dual hidden thresholds or artificial safe-by-refusal.
        retrieval_threshold = getattr(self.retriever, "relevance_threshold", 0.55)
        has_scores = any(item.get("score") is not None for item in evidence)
        max_evidence_score = max((item.get("score") or 0.0) for item in evidence if item.get("score") is not None) if has_scores else 1.0
        if not evidence or (has_scores and max_evidence_score < retrieval_threshold) or "below_relevance_threshold" in retrieved.get("reason_codes", []):
            if "no_valid_document" not in codes:
                codes.append("no_valid_document")
        documents = []
        for index, item in enumerate(evidence, 1):
            original = next((document for document in self.retriever.eligible_versions if document.doc_id == item["document_id"] and str(document.version) == str(item["version"])), None)
            documents.append({"document_id": item["document_id"], "version": str(item["version"]), "title": item["title"],
                              "snippet": item["excerpt"], "score": item.get("score"), "rank": index, "validity": "valid",
                              "effective_from": str(original.metadata.valid_from) if original else None,
                              "effective_to": str(original.metadata.valid_to) if original and original.metadata.valid_to else None})
        recommendation = "escalate" if "human_agent_requested" in codes else "abstain" if set(codes) & {"low_confidence", "out_of_scope_intent", "no_valid_document", "conflicting_sources"} else "draft"
        analysis = {"intent": {"label": label, "probability": probability, "confidence_band": "low" if (low or "low_confidence" in codes) else "high" if probability >= .9 else "medium", "source": "staff" if override else "model", "score_kind": "staff_choice" if override else prediction.get("score_kind", "unknown"), "model_mode": "override" if override else prediction.get("model_mode", "unknown"), "verified": False if override else bool(prediction.get("verified", False))},
                    "alternatives": [{"label": item["intent"], "probability": item["probability"], "confidence_band": "low"} for item in candidates if item["intent"] != label][:4],
                    "is_in_scope": label in self.policy["supported_12_intents"], "documents": documents,
                    "routing": {"recommendation": recommendation, "reason_codes": codes}, "warnings": warnings, "versions": self.versions,
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
            if "low_confidence" in codes:
                result["staff_note"] = "The model score or margin is below the routing threshold. Confirm or correct the intent before drafting."
            return result
        try:
            # The legacy client receives only the same identifier-free allow-listed order fields.
            generated = self.llm.generate(request["message"], analysis["intent"]["label"], evidence, business_context=request.get("order_context", {}))
        except Exception as error:
            code = getattr(error, 'code', 'llm_unavailable')
            failure = 'grounding_failed' if code in ('llm_insufficient_evidence', 'llm_invalid_citations') else 'llm_invalid_output' if code in ('llm_invalid_response',) else 'llm_unavailable'
            err_result = {
                **result,
                "status": "llm_unavailable",
                "reason_codes": list(set(codes) | {failure}),
                "failure_code": code if code.startswith("llm_") else "llm_unavailable",
                "staff_note": "The LLM timed out after a bounded retry. Try AI again or use the retrieved sources to write a reply." if code == "llm_timeout" else "Draft generation is unavailable. Review the retrieved sources and write a reply manually.",
            }
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

        text = generated["body"]
        allowed_placeholders = {match.group() for match in PLACEHOLDER.finditer(request["message"])}
        if any(match.group() not in allowed_placeholders for match in PLACEHOLDER.finditer(text)):
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"llm_invalid_output"})}

        # Grounding Guardrail 1: Cosmetics / restricted categories must not overgeneralize.
        # POL-RET-003 excludes cosmetics and chemicals only when protective packaging/seal is unsealed or opened.
        if re.search(r"\b(cosmetics?|chemicals?)\b", text, re.I) and re.search(r"\b(cannot|can't|not eligible|non-returnable|not support returns?|no returns?|do not accept returns?)\b", text, re.I):
            if not re.search(r"\b(unsealed|opened|open package|broken seal)\b", text, re.I):
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}

        # Grounding Guardrail 2: Chargeback / unauthorized payment must NOT receive generic duplicate-charge advice.
        if re.search(r"\b(chargeback|unauthorized\s+(?:transaction|payment|charge)|fraud)\b", request["message"], re.I):
            if re.search(r"\b(duplicate charge|double deduction|charged twice|duplicate deduction)\b", text, re.I) or any(s.get("document_id") == "POL-PAY-004" for s in generated.get("input_snapshot", {}).get("sources", [])):
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}

        sources = {source["source_id"]: source for source in generated["input_snapshot"]["sources"]}
        citations, segments = {}, []
        for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", text.strip())):
            source_ids = re.findall(r"\[(S\d+)\]", paragraph)
            if not source_ids and (len(paragraph) > 40 or FACTUAL_COMMITMENT.search(paragraph)):
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
            citation_ids = []
            for identifier in source_ids:
                if identifier not in sources:
                    return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
                source = sources[identifier]
                if source["source_type"] == "policy":
                    citations[identifier] = {"citation_id": identifier, "source_type": "kb_document", "document_id": source["document_id"], "version": str(source["version"]), "snippet": source["excerpt"]}
                    citation_ids.append(identifier)
                else:
                    for field in ("order_status", "refund_status"):
                        if field in request.get("order_context", {}):
                            order_id = identifier + "_" + field
                            citations[order_id] = {"citation_id": order_id, "source_type": "order_context", "field": field}
                            citation_ids.append(order_id)
            if source_ids and not citation_ids:
                return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
            segments.append({"segment_id": f"segment-{paragraph_index}", "paragraph_index": paragraph_index,
                             "text": re.sub(r"\s*\[S\d+\]", "", paragraph).strip(), "citation_ids": list(dict.fromkeys(citation_ids))})
        if not segments or not citations:
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {"grounding_failed"})}
        is_clarification = generated.get("is_clarification", False)
        final_codes = list(set(codes) | ({"missing_information"} if is_clarification else set()))
        staff_note = (
            "Customer request lacks required details. A polite clarification draft has been prepared with relevant policy citations for review."
            if is_clarification
            else "Review every claim against its cited source. AI output is supporting information; a person decides what to send."
        )
        return {**result, "status": "draft_ready", "reason_codes": final_codes, "draft": {"segments": segments, "citations": list(citations.values())},
                "staff_note": staff_note}

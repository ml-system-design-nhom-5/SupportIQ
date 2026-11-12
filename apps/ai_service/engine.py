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


class Engine:
    def __init__(self, model, retriever, llm, versions, policy):
        self.model, self.retriever, self.llm, self.versions, self.policy = model, retriever, llm, versions, policy

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
        if label == "human_agent":
            codes.append("human_agent_requested")
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
        )
        if sensitive or re.search(r"\b(fraud|lawsuit|legal action|chargeback|unauthorized\s+(?:transaction|payment|charge)|policy exception)\b", request["message"], re.I):
            if "requires_authority" not in codes:
                codes.append("requires_authority")
        retrieved = self.retriever.retrieve(request["message"], label, role="agent", current_time=datetime.fromisoformat(request["as_of"].replace("Z", "+00:00")))
        evidence = retrieved.get("evidence", [])
        warnings = []
        if retrieved.get("has_conflict"):
            codes.append("conflicting_sources")
            warnings.append("Retrieved knowledge base sources contain conflicting policy terms. Staff review required.")
        if not evidence:
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
            return {**result, "status": "llm_unavailable", "reason_codes": list(set(codes) | {failure}), "failure_code": code if code.startswith("llm_") else "llm_unavailable", "staff_note": "The LLM timed out after a bounded retry. Try AI again or use the retrieved sources to write a reply." if code == "llm_timeout" else "Draft generation is unavailable. Review the retrieved sources and write a reply manually."}
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
        result['step_latency_ms'] = {**analysis['step_latency_ms'], 'llm': round(generated.get('latency_seconds', 0) * 1000)}
        result['llm_usage'] = {'input_tokens': generated.get('usage', {}).get('promptTokenCount'), 'output_tokens': generated.get('usage', {}).get('candidatesTokenCount')}
        is_clarification = generated.get("is_clarification", False)
        final_codes = list(set(codes) | ({"missing_information"} if is_clarification else set()))
        staff_note = (
            "Customer request lacks required details. A polite clarification draft has been prepared with relevant policy citations for review."
            if is_clarification
            else "Review every claim against its cited source. AI output is supporting information; a person decides what to send."
        )
        return {**result, "status": "draft_ready", "reason_codes": final_codes, "draft": {"segments": segments, "citations": list(citations.values())},
                "staff_note": staff_note}

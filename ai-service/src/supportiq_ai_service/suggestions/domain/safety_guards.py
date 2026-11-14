"""Shared deterministic safety, scope, and post-generation grounding guards for Engine and PipelineRunner."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence

PLACEHOLDER = re.compile(
    r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]"
)

# Structural heuristic for detecting uncited financial, duration, or policy commitments in short segments.
# NOTE: This regex is a heuristic safety gate only; it does not establish semantic entailment or comprehensive
# factual detection. Human review remains mandatory for all outgoing replies.
FACTUAL_COMMITMENT = re.compile(
    r"(\$\s*\d+|\b\d+\s*(days?|business days?|hours?|weeks?|months?)\b|\b(refund|refunded|refunds|return window|fee|fees|warranty)\b)",
    re.I,
)

# Regulatory, dispute, financial, and policy exception keywords requiring manager authority
SENSITIVE_AUTHORITY_PATTERN = re.compile(
    r"\b("
    r"fraud(?:ulent)?|defraud(?:ed)?"
    r"|lawsuit|legal\s+(?:action|dispute|claim)|attorney|lawyer|court"
    r"|chargeback|dispute[ds]?"
    r"|unauthorized(?:\s+(?:transaction|payment|charge|debit|deduction|activity|use|withdrawal))?"
    r"|(?:transaction|payment|charge|debit|purchase|order|refund)\b[^.,;?!]{0,20}\bnot\s+authorized"
    r"|not\s+authorized\s+(?:by\s+me|to\s+charge)"
    r"|(?:policy|refund|return|order|warranty|manager|supervisor)\s+exception(?!\s+(?:timeline|window|rules?|polic(?:y|ies))\b)"
    r"|(?:make|request|grant|approve|demand|ask\s+for|need|want|seek)\s+(?:an?\s+)?exception"
    r"|exception\s+(?:request|to|clause)"
    r")\b",
    re.I,
)

_MANAGER_ESCALATION_PATTERN = re.compile(
    r"\b(?:human\s+manager|(?:speak|talk|escalate|transfer|connect(?:\s+me)?)\s+(?:to|with)\s+(?:a\s+|an\s+|the\s+|your\s+)?(?:human\s+)?manager)\b",
    re.I,
)

_HUMAN_REQUEST_PATTERN = re.compile(
    r"\b(?:(?:human|real|live)\s+(?:(?:customer|support)\s+){0,2}(?:agent|person|operator|representative|staff)|(?:talk|speak|chat)\s+(?:to|with)\s+(?:a\s+)?human)\b",
    re.I,
)

_ACCOUNT_CLOSURE_PATTERN = re.compile(r"\b(close\s+(?:my\s+)?account|delete\s+(?:my\s+)?account)\b", re.I)
_POSTAL_PICKUP_PATTERN = re.compile(
    r"\b(?:(?:schedule|book|arrange)\s+(?:a\s+)?)?postal\s+pickup\b",
    re.I,
)
_TAX_OOD_PATTERN = re.compile(r"\b(?:tax\s+return|income\s+tax|corporate\s+tax)\b", re.I)

_CROSS_BORDER_PATTERN = re.compile(
    r"\b(?:international|overseas|cross-border)\b.{0,35}\b(?:delivery|shipping)\b",
    re.I,
)

_INTERNAL_POLICY_PATTERN = re.compile(
    r"\b(?:internal|confidential|secret|restricted)\s+(?:staff\s+|audit\s+|company\s+)?(?:manual|procedures?|guidelines?|polic(?:y|ies)|rules?)\b",
    re.I,
)

_POLICY_NOUN = (
    r"(?:polic(?:y|ies)|rules?|terms?|guidelines?|procedures?|manuals?|timelines?|windows?|standards?|clauses?|framework)"
)
_NON_ACTIVE_QUALIFIER = (
    r"(?:unratified|unapproved|proposed|draft|archived|discontinued|expired|legacy|superseded|deprecated)"
)
_NON_POLICY_OBJECT = (
    r"(?!reply\b|replies\b|response\b|message\b|email\b|letter\b|product\b|item\b|goods\b|"
    r"skincare\b|food\b|cosmetic\b|cosmetics\b|medicine\b|voucher\b|coupon\b|parcel\b|package\b)"
    r"[A-Za-z0-9'-]+"
)
_NON_ACTIVE_POLICY_PATTERN = re.compile(
    rf"\b{_NON_ACTIVE_QUALIFIER}\b(?:\s+{_NON_POLICY_OBJECT}){{0,5}}\s+{_POLICY_NOUN}\b"
    rf"|\b{_POLICY_NOUN}\b\s+(?:is|was|are|were|that\s+(?:is|are|was))\s+{_NON_ACTIVE_QUALIFIER}\b",
    re.I,
)

_CONFLICT_TOPIC_PATTERN = re.compile(
    r"\b(polic(?:y|ies)|rules?|terms?|refund|returns?|shipping|cancellation|guidelines?|procedures?|manuals?|compensation|shipments?)\b",
    re.I,
)
_CONFLICT_PHRASE_PATTERN = re.compile(
    r"\b(conflict|contradict\w*|inconsistent)\b"
    r"|\bstates?\s+both\b.+\bfor\s+the\s+same\b"
    r"|\bone\s+(?:section|clause|part|rule|policy)\s+says?\b.+\b(?:and\s+)?another\s+(?:section|clause|part|rule|policy)?\s*says?\b",
    re.I,
)
_CUSTOMS_PATTERN = re.compile(r"\b(?:customs|import\s+dut(?:y|ies))\b", re.I)

_YEAR_PREP_PATTERN = re.compile(
    r"\b(?:in|during|from|since|year|old|before|after|under|for|of)\s+(?:the\s+)?(?:old\s+)?((?:19|20)\d{2})\b(?!\s*(?:VND|USD|EUR|GBP)\b)",
    re.I,
)
_YEAR_BEFORE_POLICY_PATTERN = re.compile(
    rf"\b((?:19|20)\d{{2}})\b(?=(?:\s+[A-Za-z0-9'-]+){{0,4}}\s+{_POLICY_NOUN}\b)",
    re.I,
)
_PURCHASE_EVENT_PREFIX = re.compile(
    r"\b(?:bought|purchased|ordered|received|delivered|placed|made|opened|shipped)\b",
    re.I,
)
_HISTORICAL_CLAUSE_BREAK = re.compile(r"[.,;?!:\n]|\b(?:but|however|actually|yet|though)\b", re.I)

_HUMAN_NEG_PREFIX = re.compile(
    r"\b(?:do\s+not|don't|dont|not|never|no\s+need\s+to|without(?:\s+needing)?)\s+"
    r"(?:(?:want|need|wish|ask(?:ing)?|prefer)\s+)?(?:to\s+)?"
    r"(?:(?:talk|speak|chat|connect|transfer)\s+(?:to|with)\s+)?(?:a\s+)?$",
    re.I,
)
_DISPUTE_NEG_PREFIX = re.compile(
    r"\b(?:there\s+(?:is|was|are)\s+no|no(?:\s+(?:active|open|payment|billing|card))*|"
    r"without(?:\s+any)?|not\s+(?:a|an|any))\s+(?:a\s+|an\s+)?(?:(?:payment|billing|card)\s+)?$",
    re.I,
)
_EXCEPTION_NEG_PREFIX = re.compile(
    r"\b(?:without(?:\s+(?:needing|requiring|asking\s+for|requesting))?|no\s+need\s+for|"
    r"do\s+not\s+need|don't\s+need|not\s+asking\s+for)\s+(?:an?\s+)?$",
    re.I,
)
_ALTERNATIVE_NEG_PREFIX = re.compile(
    r"\b(?:instead\s+of|rather\s+than|not|no|without(?:\s+any)?|free\s+of|excluding)\s+(?:a\s+)?$",
    re.I,
)


def _local_clause_prefix(text: str, start: int) -> str:
    """Return text within the current clause immediately preceding a regex match."""
    last_break = 0
    for m in _HISTORICAL_CLAUSE_BREAK.finditer(text, 0, start):
        last_break = m.end()
    return text[last_break:start]


def has_human_agent_request(text: str) -> bool:
    """Return True if text requests human agent assistance without direct same-clause negation."""
    for m in _HUMAN_REQUEST_PATTERN.finditer(text):
        prefix = _local_clause_prefix(text, m.start())
        if not _HUMAN_NEG_PREFIX.search(prefix):
            return True
    return False


def has_authority_request(text: str) -> bool:
    """Return True for fraud/legal/chargeback/unnegated dispute or manager-authority escalation signals.

    Never applies a broad negation window that would suppress fraud, lawsuit, or chargeback signals.
    """
    for m in SENSITIVE_AUTHORITY_PATTERN.finditer(text):
        token = m.group(0).lower()
        prefix = _local_clause_prefix(text, m.start())
        if token.startswith("disput") and _DISPUTE_NEG_PREFIX.search(prefix):
            continue
        if "exception" in token and _EXCEPTION_NEG_PREFIX.search(prefix):
            continue
        return True
    for m in _MANAGER_ESCALATION_PATTERN.finditer(text):
        prefix = _local_clause_prefix(text, m.start())
        if not _HUMAN_NEG_PREFIX.search(prefix):
            return True
    return False


def has_outside_product_scope_action(text: str) -> bool:
    """Return True for explicitly unsupported account closure or postal pickup requests."""
    if _ACCOUNT_CLOSURE_PATTERN.search(text):
        return True
    for m in _POSTAL_PICKUP_PATTERN.finditer(text):
        prefix = _local_clause_prefix(text, m.start())
        if not _ALTERNATIVE_NEG_PREFIX.search(prefix):
            return True
    return False


def has_tax_ood(text: str) -> bool:
    """Return True for out-of-domain tax return / income tax queries."""
    return bool(_TAX_OOD_PATTERN.search(text))


def evaluate_text_safety(text: str) -> Dict[str, Any]:
    """Evaluate all independent text-level safety/OOD signals without early-return truncation."""
    human = has_human_agent_request(text)
    authority = has_authority_request(text)
    outside_scope = has_outside_product_scope_action(text)
    tax_ood = has_tax_ood(text)

    reason_codes: list[str] = []
    if human:
        reason_codes.append("human_agent_requested")
    if authority:
        reason_codes.append("requires_authority")
    if outside_scope:
        reason_codes.extend(["recognized_outside_product_scope", "out_of_scope_intent"])
    if tax_ood and "out_of_scope_intent" not in reason_codes:
        reason_codes.append("out_of_scope_intent")

    escalate = human or authority or outside_scope
    action: Optional[str] = None
    if escalate:
        action = "escalate"
    elif tax_ood:
        action = "manual_fallback"

    target_queue = "manager" if authority else None
    requested_team = "general_support" if (human and not authority) else None

    return {
        "action": action,
        "reason_codes": reason_codes,
        "target_queue": target_queue,
        "requested_team": requested_team,
        "human_agent_requested": human,
        "requires_authority": authority,
        "outside_product_scope": outside_scope,
        "tax_ood": tax_ood,
    }


def has_uncovered_cross_border_shipping(text: str, evidence: Sequence[Dict[str, Any]]) -> bool:
    """Return True if cross-border/international shipping is queried without matching evidence."""
    return bool(
        _CROSS_BORDER_PATTERN.search(text)
        and not any(_CROSS_BORDER_PATTERN.search(str(item.get("excerpt", "") or "")) for item in evidence)
    )


def _extract_policy_query_years(text: str) -> list[int]:
    years: list[int] = []
    for m in _YEAR_PREP_PATTERN.finditer(text):
        prefix = _local_clause_prefix(text, m.start())
        if _PURCHASE_EVENT_PREFIX.search(prefix) and not _NON_ACTIVE_POLICY_PATTERN.search(prefix):
            continue
        years.append(int(m.group(1)))
    for m in _YEAR_BEFORE_POLICY_PATTERN.finditer(text):
        y = int(m.group(1))
        if y not in years:
            years.append(y)
    return years


def policy_scope_requires_review(
    text: str,
    evidence: Sequence[Dict[str, Any]],
    eligible_versions: Sequence[Any],
) -> bool:
    """Return True when query requests internal, non-active, conflicting, uncovered customs, or out-of-window policy."""
    if _INTERNAL_POLICY_PATTERN.search(text):
        return True
    if _NON_ACTIVE_POLICY_PATTERN.search(text):
        return True

    has_topic = bool(_CONFLICT_TOPIC_PATTERN.search(text))
    if has_topic and _CONFLICT_PHRASE_PATTERN.search(text):
        return True

    for m in _CUSTOMS_PATTERN.finditer(text):
        prefix = _local_clause_prefix(text, m.start())
        if _ALTERNATIVE_NEG_PREFIX.search(prefix):
            continue
        if not any(_CUSTOMS_PATTERN.search(str(item.get("excerpt", "") or "")) for item in evidence):
            return True

    years = _extract_policy_query_years(text)
    if (has_topic or _NON_ACTIVE_POLICY_PATTERN.search(text)) and years:
        matching_docs = [
            doc
            for doc in eligible_versions
            if any(
                doc.doc_id == (item.get("document_id") or item.get("doc_id"))
                and str(doc.version) == str(item.get("version"))
                for item in evidence
            )
        ]
        for year in years:
            if not any(
                int(str(doc.metadata.valid_from)[:4])
                <= year
                <= (int(str(doc.metadata.valid_to)[:4]) if doc.metadata.valid_to else 9999)
                for doc in matching_docs
            ):
                return True

    return False


def evaluate_evidence_scope(
    text: str,
    retrieval_res: Dict[str, Any],
    evidence: Sequence[Dict[str, Any]],
    eligible_versions: Sequence[Any],
) -> Optional[tuple[str, list[str]]]:
    """Validate retrieved evidence non-truncatingly; escalation always beats ordinary abstention."""
    has_conflict = bool(retrieval_res.get("has_conflict"))
    cross_border_gap = has_uncovered_cross_border_shipping(text, evidence)
    scope_review = policy_scope_requires_review(text, evidence, eligible_versions)

    codes: list[str] = []
    if scope_review or has_conflict:
        codes.append("insufficient_evidence")
    if has_conflict:
        codes.append("conflicting_sources")
    if cross_border_gap:
        codes.append("no_valid_document")

    if not codes:
        return None
    if scope_review or has_conflict:
        return ("escalate", codes)
    return ("manual_fallback", codes)


def classify_retrieval_fault(retrieval_res: Dict[str, Any]) -> Optional[list[str]]:
    """Classify typed retrieval encoder faults before falling back to missing-document reasons."""
    status = str(retrieval_res.get("status") or "").strip().lower()
    reasons = {str(code).strip().lower() for code in (retrieval_res.get("reason_codes") or []) if code}

    if status == "encoder_unavailable" or "encoder_unavailable" in reasons:
        return ["insufficient_evidence", "encoder_unavailable"]
    if status in {"encoder_failure", "encoder_failed", "error"} or bool(reasons & {"encoder_failure", "encoder_failed"}):
        return ["insufficient_evidence", "encoder_failure", "encoder_failed"]
    return None


def classify_ml_prediction_fault(prediction: Any) -> list[str]:
    """Map typed IntentPrediction.failure_code (never arbitrary raw error text) to bounded fault codes."""
    code = getattr(prediction, "failure_code", None)
    if code == "ml_timeout":
        return ["ml_timeout", "ml_unavailable"]
    if code == "invalid_model_output":
        return ["invalid_model_output", "ml_unavailable"]
    if code in ("ml_error", "ml_unavailable"):
        return ["ml_error", "ml_unavailable"]
    if getattr(prediction, "error", None):
        return ["ml_error", "ml_unavailable"]
    return []


def has_unqualified_cosmetics_refusal(draft_text: str) -> bool:
    """Detect overgeneralized cosmetics/chemicals return refusal lacking the unsealed/opened condition."""
    if re.search(r"\b(cosmetics?|chemicals?)\b", draft_text, re.I) and re.search(
        r"\b(cannot|can't|not eligible|non-returnable|not support returns?|no returns?|do not accept returns?)\b",
        draft_text,
        re.I,
    ):
        return not bool(re.search(r"\b(unsealed|opened|open package|broken seal)\b", draft_text, re.I))
    return False


def has_unauthorized_duplicate_advice(
    customer_text: str,
    draft_text: str,
    sources: Sequence[Dict[str, Any]],
) -> bool:
    """Detect chargeback/fraud inquiries wrongly given routine duplicate-charge or POL-PAY-004 advice."""
    if re.search(r"\b(chargeback|unauthorized\s+(?:transaction|payment|charge)|fraud)\b", customer_text, re.I):
        if re.search(r"\b(duplicate charge|double deduction|charged twice|duplicate deduction)\b", draft_text, re.I):
            return True
        if any(s.get("document_id") == "POL-PAY-004" for s in sources):
            return True
    return False


def validate_generated_draft(
    customer_text: str,
    llm_result: Any,
    snapshot_sources: Sequence[Dict[str, Any]],
) -> tuple[bool, list[str], Dict[str, Any]]:
    """Validate LLM client output against the grounded GeminiDraftClient body/citations/snapshot contract.

    Preserves inline [S1] markers in valid body output. Rejects uncited factual commitments,
    unknown/mismatched citation IDs, tampered snapshots, unexpected placeholders, and content guardrails.
    """
    if not isinstance(llm_result, dict):
        return (False, ["llm_invalid_output"], {})
    if llm_result.get("answerable") is False:
        return (False, ["grounding_failed"], {})

    body = llm_result.get("body")
    if not isinstance(body, str) or not body.strip():
        return (False, ["llm_invalid_output"], {})

    allowed_placeholders = {m.group() for m in PLACEHOLDER.finditer(customer_text)}
    if any(m.group() not in allowed_placeholders for m in PLACEHOLDER.finditer(body)):
        return (False, ["llm_invalid_output"], {})

    known_by_id: Dict[str, Dict[str, Any]] = {
        str(s["source_id"]): s for s in snapshot_sources if isinstance(s, dict) and s.get("source_id")
    }

    returned_snapshot = llm_result.get("input_snapshot")
    if returned_snapshot is not None:
        if not isinstance(returned_snapshot, dict) or not isinstance(returned_snapshot.get("sources"), list):
            return (False, ["grounding_failed"], {})
        snap_list = returned_snapshot["sources"]
        if not snap_list:
            return (False, ["grounding_failed"], {})
        for snap_src in snap_list:
            if not isinstance(snap_src, dict):
                return (False, ["grounding_failed"], {})
            sid = str(snap_src.get("source_id") or "")
            expected_src = known_by_id.get(sid)
            if expected_src is None:
                return (False, ["grounding_failed"], {})
            if str(snap_src.get("document_id") or "") != str(expected_src.get("document_id") or ""):
                return (False, ["grounding_failed"], {})
            if str(snap_src.get("version") or "") != str(expected_src.get("version") or ""):
                return (False, ["grounding_failed"], {})

    citations_raw = llm_result.get("citations")
    if not isinstance(citations_raw, list) or not citations_raw:
        return (False, ["grounding_failed"], {})

    cited_ids: set[str] = set()
    for item in citations_raw:
        if isinstance(item, str):
            sid = item.strip()
            if sid not in known_by_id:
                return (False, ["grounding_failed"], {})
            cited_ids.add(sid)
        elif isinstance(item, dict):
            sid = str(item.get("source_id") or "").strip()
            expected_src = known_by_id.get(sid)
            if expected_src is None:
                return (False, ["grounding_failed"], {})
            if item.get("document_id") is not None and str(item["document_id"]) != str(expected_src.get("document_id")):
                return (False, ["grounding_failed"], {})
            if item.get("version") is not None and str(item["version"]) != str(expected_src.get("version")):
                return (False, ["grounding_failed"], {})
            cited_ids.add(sid)
        else:
            return (False, ["grounding_failed"], {})

    all_inline: set[str] = set()
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        para_ids = re.findall(r"\[(S\d+)\]", paragraph)
        if not para_ids and (len(paragraph) > 40 or FACTUAL_COMMITMENT.search(paragraph)):
            return (False, ["grounding_failed"], {})
        for sid in para_ids:
            if sid not in known_by_id:
                return (False, ["grounding_failed"], {})
            all_inline.add(sid)

    if not all_inline or cited_ids != all_inline:
        return (False, ["grounding_failed"], {})

    if has_unqualified_cosmetics_refusal(body) or has_unauthorized_duplicate_advice(
        customer_text, body, snapshot_sources
    ):
        return (False, ["grounding_failed"], {})

    provenance = {
        "matched_sources": [
            {
                "source_id": sid,
                "source_type": known_by_id[sid].get("source_type"),
                "document_id": known_by_id[sid].get("document_id"),
                "version": str(known_by_id[sid].get("version")),
            }
            for sid in sorted(all_inline)
        ],
        **{
            k: llm_result[k]
            for k in ("provider", "model", "model_version", "prompt_version")
            if llm_result.get(k) is not None
        },
    }
    return (True, [], provenance)

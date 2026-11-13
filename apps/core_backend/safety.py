"""Shared deterministic safety, scope, and post-generation grounding guards for Engine and PipelineRunner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
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


_CITATION_TAG = re.compile(r"\[(S\d+)\]")
_SENTENCE_BOUNDARY = re.compile(r"([.!?])((?:\s*\[S\d+\])*)(?=\s+(?=[A-Za-z0-9\"'(\[])|\s*$)")
_ABBREVIATION_PREFIX = re.compile(
    r"(?:^|[\s(,])(?:e\.g|i\.e|approx|etc|vs|no|mr|mrs|ms|dr|prof|inc|ltd|dept|est|min|max|avg)$",
    re.I,
)
_NUMBER_TOKEN = re.compile(r"\d+(?:[.,]\d+)*")
_DIGIT_GROUP_RUN = re.compile(r"\d(?:[ .,-]?\d){5,}")
_VND_CURRENCY = re.compile(r"\b(?:VND|vnđ|đ|dong)\b", re.I)

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_ISO_DATE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b")
_MDY_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b",
    re.I,
)
_DMY_DATE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+((?:19|20)\d{2})\b",
    re.I,
)

_POLITE_NON_CLAIM = re.compile(
    r"^(?:"
    r"(?:hi|hello|dear|good\s+(?:morning|afternoon|evening))(?:\s+[^.!?]{0,40})?[!,.]?"
    r"|(?:thank\s+you|thanks)(?:\s+(?:for|so\s+much))?[^.!?]{0,60}[.!]?"
    r"|please\s+(?:let\s+us\s+know|reach\s+out|feel\s+free|share|provide|confirm)[^.!?]{0,80}[.!?]?"
    r"|we(?:'re|\s+are)\s+happy\s+to\s+help[^.!?]{0,40}[.!]?"
    r"|(?:best\s+regards|kind\s+regards|warm\s+regards|sincerely)[,.!]?"
    r"|i\s+understand(?:\s+your\s+concern)?[^.!?]{0,50}[.!]?"
    r")$",
    re.I,
)

_UNCITED_CLAIM_TERMS = re.compile(
    r"\b(?:eligible|ineligible|always|never|guarantee[ds]?|free|price|cost|fee|fees|"
    r"warranty|discount|voucher|hotline|within|arrivals?|arrive[ds]?|credit(?:ed)?|"
    r"process(?:ed|es|ing)?|approv(?:ed?|als?)|cancell?(?:ed|ation)?|refund(?:s|ed|ing)?|"
    r"ship(?:s|ped|ping)?|deliver(?:s|ed|y)?|return(?:s|ed|able)?|replace(?:ment)?|"
    r"order(?:s)?|policy|policies)\b",
    re.I,
)

_DOUBLE_QUOTED_SPAN = re.compile(r'"[^"\n]{1,240}"')
_SINGLE_QUOTED_SPAN = re.compile(r"(?<!\w)'(?:[^'\n]|(?<=\w)'(?=\w)){1,240}'(?!\w)")
_CUSTOMER_ATTRIBUTION = re.compile(
    r"\byou\s+(?:mentioned|said|wrote|stated|noted|reported)\s+(?:that\s+)?"
    r"(?!(?:i|we|our\s+team|support)\b)[^.,;?!\n]{1,120}?"
    r"(?=[.,;?!\n]|\b(?:and|but|so|however)\b|$)",
    re.I,
)

_COMMIT_ACTION = r"(?:cancell?ed|refunded|approved|processed|issued|credited|reimbursed|reversed|executed|completed)"
_COMMIT_SUBJECT = (
    r"(?:order|refund|return(?:\s+request)?|cancellation(?:\s+request)?|"
    r"payment|charge|transaction|replacement|credit|reimbursement|claim|request)"
)
_FIRST_PERSON_COMMIT = re.compile(
    rf"\b(?:I(?:'ve|\s+have)?|we(?:'ve|\s+have)?|our\s+team\s+has|support\s+has|the\s+system\s+has)\s+"
    rf"(?:(?:just|now|already|successfully)\s+)*{_COMMIT_ACTION}\b",
    re.I,
)
_FIRST_PERSON_IMMEDIATE_COMMIT = re.compile(
    rf"\b(?:I(?:'m|\s+am|'ll|\s+will)|we(?:'re|\s+are|'ll|\s+will))\s+"
    rf"(?:(?:now|just|currently|immediately|right\s+now)\s+)*"
    rf"(?:cancell?ing|cancel|refunding|refund|issuing|issue|approving|approve|processing|process)\s+"
    rf"(?:your|the|this)\s+{_COMMIT_SUBJECT}\b",
    re.I,
)
_PASSIVE_COMMIT = re.compile(
    rf"\b(?:your|the|this|a|an)\s+(?:full\s+|partial\s+)?{_COMMIT_SUBJECT}\s+"
    rf"(?:has\s+(?:(?:just|now|already|successfully)\s+)*been|was(?:\s+(?:just|already|successfully))?|is\s+(?:now|already))\s+"
    rf"(?:(?:[a-z]+\s+and|successfully)\s+)*{_COMMIT_ACTION}\b",
    re.I,
)
_COMMIT_NEG_PREFIX = re.compile(
    r"\b(?:not|never|no|unable\s+to|failed\s+to|cannot|can't|won't|will\s+not|"
    r"did\s+not|didn't|has\s+not|hasn't|have\s+not|haven't|without)\s+$",
    re.I,
)
_CONDITIONAL_CLAUSE_PREFIX = re.compile(
    r"\b(?:if|once|when|whenever|unless|until|provided(?:\s+that)?|"
    r"assuming|supposing|in\s+the\s+event(?:\s+that)?|in\s+case|after|before)\s+(?:that\s+)?$",
    re.I,
)
_SENTENCE_START_BREAK = re.compile(r"[.;?!\n]")
_LEADING_CONDITIONAL_CLAUSE = re.compile(
    r"^\s*(?:in\s+the\s+event(?:\s+that)?|if|once|when|whenever|unless|until|provided(?:\s+that)?|in\s+case)\b[^.;?!\n]*,\s*",
    re.I,
)


def split_draft_sentences(text: str) -> list[str]:
    """Split draft into sentences while preserving abbreviations and trailing [S1] citations."""
    sentences: list[str] = []
    for raw_line in re.split(r"\n+", text.strip()):
        line = raw_line.strip()
        if not line:
            continue
        start = 0
        for m in _SENTENCE_BOUNDARY.finditer(line):
            punct, attached_cites = m.group(1), m.group(2)
            if punct == "." and not attached_cites.strip() and _ABBREVIATION_PREFIX.search(line[:m.start()]):
                continue
            part = line[start:m.end()].strip()
            if part:
                sentences.append(part)
            start = m.end()
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _strip_citations_and_placeholders(text: str) -> str:
    cleaned = _CITATION_TAG.sub(" ", text)
    return PLACEHOLDER.sub(" ", cleaned)


def _is_safe_uncited_sentence(sentence: str) -> bool:
    stripped = sentence.strip()
    if not stripped:
        return True
    cleaned = _strip_citations_and_placeholders(stripped).strip()
    if not cleaned:
        return True
    if len(cleaned) > 100:
        return False
    if re.search(r"\d", cleaned) or FACTUAL_COMMITMENT.search(cleaned) or _UNCITED_CLAIM_TERMS.search(cleaned):
        return False
    if has_ungrounded_transaction_commitment(cleaned):
        return False
    return bool(_POLITE_NON_CLAIM.match(cleaned))


def _extract_dates_and_strip(text: str) -> tuple[set[str], str]:
    """Extract canonical YYYY-MM-DD dates and remove them so month/day components cannot justify durations."""
    dates: set[str] = set()
    spans: list[tuple[int, int]] = []

    def _try_add(year_s: str, month: int, day_s: str, span: tuple[int, int]) -> None:
        try:
            iso = date(int(year_s), month, int(day_s)).isoformat()
            dates.add(iso)
            spans.append(span)
        except ValueError:
            pass

    for m in _ISO_DATE.finditer(text):
        _try_add(m.group(1), int(m.group(2)), m.group(3), m.span())
    for m in _MDY_DATE.finditer(text):
        month = _MONTH_MAP.get(m.group(1).lower())
        if month:
            _try_add(m.group(3), month, m.group(2), m.span())
    for m in _DMY_DATE.finditer(text):
        month = _MONTH_MAP.get(m.group(2).lower())
        if month:
            _try_add(m.group(3), month, m.group(1), m.span())

    if not spans:
        return dates, text
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return dates, "".join(chars)


def _canonical_number_value(raw: str, is_vnd_context: bool) -> str:
    """Normalize numeric tokens across decimal, thousands-grouped, currency, and zero-padded forms."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", raw) or re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
        return str(int(re.sub(r"[.,]", "", raw)))
    if re.fullmatch(r"[1-9]\d{0,2}\.\d{3}", raw) and is_vnd_context:
        return str(int(raw.replace(".", "")))
    if "," in raw and "." in raw:
        candidate = raw.replace(",", "")
        try:
            rendered = format(Decimal(candidate), "f")
            return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
        except InvalidOperation:
            return raw
    if "," not in raw:
        try:
            rendered = format(Decimal(raw), "f")
            return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
        except InvalidOperation:
            return raw
    return raw


def _extract_numeric_tokens(text: str) -> tuple[set[str], set[str], set[str], str]:
    """Return canonical numeric tokens, compact digit runs, ISO dates, and date-stripped text."""
    cleaned = _strip_citations_and_placeholders(text)
    dates, non_date_text = _extract_dates_and_strip(cleaned)
    is_vnd = bool(_VND_CURRENCY.search(non_date_text))
    numbers: set[str] = set()
    for m in _NUMBER_TOKEN.finditer(non_date_text):
        raw = m.group(0)
        numbers.add(raw)
        numbers.add(_canonical_number_value(raw, is_vnd))
    compact_runs = {
        digits
        for run in _DIGIT_GROUP_RUN.findall(non_date_text)
        if len(digits := re.sub(r"\D", "", run)) >= 6
    }
    return numbers, compact_runs, dates, non_date_text


def _sentence_has_unsupported_numbers(
    sentence: str,
    cited_sources: Sequence[Dict[str, Any]],
) -> bool:
    """Return True if any date or complete numeric claim in sentence lacks support in its cited sources."""
    sent_nums, sent_runs, sent_dates, sent_non_date = _extract_numeric_tokens(sentence)
    if not sent_nums and not sent_runs and not sent_dates:
        return False
    source_text = "\n".join(str(s.get("text") or s.get("excerpt") or "") for s in cited_sources)
    src_nums, src_runs, src_dates, _ = _extract_numeric_tokens(source_text)
    if not sent_dates.issubset(src_dates):
        return True
    is_vnd = bool(_VND_CURRENCY.search(sent_non_date))
    for m in _NUMBER_TOKEN.finditer(sent_non_date):
        raw = m.group(0)
        canon = _canonical_number_value(raw, is_vnd)
        if raw in src_nums or canon in src_nums or raw in src_runs or canon in src_runs:
            continue
        return True
    for run in sent_runs:
        if run not in src_runs and run not in src_nums:
            return True
    return False


def _sentence_prefix(text: str, pos: int) -> str:
    last = 0
    for m in _SENTENCE_START_BREAK.finditer(text, 0, pos):
        last = m.end()
    return text[last:pos]


def _is_verified_recorded_order_status(
    matched_phrase: str,
    cited_order_sources: Sequence[Dict[str, Any]],
) -> bool:
    """Return True when passive status phrasing strictly reflects cited order_facts values."""
    if not cited_order_sources:
        return False
    fields: dict[str, str] = {}
    for src in cited_order_sources:
        text = str(src.get("text") or src.get("excerpt") or "")
        for line in text.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                fields[key.strip().lower()] = val.strip().lower()
    phrase = matched_phrase.lower()
    order_st = fields.get("order_status", "")
    refund_st = fields.get("refund_status", "")
    payment_st = fields.get("payment_status", "")
    combined_refund = f"{refund_st} {payment_st}"
    if re.search(r"\bcancell?ed\b", phrase):
        return bool(re.search(r"\bcancell?ed\b", order_st))
    if re.search(r"\b(?:refunded|credited|reimbursed)\b", phrase):
        return bool(re.search(r"\b(?:refunded|refund\s+succeeded|credited|reimbursed)\b", combined_refund))
    return False


def has_ungrounded_transaction_commitment(
    draft_text: str,
    cited_order_sources: Sequence[Dict[str, Any]] = (),
) -> bool:
    """Detect assistant transaction-execution claims while preserving quotes, conditionals, and verified order status."""
    masked = _DOUBLE_QUOTED_SPAN.sub(' "QUOTED" ', draft_text)
    masked = _SINGLE_QUOTED_SPAN.sub(" 'QUOTED' ", masked)
    masked = _CUSTOMER_ATTRIBUTION.sub(" ", masked)

    for pattern in (_FIRST_PERSON_COMMIT, _FIRST_PERSON_IMMEDIATE_COMMIT, _PASSIVE_COMMIT):
        for m in pattern.finditer(masked):
            clause_prefix = _local_clause_prefix(masked, m.start())
            if _COMMIT_NEG_PREFIX.search(clause_prefix) or _CONDITIONAL_CLAUSE_PREFIX.search(clause_prefix):
                continue
            if pattern is _FIRST_PERSON_IMMEDIATE_COMMIT and re.search(r"\bwill\b|'ll\b", m.group(0), re.I):
                if _LEADING_CONDITIONAL_CLAUSE.match(_sentence_prefix(masked, m.start())):
                    continue
            if pattern is _PASSIVE_COMMIT and _is_verified_recorded_order_status(m.group(0), cited_order_sources):
                continue
            return True
    return False


def find_draft_grounding_violation(
    customer_text: str,
    draft_body: str,
    snapshot_sources: Sequence[Dict[str, Any]],
) -> Optional[str]:
    """Validate sentence-level citations, evidence-constrained numbers, and transaction commitments."""
    sources_by_id: Dict[str, Dict[str, Any]] = {
        str(s.get("source_id") or s.get("id")): s
        for s in snapshot_sources
        if isinstance(s, dict) and (s.get("source_id") or s.get("id"))
    }
    sentences = split_draft_sentences(draft_body)
    if not sentences:
        return "invalid_citations"

    has_cited_sentence = False
    for sentence in sentences:
        sent_ids = _CITATION_TAG.findall(sentence)
        if not sent_ids:
            if not _is_safe_uncited_sentence(sentence):
                return "uncited_claim"
            continue
        if any(sid not in sources_by_id for sid in sent_ids):
            return "invalid_citations"
        has_cited_sentence = True
        sent_sources = [sources_by_id[sid] for sid in sent_ids]
        if _sentence_has_unsupported_numbers(sentence, sent_sources):
            return "unsupported_number"
        order_sources = [s for s in sent_sources if s.get("source_type") == "order_facts"]
        if has_ungrounded_transaction_commitment(sentence, cited_order_sources=order_sources):
            return "transaction_commitment"

    if not has_cited_sentence:
        return "invalid_citations"
    if has_unqualified_cosmetics_refusal(draft_body) or has_unauthorized_duplicate_advice(
        customer_text, draft_body, snapshot_sources
    ):
        return "grounding_guardrail_failed"
    return None


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

    all_inline = set(_CITATION_TAG.findall(body))
    if not all_inline or not all_inline.issubset(known_by_id) or cited_ids != all_inline:
        return (False, ["grounding_failed"], {})

    if find_draft_grounding_violation(customer_text, body, snapshot_sources) is not None:
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

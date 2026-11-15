"""Shared deterministic safety, scope, and post-generation grounding guards for Engine and PipelineRunner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Optional, Sequence
import unicodedata

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
    r"\b(?:instead\s+of|rather\s+than|not|no|without(?:\s+any)?|free\s+of|excluding|besides|save|barring)\s+(?:a\s+)?$",
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


_ADJ_TRANSPOSITION_TARGETS = (
    "store",
    "stores",
    "shops",
    "retail",
    "branch",
    "branches",
    "storefront",
    "shopfront",
    "showroom",
    "counter",
    "outlet",
    "kiosk",
    "label",
    "labels",
    "prepaid",
    "printable",
    "downloadable",
    "history",
    "purchase",
    "purchases",
    "orders",
    "account",
)
_QUOTE_TRANSLATION = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
    "\u00a0": " ",
})
_CONTRASTIVE_QUOTE_PREFIX = re.compile(r"\b(?:instead\s+of|rather\s+than)\s*[:,\-]?\s*$", re.I)
_UI_OR_SPEECH_QUOTE_PREFIX = re.compile(
    r"\b(?:called|labeled|titled|button|tab|section|page|menu|option|"
    r"said|says|asked|asks|told\s+(?:me|us)|wrote|writes|stated|states|mentioned|mentions|reads?|"
    r"joked|jokes|claimed|claims|suggested|suggests|replied|replies|advised|advises)\s*[:,\-]?\s*$",
    re.I,
)
_QUOTE_FIRST_PERSON_OR_MODAL = re.compile(
    r"\b(?:i|we|i'm|we're|i've|we've|i'd|we'd|let\s+me|let\s+us|"
    r"can|could|would|will|should|shall|may|might|do|does|did|please)\b",
    re.I,
)
_LOCAL_QUOTE_FALSITY = re.compile(
    r"\b(?:wrongly|erroneous(?:ly)?|mistaken(?:ly)?|by\s+mistake|false(?:ly)?|incorrect(?:ly)?)\b",
    re.I,
)
_POST_QUOTE_DISAVOWAL_PREFIX = re.compile(
    r"^\s*(?:[,;:\-]+)?\s*(?:"
    r"(?:by\s+mistake|wrongly|erroneous(?:ly)?|mistaken(?:ly)?|false(?:ly)?|incorrect(?:ly)?)"
    r"(?:\s*[,;:\-]?\s*(?:instead|rather|but))?\b"
    r"|instead(?:\s+of\s+(?:doing\s+)?(?:that|this|it|so))?\b"
    r"|rather(?:\s+than\s+(?:doing\s+)?(?:that|this|it|so))?\b"
    r"|though\s+(?:i|we)\s+actually\b"
    r")",
    re.I,
)
_COVERED_ALT_RETURN_ACTION = re.compile(
    r"\b(?:return(?:ing)?|exchange|exchanging|refund|pickup|pick\s+up|drop[-\s]?off|"
    r"drop\b[^.,;?!\n]{0,20}\boff|collect|upload|courier|post\s+office|steps?|process|"
    r"how\s+do\s+i\s+(?:use|start|initiate))\b",
    re.I,
)
_UNRESOLVED_QUOTE_REFERENCE = re.compile(
    r"\b(?:"
    r"that|there|doing\s+so|such|same|also|too|as\s+well|alongside|along\s+with|either|"
    r"visit(?:ing)?|going|walk(?:ing)?|go\s+(?:there|in|to)|"
    r"this(?!\s+(?:item|order|product|parcel|package|box|shirt|kettle|headset|laptop|"
    r"microwave|printer|keyboard|monitor|lamp|earbuds?)\b)"
    r")\b",
    re.I,
)
_POST_QUOTE_CLAUSE_SPLIT = re.compile(
    r"[.;!\n?]+|\s+-\s+|--|\b(?:and|or|but|while|whereas|before|after|alongside|plus)\b",
    re.I,
)
_CHANNEL_RETURN_VERB = re.compile(
    r"\b(?:return(?:ing|ed)?|exchange|exchanging|swap(?:ping)?|"
    r"drop(?:ping)?(?:\s+\w+){0,4}\s+off|"
    r"bring(?:ing)?(?:\s+\w+){0,4}\s+(?:back|in)|"
    r"hand(?:ing)?(?:\s+\w+){0,4}\s+in|"
    r"send(?:ing)?(?:\s+\w+){0,4}\s+back|"
    r"ship(?:ping)?(?:\s+\w+){0,4}\s+back|"
    r"take(?:\s+\w+){0,4}\s+back)\b",
    re.I,
)
_STORE_PURCHASE_CONTEXT = re.compile(
    r"\b(?:bought|purchased|ordered|received|delivered|picked\s+up|collected|obtained|got|sold\s+by)\b",
    re.I,
)
_ONLINE_OR_DIGITAL_STORE_MODIFIER = re.compile(
    r"\b(?:online|web|app|google\s+play|play|apple|digital|virtual|e[-\s]?commerce)\s+$",
    re.I,
)
_STORE_NON_CHANNEL_SUFFIX = re.compile(
    r"^\s*(?:credits?|wallets?|vouchers?|cards?|balances?|polic(?:y|ies))\b",
    re.I,
)
_NEG_CHANNEL_INTRANSITIVE_VERBS = (
    r"go(?:ing)?|travel(?:ing|ling)?|walk(?:ing)?|head(?:ing)?|driv(?:e|ing)|"
    r"commut(?:e|ing)|com(?:e|ing)|visit(?:ing)?|stop(?:ping)?(?:\s+by)?|"
    r"drop(?:ping)?\s+in|wait(?:ing)?|stay(?:ing)?|leav(?:e|ing)|keep(?:ing)?|"
    r"ask(?:ing)?|mail(?:ing)?|print(?:ing)?|download(?:ing)?|generat(?:e|ing)|us(?:e|ing)"
)
_NEG_CHANNEL_TRANSITIVE_VERBS = (
    r"return(?:ing)?|bring(?:ing)?|tak(?:e|ing)|drop(?:ping)?|hand(?:ing)?|"
    r"send(?:ing)?|ship(?:ping)?|carry(?:ing)?|deliver(?:ing)?|exchang(?:e|ing)|swap(?:ping)?"
)
_NEG_CLAUSE_BOUNDARY_WORDS = (
    r"and|or|but|so|yet|though|although|however|actually|whereas|while|"
    r"except|without|unless|excluding|besides|save|barring|instead|rather|only|just|not|never|neither|nor|still|also|"
    r"if|when|where|because|since|until|then|before|after|whether|than|"
    r"to|for|from|by|at|in|into|onto|on|via|with|"
    r"am|is|are|was|were|be|been|being|do|does|did|have|has|had|"
    r"can|could|will|would|shall|should|may|might|must|"
    r"i|we|you|he|she|they|i'm|i'll|i'd|we're|we'll|we'd|you're|you'll|let|let's|"
    r"someone|anyone|everyone|please|"
    r"want|need|plan|prefer|like|wish|try|trying|allow|accept|process|handle"
)
_NEG_CHANNEL_TRANSITIVE_ACTION = (
    r"(?:return(?:ing)?|bring(?:ing)?(?:\s+(?:back|in))?|tak(?:e|ing)(?:\s+back)?|"
    r"drop(?:ping)?(?:\s+off)?|hand(?:ing)?(?:\s+in)?|send(?:ing)?(?:\s+back)?|"
    r"ship(?:ping)?(?:\s+back)?|carry(?:ing)?|deliver(?:ing)?|exchang(?:e|ing)|swap(?:ping)?)"
)
_NEG_NON_OBJECT_TOKEN = re.compile(
    rf"\b(?:{_NEG_CLAUSE_BOUNDARY_WORDS}|{_NEG_CHANNEL_INTRANSITIVE_VERBS}|{_NEG_CHANNEL_TRANSITIVE_VERBS})\b",
    re.I,
)
_NEG_OBJECT_NP_WORD = (
    rf"(?!(?:{_NEG_CLAUSE_BOUNDARY_WORDS}|{_NEG_CHANNEL_INTRANSITIVE_VERBS}|{_NEG_CHANNEL_TRANSITIVE_VERBS})\b)"
    r"[A-Za-z0-9'](?:[A-Za-z0-9'-]{0,28}[A-Za-z0-9'])?"
)
_NEG_CHANNEL_ACTION_CLAUSE = (
    rf"(?:"
    rf"{_NEG_CHANNEL_TRANSITIVE_ACTION}(?:\s+{_NEG_OBJECT_NP_WORD}){{1,5}}(?:\s+(?:back|off|in))?"
    rf"|{_NEG_CHANNEL_TRANSITIVE_VERBS}|{_NEG_CHANNEL_INTRANSITIVE_VERBS}"
    rf")"
)
_STORE_CHANNEL_VERB_PREFIX_SPLIT = re.compile(
    rf"^({_NEG_CHANNEL_TRANSITIVE_ACTION})\s+(.+?)\s+(?=(?:at|to|in|into)\b|in[-\s]+person\b)",
    re.I,
)
_COVERED_RETURN_ALTERNATIVE_PATTERN = re.compile(
    r"\b(?:"
    r"(?:shipping\s+)?couriers?"
    r"|(?:designated\s+)?(?:partner\s+)?post\s+office\s+(?:drop[-\s]?off|steps?|returns?)"
    r"|(?:designated\s+|partner\s+)post\s+offices?"
    r"|order\s+management"
    r"|(?:tiki\s+)?app\b"
    r"|(?:in|on|via|through)\s+(?:the\s+)?app\b"
    r"|(?:return|exchange)(?:ing)?\s+online"
    r"|online\s+(?:return|exchange|courier|pickup)"
    r")\b",
    re.I,
)
_DECLARATIVE_NEGATION_STEM = (
    r"no\s+need\s+(?:for|to)"
    r"|(?:i|we)(?:'d|\s+would)?\s+(?:prefer\s+not\s+to|rather\s+not)"
    r"|(?:i|we)\s+(?:do\s+not|don't|did\s+not|didn't|cannot|can\s+not|can't|could\s+not|couldn't|will\s+not|won't|would\s+not|wouldn't)"
    r"|(?:(?:i'm|we're|(?:i|we)\s+(?:am|are))\s+not|we\s+aren't)(?:\s+(?:going|planning|willing|trying|looking|asking))?"
    r"|(?:i'm|we're|(?:i|we)\s+(?:am|are))\s+unable"
    r"|without(?:\s+(?:going|traveling|walking|heading|driving|visiting|needing|having|using|printing|downloading))?"
)
_ALT_CLAUSE_REJECTION = re.compile(
    rf"(?:\b(?:{_DECLARATIVE_NEGATION_STEM})\b[^.,;?!\n]*$"
    r"|\b(?:instead\s+of|rather\s+than)\b(?:\s+(?:waiting\s+for|using|booking|getting|trying|relying\s+on))?\s*(?:a\s+|an\s+|the\s+)?$"
    r"|\b(?:not|never|without|neither|nor)\s+(?:waiting\s+for|using|booking|getting|having|needing)\s*(?:a\s+|an\s+|the\s+)?$"
    r"|\bno\s+(?:available\s+|free\s+)?$)",
    re.I,
)
_ALT_CLAUSE_POST_NEG = re.compile(
    r"^(?:\s+(?!for\b|at\b|on\b|in\b|to\b|with\b|via\b|from\b|how\b|when\b|where\b|can\b|could\b|will\b|would\b|should\b)[A-Za-z'-]+){0,2}\s+"
    r"(?:"
    r"(?:is|are|was|were|does|do|did|will|would|can|could)\s+not\b"
    r"|(?:isn't|aren't|doesn't|don't|didn't|won't|wouldn't|can't|cannot|couldn't)\b"
    r"|(?:(?:is|are|was|were|seems?|appears?|looks?)\s+)?(?:(?:currently|temporarily|completely|totally|still)\s+)?"
    r"(?:unavailable|unusable|offline|down|broken|disabled|closed)\b"
    r")",
    re.I,
)
_DECLARATIVE_CHANNEL_NEG_PREFIX = re.compile(
    rf"\b(?:{_DECLARATIVE_NEGATION_STEM})"
    r"(?:\s+(?:want|need|wish|plan|expect|intend|prefer|like|have|be\s+able|able))?"
    rf"(?:\s+(?:to|for))?(?:\s+{_NEG_CHANNEL_ACTION_CLAUSE})?"
    r"(?:\s+(?:to|into|at|for|with|any|a|an|the|my|your))*\s*$",
    re.I,
)
_INSTEAD_OF_PREFIX = re.compile(r"\b(?:instead\s+of|rather\s+than)\b([^.,;?!\n]*)$", re.I)
_REQUEST_MODAL_VERB = re.compile(r"\b(?:want|need|would|can|could|will|prefer|ask|please)\b", re.I)
_COURIER_PICKUP_CONTEXT = re.compile(
    r"\b(?:courier|driver|rider|delivery)\b[^.,;?!\n]{0,45}\b(?:pick(?:ing)?\s+up|pickup|collect(?:ing)?)\b",
    re.I,
)

_PHYSICAL_VENUE_NOUN = r"(?:stores?|shops?|storefronts?|shopfronts?|branch(?:es)?|showrooms?|outlets?|kiosks?)"
_PHYSICAL_VENUE_STRICT_MOD = r"(?:physical|retail|brick[-\s]+and[-\s]+mortar)"
_PHYSICAL_VENUE_ANY_MOD = (
    r"(?:physical|retail|local|brick[-\s]+and[-\s]+mortar|walk[-\s]+in|"
    r"mall(?:\s+pop[-\s]+up)?|pop[-\s]+up|tiki(?:\s+retail)?|brand|flagship)"
)
_PHYSICAL_STORE_CHANNEL_PATTERN = re.compile(
    r"\b(?:"
    r"in[-\s]+(?:stores?|shops?)"
    rf"|(?:at|to|into|walk\s+in(?:to)?|visit(?:ing)?)\s+(?:a|an|any|your|the|one\s+of\s+(?:your|the)|nearest|closest|local)?\s*"
    rf"(?:{_PHYSICAL_VENUE_ANY_MOD}\s+)*{_PHYSICAL_VENUE_NOUN}(?:\s+(?:branch|counter|location|desk)s?)?"
    rf"|{_PHYSICAL_VENUE_STRICT_MOD}\s+(?:{_PHYSICAL_VENUE_ANY_MOD}\s+)*(?:{_PHYSICAL_VENUE_NOUN}|locations?|counters?)"
    rf"|(?:{_PHYSICAL_VENUE_ANY_MOD}\s+)?{_PHYSICAL_VENUE_NOUN}\s+(?:branch|counter|drop[-\s]?off|return|exchange)s?"
    rf"|(?:(?:a|an|any|your|the|local|nearest)\s+)?(?:{_PHYSICAL_VENUE_ANY_MOD}\s+)*{_PHYSICAL_VENUE_NOUN}(?:\s+counters?)?\s+"
    rf"(?:accept|take|handle|process)(?:s|ing)?\s+(?:[\w-]+\s+){{0,4}}(?:returns?|exchanges?|drop[-\s]?offs?)"
    rf"|(?:accept|take|handle|process)(?:s|ing)?\s+(?:[\w-]+\s+){{0,3}}in[-\s]+person\s+(?:[\w-]+\s+){{0,2}}(?:returns?|exchanges?|drop[-\s]?offs?)"
    rf"|(?:return(?:ing)?|exchange|exchanging|swap(?:ping)?|drop(?:ping)?(?:\s+\w+){{0,4}}\s+off|"
    rf"bring(?:ing)?(?:\s+\w+){{0,4}}\s+(?:back|in)|take(?:\s+\w+){{0,4}}\s+back|hand(?:ing)?(?:\s+\w+){{0,4}}\s+in)\s+"
    rf"(?:[\w-]+\s+){{0,3}}(?:(?:at|to|in|into)\s+(?:a|an|any|your|the|one\s+of\s+(?:your|the)|local|nearest|closest)?\s*(?:{_PHYSICAL_VENUE_ANY_MOD}\s+)*{_PHYSICAL_VENUE_NOUN}|in[-\s]+person)"
    r")\b",
    re.I,
)
_PREPAID_RETURN_LABEL_PATTERN = re.compile(
    r"\b(?:"
    r"(?:pre[-\s]?paid|printable|downloadable|self[-\s]?print(?:ed)?)\s+(?:[\w-]+\s+){0,2}(?:return(?:\s+shipping)?|shipping)\s+labels?"
    r"|(?:return(?:\s+shipping)?|shipping)\s+label\s+(?:portals?|downloads?|pdfs?|links?|pages?|buttons?|tools?|generators?)"
    r"|(?:print(?:ing)?|download(?:ing)?|generat(?:e|ing)|reprint(?:ing)?)\s+"
    r"(?:[\w-]+\s+){0,3}(?:(?:return(?:\s+shipping)?|shipping)\s+labels?)"
    r"|(?:email|send)\s+(?:me\s+)?(?:a|the)?\s*(?:pre[-\s]?paid|printable|downloadable|self[-\s]?print(?:ed)?)\s+(?:[\w-]+\s+){0,2}(?:return(?:\s+shipping)?|shipping)\s+labels?"
    r")\b",
    re.I,
)
_FULL_ORDER_HISTORY_PATTERN = re.compile(
    r"\b(?:"
    r"(?:full|entire|complete|whole|lifetime|total|account)\s+"
    r"(?:(?:account|personal|customer|online)\s+)?(?:orders?|purchases?)\s+(?:history|logs?|lists?|records?|summary)"
    r"|(?:list|log|history|records?|summary)\s+of\s+(?:all(?:\s+of)?\s+)?(?:(?:my|the)\s+)?(?:past\s+|previous\s+|historical\s+|older\s+)?(?:orders?|purchases?)"
    r"|(?:show(?:ing)?|list(?:ing)?|view(?:ing)?|see(?:ing)?|get(?:ting)?|export(?:ing)?|download(?:ing)?|pull(?:ing)?(?:\s+up)?|send(?:ing)?(?:\s+me)?|retriev(?:e|ing)|access(?:ing)?|display(?:ing)?)\s+"
    r"(?:[\w-]+\s+){0,2}(?:"
    r"(?:all(?:\s+of)?(?:\s+my)?|every)\s+(?:(?:past|previous|historical|older|prior)\s+)*(?:orders|purchases|past\s+purchase|historical\s+order|previous\s+purchase)"
    r"|(?:my|the)\s+(?:full|entire|complete|whole)\s+(?:[\w-]+\s+){0,1}(?:orders?|purchases?)(?:\s+(?:history|logs?|lists?|records?|summary))?"
    r"|(?:my|the)\s+(?:past|previous|historical)\s+(?:(?:orders|purchases)|(?:order|purchase)s?\s+(?:history|logs?|lists?|records?|summary))"
    r"|(?:(?:my|the)\s+)?(?:order|purchase)\s+history(?!\s+(?:for|of)\s+(?:order\s+)?(?:#?\d+|ORD-\w+|this\s+order))"
    r")"
    r"|(?:all(?:\s+of)?(?:\s+my)?|every)\s+(?:(?:past|previous|historical|older|prior)\s+)+(?:orders|purchases)(?:\s+i(?:'ve|\s+have)?\s+(?:ever\s+)?(?:placed|made))?"
    r"|every\s+(?:past\s+|previous\s+|historical\s+)?(?:order|purchase)(?:\s+i(?:'ve|\s+have)?\s+(?:ever\s+)?(?:placed|made)|(?:\s+in|\s+under)\s+(?:my|the)\s+(?:account|login))"
    r")\b",
    re.I,
)


def _is_adjacent_transposition(token: str, target: str) -> bool:
    """Return True if lowercase token is a single adjacent-letter transposition of a >=5-char target."""
    if len(target) < 5 or len(token) != len(target) or token == target:
        return False
    diffs = [i for i, (a, b) in enumerate(zip(token, target)) if a != b]
    return (
        len(diffs) == 2
        and diffs[1] == diffs[0] + 1
        and token[diffs[0]] == target[diffs[1]]
        and token[diffs[1]] == target[diffs[0]]
    )


def _normalize_scope_text(text: str) -> str:
    """Normalize Unicode compatibility forms, quotes/dashes, spacing, and >=5-char channel transpositions."""
    norm = unicodedata.normalize("NFKC", text).translate(_QUOTE_TRANSLATION)
    norm = re.sub(r"[\u200b-\u200d\ufeff]", "", norm)
    norm = re.sub(r"[ \t\r\f\v]+", " ", norm)

    def _fix_transposition(m: re.Match[str]) -> str:
        word = m.group(0)
        low = word.lower()
        for target in _ADJ_TRANSPOSITION_TARGETS:
            if _is_adjacent_transposition(low, target):
                return target
        return word

    return re.sub(r"\b[A-Za-z]{5,14}\b", _fix_transposition, norm)


def _clause_before(text: str, pos: int) -> str:
    """Return text within the current clause before pos, splitting on punctuation/contrast and spaced dashes."""
    prefix = _local_clause_prefix(text, pos)
    last_dash = max(prefix.rfind(" - "), prefix.rfind("--"))
    if last_dash != -1:
        dash_len = 3 if prefix[last_dash : last_dash + 3] == " - " else 2
        prefix = prefix[last_dash + dash_len :]
    return prefix


def _clause_after(text: str, pos: int) -> str:
    """Return text within the current clause immediately following a regex match."""
    tail = text[pos:]
    end = len(tail)
    for m in _HISTORICAL_CLAUSE_BREAK.finditer(tail):
        end = min(end, m.start())
        break
    for sep in (" - ", "--"):
        idx = tail.find(sep)
        if idx != -1:
            end = min(end, idx)
    return tail[:end]


def _is_covered_alt_clause_negated(prefix: str, suffix: str) -> bool:
    """Return True when a covered-alternative mention is negated in its local clause."""
    return bool(
        _ALTERNATIVE_NEG_PREFIX.search(prefix)
        or _ALT_CLAUSE_REJECTION.search(prefix)
        or _ALT_CLAUSE_POST_NEG.search(suffix)
    )


def _has_covered_return_alternative_request(text: str, *, require_return_action: bool = False) -> bool:
    """Return True when context affirmatively names an unnegated approved return alternative."""
    for m in _COVERED_RETURN_ALTERNATIVE_PATTERN.finditer(text):
        prefix = _clause_before(text, m.start())
        suffix = _clause_after(text, m.end())
        if _is_covered_alt_clause_negated(prefix, suffix):
            continue
        if require_return_action and not _COVERED_ALT_RETURN_ACTION.search(f"{prefix}{m.group(0)}{suffix}"):
            continue
        return True
    return False


def _post_quote_is_exclusively_covered(local_post: str, *, has_prefix_disavowal: bool) -> bool:
    """Require local explicit disavowal and verify every subsequent clause exclusively asks for an approved return alternative."""
    post_m = _POST_QUOTE_DISAVOWAL_PREFIX.match(local_post)
    if post_m:
        rem = local_post[post_m.end() :]
    elif has_prefix_disavowal:
        rem = re.sub(r"^\s*(?:[,;:\-]+)?\s*(?:(?:and|but)\s+)?", "", local_post, flags=re.I)
    else:
        return False

    rem = re.sub(r"^\s*[,;:\-\s]+", "", rem).strip()
    if not rem or _UNRESOLVED_QUOTE_REFERENCE.search(rem):
        return False

    clauses = [c.strip(" ,;:\t-") for c in _POST_QUOTE_CLAUSE_SPLIT.split(rem)]
    non_empty = [c for c in clauses if c]
    if not non_empty:
        return False
    return all(_has_covered_return_alternative_request(c, require_return_action=True) for c in non_empty)


def _collect_non_overlapping_quotes(text: str) -> list[re.Match[str]]:
    """Collect non-overlapping quoted spans sorted left-to-right."""
    candidates = sorted(
        [m for pat in (_DOUBLE_QUOTED_SPAN, _SINGLE_QUOTED_SPAN) for m in pat.finditer(text)],
        key=lambda m: (m.start(), -m.end()),
    )
    ordered: list[re.Match[str]] = []
    last_end = -1
    for m in candidates:
        if m.start() >= last_end:
            ordered.append(m)
            last_end = m.end()
    return ordered


def _quote_bounds_and_prefix(text: str, matches: list[re.Match[str]], idx: int) -> tuple[str, str]:
    """Return strictly bounded (local_prefix, local_post) isolated from other quotes."""
    m = matches[idx]
    prev_end = matches[idx - 1].end() if idx > 0 else 0
    next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)

    punct_m = re.search(r"[:,\-]\s*$", text[prev_end : m.start()])
    attr_pos = prev_end + punct_m.start() if punct_m else m.start()
    pre_slice = text[prev_end:attr_pos]
    local_prefix = _clause_before(pre_slice, len(pre_slice)) + text[attr_pos : m.start()]

    post_end = next_start
    if idx + 1 < len(matches):
        rel = text[m.end() : next_start]
        next_punct = re.search(r"[:,\-]\s*$", rel)
        next_attr_rel = next_punct.start() if next_punct else len(rel)
        next_intro = _clause_before(rel, next_attr_rel)
        cut_rel = next_attr_rel - len(next_intro)
        if cut_rel > 0:
            post_end = m.end() + cut_rel

    return local_prefix, text[m.end() : post_end]


def _mask_attributed_quotes(text: str) -> str:
    """Retain unsupported capability quotes by default; blank ONLY with positive local disavowal and exclusive covered alternative."""
    matches = _collect_non_overlapping_quotes(text)
    if not matches:
        return text
    chars = list(text)
    for idx, m in enumerate(matches):
        if not _PHYSICAL_STORE_CHANNEL_PATTERN.search(m.group(0)):
            continue
        local_prefix, local_post = _quote_bounds_and_prefix(text, matches, idx)
        contrast_m = _CONTRASTIVE_QUOTE_PREFIX.search(local_prefix)
        quote_m = None if contrast_m else _UI_OR_SPEECH_QUOTE_PREFIX.search(local_prefix)
        if not contrast_m and not quote_m:
            continue
        pre_attr = local_prefix[: (contrast_m or quote_m).start()]
        if _QUOTE_FIRST_PERSON_OR_MODAL.search(pre_attr):
            continue
        has_prefix_disavowal = bool(contrast_m or _LOCAL_QUOTE_FALSITY.search(local_prefix))
        if not _post_quote_is_exclusively_covered(local_post, has_prefix_disavowal=has_prefix_disavowal):
            continue
        for pos in range(m.start(), m.end()):
            chars[pos] = " "
    return "".join(chars)


def _is_negated_channel_alternative(text: str, start: int, matched_text: str = "") -> bool:
    """Return True when a channel match is cleanly declined with pure NP syntax rather than exception/contrast."""
    if matched_text:
        split_m = _STORE_CHANNEL_VERB_PREFIX_SPLIT.match(matched_text)
        if split_m:
            interior = re.sub(r"\s+(?:back|off|in)$", "", split_m.group(2), flags=re.I)
            if _NEG_NON_OBJECT_TOKEN.search(interior):
                return False
    prefix = _local_clause_prefix(text, start)
    if _DECLARATIVE_CHANNEL_NEG_PREFIX.search(prefix):
        return True
    instead_match = _INSTEAD_OF_PREFIX.search(prefix)
    if instead_match:
        tail = instead_match.group(1)
        if not _REQUEST_MODAL_VERB.search(tail) and not re.search(r"\s-\s|--", tail):
            return True
    return False


def _is_non_return_store_context(text: str, start: int, end: int, matched_text: str = "") -> bool:
    """Return True for purchase-in-store facts, digital/online stores, courier in-person pickup, or store-credit mentions."""
    if _STORE_NON_CHANNEL_SUFFIX.match(text[end : end + 24]):
        return True
    prefix = _local_clause_prefix(text, start)
    if re.search(r"\bin[-\s]+person\b", matched_text, re.I) and _COURIER_PICKUP_CONTEXT.search(prefix + text[start:end]):
        return True
    if _CHANNEL_RETURN_VERB.search(matched_text) or re.search(
        r"\b(?:accept|take|handle|process)(?:s|ing)?\b", matched_text, re.I
    ):
        return False
    if _ONLINE_OR_DIGITAL_STORE_MODIFIER.search(prefix) and not _CHANNEL_RETURN_VERB.search(prefix):
        return True
    purchase_matches = list(_STORE_PURCHASE_CONTEXT.finditer(prefix))
    if not purchase_matches:
        return False
    last_purchase_end = purchase_matches[-1].end()
    return_matches = list(_CHANNEL_RETURN_VERB.finditer(prefix))
    last_return_end = return_matches[-1].end() if return_matches else -1
    if last_purchase_end > last_return_end and not re.search(r"\bonline\b", prefix[last_purchase_end:], re.I):
        return True
    return False


def _trusted_policy_docs(evidence: Sequence[Dict[str, Any]], eligible_versions: Sequence[Any]) -> list[Any]:
    """Return approved active PolicyVersion docs strictly matching retrieved source_type='policy' items."""
    trusted: list[Any] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in evidence:
        if not isinstance(item, dict) or item.get("source_type") != "policy":
            continue
        item_id = item.get("document_id") or item.get("doc_id")
        item_ver = item.get("version")
        if not isinstance(item_id, str) or item_ver is None:
            continue
        key = (item_id, str(item_ver))
        if key in seen_keys:
            continue
        for doc in eligible_versions:
            if getattr(doc, "doc_id", None) != item_id or str(getattr(doc, "version", None)) != str(item_ver):
                continue
            meta = getattr(doc, "metadata", None)
            status = getattr(meta, "status", None)
            if isinstance(status, str) and status != "approved":
                continue
            trusted.append(doc)
            seen_keys.add(key)
            break
    return trusted


def _trusted_docs_cover_capability(trusted_docs: Sequence[Any], capability: str) -> bool:
    """Verify whether trusted approved policy docs explicitly grant the requested channel/capability."""
    cap_aliases = {
        "physical_store_return": {"in_store_return", "retail_store_return", "store_drop_off"},
        "prepaid_return_label": {"prepaid_return_label", "return_label_portal", "printable_return_label"},
        "full_order_history": {"order_history", "purchase_history", "full_order_history"},
    }
    text_evidence_patterns = {
        "physical_store_return": re.compile(
            r"\b(?:return|drop\s+off|exchange)\b[^.\n]{0,40}\b(?:in[-\s]+(?:stores?|shops?)|retail\s+(?:stores?|shops?)|physical\s+(?:stores?|shops?)|storefronts?|shopfronts?|branch(?:es)?)\b",
            re.I,
        ),
        "prepaid_return_label": re.compile(
            r"\b(?:pre[-\s]?paid|printable|downloadable)?\s*(?:return|shipping)\s+label\b",
            re.I,
        ),
        "full_order_history": re.compile(r"\b(?:order|purchase)\s+history\b", re.I),
    }
    allowed_caps = cap_aliases[capability]
    text_pat = text_evidence_patterns[capability]
    for doc in trusted_docs:
        meta = getattr(doc, "metadata", None)
        raw_caps = getattr(meta, "answer_capabilities", None)
        if isinstance(raw_caps, (list, tuple)) and any(isinstance(c, str) and c in allowed_caps for c in raw_caps):
            return True
        raw_content = getattr(doc, "content", None)
        if isinstance(raw_content, str) and text_pat.search(raw_content):
            return True
    return False


def _has_uncovered_channel_or_capability(
    text: str,
    evidence: Sequence[Dict[str, Any]],
    eligible_versions: Sequence[Any],
) -> bool:
    """Return True if non-empty evidence would otherwise be served for an uncovered channel/capability."""
    if not evidence:
        return False
    normalized = _mask_attributed_quotes(_normalize_scope_text(text))
    requested: list[str] = []
    has_covered_return_alt = _has_covered_return_alternative_request(normalized)

    for m in _PHYSICAL_STORE_CHANNEL_PATTERN.finditer(normalized):
        if has_covered_return_alt and _is_negated_channel_alternative(normalized, m.start(), m.group(0)):
            continue
        if _is_non_return_store_context(normalized, m.start(), m.end(), m.group(0)):
            continue
        requested.append("physical_store_return")
        break

    for m in _PREPAID_RETURN_LABEL_PATTERN.finditer(normalized):
        if not _is_negated_channel_alternative(normalized, m.start()):
            requested.append("prepaid_return_label")
            break

    for m in _FULL_ORDER_HISTORY_PATTERN.finditer(normalized):
        if not _is_negated_channel_alternative(normalized, m.start()):
            requested.append("full_order_history")
            break

    if not requested:
        return False

    trusted_docs = _trusted_policy_docs(evidence, eligible_versions)
    return any(not _trusted_docs_cover_capability(trusted_docs, cap) for cap in requested)


def policy_scope_requires_review(
    text: str,
    evidence: Sequence[Dict[str, Any]],
    eligible_versions: Sequence[Any],
) -> bool:
    """Return True when query requests internal, non-active, conflicting, uncovered customs/capability, or out-of-window policy."""
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

    if _has_uncovered_channel_or_capability(text, evidence, eligible_versions):
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
_SENTENCE_BOUNDARY = re.compile(
    r"([.!?;])((?:\s*\[S\d+\])*)"
    r"(?=\s+(?=[A-Za-z0-9\"'(\[])|(?<=\])(?=[A-Za-z0-9\"'(\[])|(?<=[.!?;])(?=[A-Za-z\"'(\[])|\s*$)"
)
_ABBREVIATION_PREFIX = re.compile(
    r"(?:^|[\s(,])(?:e\.g|i\.e|approx|etc|vs|no|mr|mrs|ms|dr|prof|inc|ltd|dept|est|min|max|avg)$",
    re.I,
)
_DOMAIN_OR_EXT_AFTER_DOT = re.compile(
    r"^(?:com|net|org|edu|gov|vn|io|co|uk|de|fr|jp|html|htm|php|json|pdf|csv|txt|py|js)\b",
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
_ISO_DATE = re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})(?=\b|T\d{2}:\d{2})")
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

_POLITE_SUBJECT_MOD = r"(?:(?:return|refund|shipping|delivery|cancellation|payment|exchange)\s+)?"
_POLITE_TOPIC_NP = (
    rf"(?:support|us"
    rf"|(?:your|this|the|our)\s+{_POLITE_SUBJECT_MOD}"
    rf"(?:order|return|refund|delivery|shipping|shipment|cancellation|payment|request|inquiry|question|concern|issue|policy|policies)"
    rf"(?:\s+(?:inquiry|question|concern|issue|request|details|information))?"
    rf")"
)
_SAFE_POLITE_FRAMING = re.compile(
    rf"^(?:"
    rf"(?:thank\s+you(?:\s+(?:very|so)\s+much)?|thanks)"
    rf"(?:\s+for\s+(?:reaching\s+out|contacting\s+(?:us|support)|getting\s+in\s+touch|writing(?:\s+to\s+us)?|your\s+(?:message|inquiry|question|patience))"
    rf"(?:\s+(?:to\s+us\s+)?(?:about|regarding|concerning|with)\s+{_POLITE_TOPIC_NP})?"
    rf"(?:\s+today)?)?[.!]"
    rf"|(?:please\s+)?(?:let\s+us\s+know|feel\s+free\s+to\s+(?:reach\s+out(?:\s+to\s+us)?|contact\s+us|ask)|reach\s+out(?:\s+to\s+us)?|contact\s+us)"
    rf"\s+if\s+you\s+(?:have\s+(?:any\s+)?(?:further\s+|additional\s+|more\s+)?questions?(?:\s+(?:about|regarding|concerning)\s+{_POLITE_TOPIC_NP})?"
    rf"|need\s+(?:any\s+)?(?:further\s+|additional\s+|more\s+)?(?:help|assistance)(?:\s+(?:with|about|regarding)\s+{_POLITE_TOPIC_NP})?)[.!?]"
    rf"|we(?:'re|\s+are)\s+happy\s+to\s+help(?:\s+(?:with|about|regarding)\s+{_POLITE_TOPIC_NP})?[.!]"
    rf"|i\s+understand\s+(?:your|this)\s+concern(?:\s+(?:about|regarding)\s+{_POLITE_TOPIC_NP})?[.!]"
    rf"|we\s+(?:apologize|are\s+sorry)\s+for\s+(?:the|any)\s+inconvenience(?:\s+(?:with\s+{_POLITE_TOPIC_NP}))?[.!]"
    rf")$",
    re.I,
)
_POLITE_NON_CLAIM = re.compile(
    r"^(?:"
    r"(?i:hi|hello|dear|good\s+(?:morning|afternoon|evening))(?:\s*,?\s*(?:(?i:there|(?:valued\s+)?customer|friend|sir(?:\s+or\s+madam)?|madam|ma'am|everyone|team)|[A-Z][a-zA-Z'-]{1,20}(?:\s+[A-Z][a-zA-Z'-]{1,20})?))?\s*[!,.]?"
    r"|(?i:(?:best|kind|warm)\s+regards|sincerely|warmly)\s*[,.!]?"
    r")$"
)
_UNSAFE_UNCITED_TOKENS = re.compile(
    r"(?:[$€£¥₫đ]|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"tomorrow|yesterday|tonight|days?|hours?|weeks?|months?|years?|minutes?)\b)",
    re.I,
)
_SAFE_CLARIFICATION_TOPIC = (
    r"(?:your\s+)?(?:order\s+(?:id|number|code)|tracking\s+(?:id|number|code)|"
    r"transaction\s+(?:id|number|reference)|item|product|issue|details?|information|"
    r"which\s+(?:order|item|product))"
)
_SAFE_CLARIFICATION_QUESTION = re.compile(
    rf"^(?:(?:could|can|would)\s+you\s+(?:please\s+)?|please\s+)"
    rf"(?:provide|share|confirm|send|clarify|specify|let\s+us\s+know)\s+"
    rf"{_SAFE_CLARIFICATION_TOPIC}"
    rf"(?:\s+(?:so\s+(?:i|we)\s+can\s+(?:assist|help|check)(?:\s+you)?|for\s+us))?\s*[.?]$",
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
    rf"(?:has\s+(?:(?:just|now|already|successfully)\s+)*been|was(?:\s+(?:just|already|successfully))?|is(?:\s+(?:now|already))?)\s+"
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


def _is_token_identifier_dot(line: str, dot_pos: int, match_end: int) -> bool:
    """Return True when a no-space period is inside an email, URL, or file/domain extension."""
    if dot_pos + 1 != match_end:
        return False
    left = line.rfind(" ", 0, dot_pos)
    right = line.find(" ", dot_pos)
    token = line[left + 1 : len(line) if right == -1 else right]
    if "@" in token or re.match(r"^(?:https?://|www\.)", token, re.I):
        return True
    after = line[match_end:]
    if _DOMAIN_OR_EXT_AFTER_DOT.match(after) and dot_pos > 0 and line[dot_pos - 1].islower():
        return True
    return False


def split_draft_sentences(text: str) -> list[str]:
    """Split draft into sentences while preserving abbreviations, domains/decimals, and trailing [S1] citations."""
    sentences: list[str] = []
    for raw_line in re.split(r"\n+", text.strip()):
        line = raw_line.strip()
        if not line:
            continue
        start = 0
        for m in _SENTENCE_BOUNDARY.finditer(line):
            punct, attached_cites = m.group(1), m.group(2)
            if punct == "." and not attached_cites.strip():
                is_multi_dot_abbrev = (
                    re.search(r"(?:^|[\s(,])(?:e|i)$", line[:m.start()], re.I) is not None
                    and re.match(r"^(?:g|e)\.", line[m.end():], re.I) is not None
                )
                if (
                    is_multi_dot_abbrev
                    or _ABBREVIATION_PREFIX.search(line[:m.start()])
                    or _is_token_identifier_dot(line, m.start(), m.end())
                ):
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


def _is_safe_uncited_sentence(sentence: str, *, allow_clarification: bool = False) -> bool:
    stripped = sentence.strip()
    if not stripped:
        return True
    cleaned = re.sub(r"\s+", " ", _strip_citations_and_placeholders(stripped)).strip()
    if not cleaned:
        return True
    if len(cleaned) > 100:
        return False
    if re.search(r"\d", cleaned) or _UNSAFE_UNCITED_TOKENS.search(cleaned) or _VND_CURRENCY.search(cleaned):
        return False
    if has_ungrounded_transaction_commitment(cleaned):
        return False
    if _SAFE_POLITE_FRAMING.match(cleaned):
        return True
    if allow_clarification and _SAFE_CLARIFICATION_QUESTION.match(cleaned):
        return True
    if FACTUAL_COMMITMENT.search(cleaned) or _UNCITED_CLAIM_TERMS.search(cleaned):
        return False
    return bool(_POLITE_NON_CLAIM.match(cleaned))


def is_safe_uncited_paragraph(paragraph: str, *, allow_clarification: bool = False) -> bool:
    """Return True when every sentence in an uncited paragraph is non-factual polite framing."""
    sentences = split_draft_sentences(paragraph)
    return bool(sentences) and all(
        _is_safe_uncited_sentence(sentence, allow_clarification=allow_clarification)
        for sentence in sentences
    )


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
    return_st = fields.get("return_status", "")
    payment_st = fields.get("payment_status", "")
    combined_refund = f"{refund_st} {payment_st}"
    if re.search(r"\bcancell?ed\b", phrase):
        return bool(re.search(r"\bcancell?ed\b", order_st))
    if re.search(r"\b(?:refunded|credited|reimbursed)\b", phrase):
        return bool(re.search(r"\b(?:refunded|refund\s+succeeded|credited|reimbursed)\b", combined_refund))
    if re.search(r"\bapproved\b", phrase):
        if re.search(r"\breturn\b", phrase):
            return bool(re.search(r"\bapproved\b", return_st))
        if re.search(r"\b(?:refund|credit|reimbursement)\b", phrase):
            return bool(re.search(r"\bapproved\b", combined_refund))
        return bool(re.search(r"\bapproved\b", f"{refund_st} {return_st}"))
    if re.search(r"\b(?:processed|issued|completed)\b", phrase):
        if re.search(r"\breturn\b", phrase):
            return bool(re.search(r"\b(?:processed|completed)\b", return_st))
        if re.search(r"\b(?:refund|credit|reimbursement|payment|charge|transaction)\b", phrase):
            return bool(re.search(r"\b(?:processed|issued|completed|refunded|refund\s+succeeded)\b", combined_refund))
        return bool(re.search(r"\b(?:processed|completed)\b", order_st))
    return False


_CLAUSE_DELIM = re.compile(r"(?:[()]|(?<!\d):(?!\d)|\s+[-\u2013\u2014]+\s+|(?<!\d),(?!\d))")
_INTRO_NON_CLAIM = re.compile(
    r"^(?:per|according\s+to|regarding|concerning|under|about)\s+(?:our|the|this|your)\s+[a-z\s]+$",
    re.I,
)
_CLAUSE_PREDICATE_CLAIM = re.compile(
    r"\b(?:eligible|ineligible|always|never|guarantee[ds]?|free|price|cost|fee|fees|"
    r"warranty|discount|voucher|instant(?:ly)?|unlimited|automatic(?:ally)?|waived|"
    r"hotline|arrivals?|arrive[ds]?|credit(?:ed)?|process(?:ed|es|ing)?|"
    r"approv(?:ed?|als?)|cancell?(?:ed|ation)?|refund(?:s|ed|ing)?|"
    r"ship(?:s|ped|ping)?|deliver(?:s|ed|y)?|return(?:s|ed|able)?|replace(?:ment)?)\b",
    re.I,
)
_STEM_IRREGULARS = {
    "cancelled": "cancel",
    "canceled": "cancel",
    "cancellation": "cancel",
    "delivery": "deliver",
    "delivered": "deliver",
    "delivers": "deliver",
    "shipping": "ship",
    "shipped": "ship",
    "ships": "ship",
    "eligibility": "eligib",
    "eligible": "eligib",
    "ineligible": "ineligib",
    "guarantee": "guarant",
    "guaranteed": "guarant",
    "guarantees": "guarant",
    "approval": "approv",
    "approvals": "approv",
    "approved": "approv",
    "approve": "approv",
    "credited": "credit",
    "processed": "process",
    "processing": "process",
    "processes": "process",
    "arrivals": "arriv",
    "arrival": "arriv",
    "arrived": "arriv",
    "arrives": "arriv",
    "arrive": "arriv",
    "fees": "fee",
    "costs": "cost",
    "prices": "price",
    "refunds": "refund",
    "refunded": "refund",
    "refunding": "refund",
    "returns": "return",
    "returned": "return",
    "returnable": "return",
    "replacement": "replac",
    "replace": "replac",
}


def _claim_stem(word: str) -> str:
    low = word.lower()
    if low in _STEM_IRREGULARS:
        return _STEM_IRREGULARS[low]
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if len(low) > len(suffix) + 3 and low.endswith(suffix):
            return low[: -len(suffix)]
    return low


def _clause_lacks_source_support(
    clause: str,
    source_stems: set[str],
    *,
    allow_clarification: bool = False,
) -> bool:
    """Return True if a spliced clause asserts claim terms missing from its cited sources."""
    stripped = re.sub(r"^(?:and|or|but|so|then|however)\b\s*", "", clause.strip(" .!?;:\"'")).strip()
    if not stripped or not re.search(r"[A-Za-z0-9]", stripped):
        return False
    if _is_safe_uncited_sentence(stripped + ".", allow_clarification=allow_clarification):
        return False
    if _INTRO_NON_CLAIM.match(stripped):
        return False
    for m in _CLAUSE_PREDICATE_CLAIM.finditer(stripped):
        prefix = _local_clause_prefix(stripped, m.start())
        if _COMMIT_NEG_PREFIX.search(prefix) and m.group(0).lower() in {"cancelled", "canceled", "refunded", "credited", "approved", "processed"}:
            continue
        if _claim_stem(m.group(0)) not in source_stems:
            return True
    return False


def _has_spliced_uncited_clause(
    sentence: str,
    cited_sources: Sequence[Dict[str, Any]],
    *,
    allow_clarification: bool = False,
) -> bool:
    """Detect uncited trailing clauses after [S#] and inline comma/colon/dash/paren clause splices."""
    source_text = "\n".join(
        f"{s.get('title') or ''} {s.get('text') or s.get('excerpt') or ''}" for s in cited_sources
    )
    source_stems = {_claim_stem(w) for w in re.findall(r"[A-Za-z0-9]{2,}", source_text)}

    last_cite_end = 0
    for m in _CITATION_TAG.finditer(sentence):
        last_cite_end = m.end()
    trailing = sentence[last_cite_end:].strip(" .!?;:)]}\"'")
    if trailing and re.search(r"[A-Za-z0-9]", trailing):
        cleaned_trailing = re.sub(r"\s+", " ", PLACEHOLDER.sub(" ", trailing)).strip()
        if not _is_safe_uncited_sentence(cleaned_trailing + ".", allow_clarification=allow_clarification):
            if _clause_lacks_source_support(cleaned_trailing, source_stems, allow_clarification=allow_clarification):
                return True

    masked = _DOUBLE_QUOTED_SPAN.sub(" ", _strip_citations_and_placeholders(sentence))
    masked = _SINGLE_QUOTED_SPAN.sub(" ", masked)
    masked = _CUSTOMER_ATTRIBUTION.sub(" ", masked)
    _, masked = _extract_dates_and_strip(masked)
    clauses = [c.strip() for c in _CLAUSE_DELIM.split(masked) if c.strip(" .!?;:\"'")]
    if len(clauses) >= 2:
        for clause in clauses:
            if _clause_lacks_source_support(clause, source_stems, allow_clarification=allow_clarification):
                return True
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
    *,
    allow_clarification_questions: bool = False,
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
            if not _is_safe_uncited_sentence(sentence, allow_clarification=allow_clarification_questions):
                return "uncited_claim"
            continue
        if any(sid not in sources_by_id for sid in sent_ids):
            return "invalid_citations"
        has_cited_sentence = True
        sent_sources = [sources_by_id[sid] for sid in sent_ids]
        if _has_spliced_uncited_clause(sentence, sent_sources, allow_clarification=allow_clarification_questions):
            return "uncited_claim"
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


def validate_snapshot_sources(
    returned_snapshot: Any,
    authoritative_sources: Sequence[Dict[str, Any]],
    *,
    require_snapshot: bool = False,
) -> bool:
    """Verify an LLM-returned input_snapshot strictly matches authoritative sources."""
    if returned_snapshot is None:
        return not require_snapshot
    if not isinstance(returned_snapshot, dict) or not isinstance(returned_snapshot.get("sources"), list):
        return False
    snap_list = returned_snapshot["sources"]
    if not snap_list:
        return False
    known_by_id: Dict[str, Dict[str, Any]] = {
        str(s.get("source_id") or s.get("id")): s
        for s in authoritative_sources
        if isinstance(s, dict) and (s.get("source_id") or s.get("id"))
    }
    for snap_src in snap_list:
        if not isinstance(snap_src, dict):
            return False
        sid = str(snap_src.get("source_id") or snap_src.get("id") or "")
        expected_src = known_by_id.get(sid)
        if expected_src is None:
            return False
        expected_type = str(expected_src.get("source_type") or "")
        if expected_type and str(snap_src.get("source_type") or "") != expected_type:
            return False
        if str(snap_src.get("document_id") or "") != str(expected_src.get("document_id") or ""):
            return False
        if str(snap_src.get("version") or "") != str(expected_src.get("version") or ""):
            return False
        expected_text = str(
            expected_src.get("excerpt") if expected_src.get("excerpt") is not None else (expected_src.get("text") or "")
        ).strip()
        if expected_text:
            snap_text = snap_src.get("excerpt") if snap_src.get("excerpt") is not None else snap_src.get("text")
            if str(snap_text or "").strip() != expected_text:
                return False
        if snap_src.get("sha256") is not None and expected_src.get("sha256"):
            if str(snap_src.get("sha256") or "") != str(expected_src.get("sha256") or ""):
                return False
    return True


def validate_generated_draft(
    customer_text: str,
    llm_result: Any,
    snapshot_sources: Sequence[Dict[str, Any]],
    *,
    allow_clarification_questions: bool = False,
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
        str(s.get("source_id") or s.get("id")): s
        for s in snapshot_sources
        if isinstance(s, dict) and (s.get("source_id") or s.get("id"))
    }

    if not validate_snapshot_sources(llm_result.get("input_snapshot"), snapshot_sources, require_snapshot=False):
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

    if find_draft_grounding_violation(
        customer_text,
        body,
        snapshot_sources,
        allow_clarification_questions=allow_clarification_questions,
    ) is not None:
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

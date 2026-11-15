"""Pseudonymize known customer values and contact/identifier patterns before AI calls."""

from collections import defaultdict
from datetime import datetime
import re

from apps.core_backend.llm.gemini import ORDER_CONTEXT_ALLOWED_SET, extract_order_facts

PLACEHOLDER = re.compile(r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(?:_[1-9][0-9]*)?\]")

CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
IDENTIFIER_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    ("ORDER_ID", re.compile(r"\bORD-[A-Za-z0-9]+\b")),
    ("TRACKING_ID", re.compile(r"\b(?:TRK-|GIAO|TIKI|VIET|VNPOST)\w+\b")),
    ("TRANSACTION_ID", re.compile(r"\b(?:TXN-|TIKI-TXN-)\w+\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d[ .()-]?){9,15}(?!\w)")),
    ("ADDRESS", re.compile(r"\b\d+\s+[A-Za-z0-9\s,.-]+\s+\b(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Ward|District|City|Province)\b", re.IGNORECASE)),
]
_HIGH_SPECIFICITY_KINDS = {"EMAIL", "ORDER_ID", "TRACKING_ID", "TRANSACTION_ID"}
_ISO_DATETIME_SPAN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
)
_EGRESS_ALLOWED_KEYS = frozenset({"message", "order_context", "as_of", "intent_override"})
_EGRESS_REQUIRED_KEYS = frozenset({"message", "order_context", "as_of"})
_SENTINEL_LEAK = re.compile(r"\x00P\d+\x00")

_SPACY_NLP = None


def _get_spacy_nlp():
    global _SPACY_NLP
    if _SPACY_NLP is False:
        return None
    if _SPACY_NLP is None:
        try:
            import spacy
            _SPACY_NLP = spacy.load("en_core_web_sm")
        except Exception:
            _SPACY_NLP = False
    return _SPACY_NLP if _SPACY_NLP is not False else None


def is_privacy_ner_available() -> bool:
    """Return True when the local spaCy NER pipeline loads cleanly."""
    try:
        return _get_spacy_nlp() is not None
    except Exception:
        return False


def luhn_checksum_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def _overlaps(spans: list[tuple[int, int, str, str]], start: int, end: int) -> bool:
    return any(not (end <= a_start or start >= a_end) for a_start, a_end, _, _ in spans)


def _iso_date_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _ISO_DATETIME_SPAN.finditer(text)]


def _in_ranges(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(not (end <= r_s or start >= r_e) for r_s, r_e in ranges)


def _uncovered_gaps(length: int, accepted: list[tuple[int, int, str, str]]) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for s, e, _k, _r in sorted(accepted, key=lambda item: item[0]):
        if s > cursor:
            gaps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < length:
        gaps.append((cursor, length))
    return gaps


def _collect_regex_and_known_spans(
    message: str,
    known: dict,
    literal_spans: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Resolve non-overlapping PII spans via tiered longest-match ordering over uncovered gaps."""
    accepted = list(literal_spans)
    iso_ranges = _iso_date_ranges(message)

    # Phase A: Structured high-precision spans (CARD, EMAIL, ORDER_ID, TRACKING_ID, TRANSACTION_ID)
    structured: list[tuple[int, int, int, str, str]] = []
    for match in CARD_PATTERN.finditer(message):
        if luhn_checksum_valid(match.group()):
            structured.append((match.start(), match.end(), 0, "CARD", match.group()))
    for kind, pattern in IDENTIFIER_PATTERNS:
        if kind in _HIGH_SPECIFICITY_KINDS:
            for match in pattern.finditer(message):
                structured.append((match.start(), match.end(), 1, kind, match.group()))
    structured.sort(key=lambda item: (item[2], -(item[1] - item[0]), item[0]))
    for s, e, _r, kind, raw in structured:
        if s < e and not _overlaps(accepted, s, e):
            accepted.append((s, e, kind, raw))

    # Phase B: Phone numbers within uncovered gaps (before ADDRESS so phones aren't swallowed)
    phone_pattern = dict(IDENTIFIER_PATTERNS)["PHONE"]
    for g_s, g_e in _uncovered_gaps(len(message), accepted):
        for match in phone_pattern.finditer(message, g_s, g_e):
            if _in_ranges(match.start(), match.end(), iso_ranges):
                continue
            if not _overlaps(accepted, match.start(), match.end()):
                accepted.append((match.start(), match.end(), "PHONE", match.group()))

    # Phase C: ADDRESS regex (per uncovered gap) + known DB values resolved longest-match first
    addr_pattern = dict(IDENTIFIER_PATTERNS)["ADDRESS"]
    tier3: list[tuple[int, int, int, str, str]] = []
    for g_s, g_e in _uncovered_gaps(len(message), accepted):
        for match in addr_pattern.finditer(message, g_s, g_e):
            tier3.append((match.start(), match.end(), 0, "ADDRESS", match.group()))
    for kind, values in (known or {}).items():
        for val in values or ():
            if not val:
                continue
            for match in re.finditer(re.escape(str(val)), message, flags=re.IGNORECASE):
                tier3.append((match.start(), match.end(), 1, str(kind), match.group()))
    tier3.sort(key=lambda item: (-(item[1] - item[0]), item[2], item[0]))
    for s, e, _r, kind, raw in tier3:
        if s < e and not _overlaps(accepted, s, e):
            accepted.append((s, e, kind, raw))

    return accepted


def _collect_ner_spans(
    message: str,
    accepted: list[tuple[int, int, str, str]],
    *,
    require_ner: bool,
) -> list[tuple[int, int, str, str]]:
    """Run spaCy NER over unmasked gaps only so NER never corrupts literals or existing spans."""
    try:
        nlp = _get_spacy_nlp()
    except Exception as exc:
        raise ValueError("Privacy NER model load failed") from exc
    if nlp is None:
        if require_ner:
            raise ValueError("Strict privacy NER model is unavailable")
        return accepted

    ordered = sorted(accepted, key=lambda item: item[0])
    ner_parts: list[str] = []
    gap_map: list[tuple[int, int, int, int]] = []
    msg_cursor = 0
    ner_cursor = 0
    for s, e, kind, _raw in ordered:
        if s > msg_cursor:
            seg = message[msg_cursor:s]
            ner_parts.append(seg)
            gap_map.append((ner_cursor, ner_cursor + len(seg), msg_cursor, s))
            ner_cursor += len(seg)
        marker = f"[{kind}_MASK]"
        ner_parts.append(marker)
        ner_cursor += len(marker)
        msg_cursor = e
    if msg_cursor < len(message):
        seg = message[msg_cursor:]
        ner_parts.append(seg)
        gap_map.append((ner_cursor, ner_cursor + len(seg), msg_cursor, len(message)))

    ner_input = "".join(ner_parts)
    try:
        doc = nlp(ner_input)
        ner_candidates: list[tuple[int, int, str, str]] = []
        for ent in doc.ents:
            ent_text = getattr(ent, "text", "")
            label = getattr(ent, "label_", "")
            if not ent_text or "[" in ent_text or "]" in ent_text or len(ent_text.strip()) <= 2:
                continue
            target_kind = "NAME" if label == "PERSON" else ("ADDRESS" if label in ("GPE", "LOC", "FAC") else None)
            if target_kind is None:
                continue

            ent_s = getattr(ent, "start_char", None)
            ent_e = getattr(ent, "end_char", None)
            matched_via_offsets = False
            if isinstance(ent_s, int) and isinstance(ent_e, int):
                for g_ns, g_ne, g_ms, _g_me in gap_map:
                    if ent_s >= g_ns and ent_e <= g_ne:
                        orig_s = g_ms + (ent_s - g_ns)
                        orig_e = g_ms + (ent_e - g_ns)
                        ner_candidates.append((orig_s, orig_e, target_kind, message[orig_s:orig_e]))
                        matched_via_offsets = True
                        break
            if not matched_via_offsets:
                pat = re.compile(r"(?<!\w)" + re.escape(ent_text) + r"(?!\w)")
                for _ns, _ne, g_ms, g_me in gap_map:
                    for m in pat.finditer(message, g_ms, g_me):
                        ner_candidates.append((m.start(), m.end(), target_kind, m.group()))
    except Exception as exc:
        raise ValueError("Privacy NER inference failed") from exc

    updated = list(accepted)
    for start, end, kind, raw in sorted(ner_candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
        if start < end and not _overlaps(updated, start, end):
            updated.append((start, end, kind, raw))
    return updated


def pseudonymize(message, known, *, require_ner: bool = True):
    if not isinstance(message, str) or not (1 <= len(message) <= 4000):
        raise ValueError("Pseudonymized message exceeds the supported length")

    known = known or {}
    # 0. Protect customer-authored placeholders before any PII detection or NER pass.
    literal_spans = [(m.start(), m.end(), "LITERAL", m.group()) for m in PLACEHOLDER.finditer(message)]

    # 1. Resolve disjoint regex + known DB spans on unmodified text (longest match wins).
    accepted = _collect_regex_and_known_spans(message, known, literal_spans)

    # 2. Run NER over uncovered gaps only; fail closed when strict NER is required or throws.
    accepted = _collect_ner_spans(message, accepted, require_ner=require_ner)

    # 3. Single-pass left-to-right materialization directly into final placeholders (zero sentinels).
    mapping, counters = {}, defaultdict(int)
    value_to_placeholder: dict[tuple[str, str], str] = {}

    def assign(kind: str, value: str) -> str:
        key = (kind, value)
        if key in value_to_placeholder:
            return value_to_placeholder[key]
        counters[kind] += 1
        placeholder = f"[{kind}_{counters[kind]}]"
        value_to_placeholder[key] = placeholder
        mapping[placeholder] = value
        return placeholder

    parts: list[str] = []
    cursor = 0
    for start, end, kind, raw in sorted(accepted, key=lambda item: item[0]):
        if start > cursor:
            parts.append(message[cursor:start])
        parts.append(assign(kind, raw))
        cursor = end
    if cursor < len(message):
        parts.append(message[cursor:])
    result = "".join(parts)

    if not 1 <= len(result) <= 4000:
        raise ValueError("Pseudonymized message exceeds the supported length")
    return result, mapping


def _assert_no_raw_pii(text: str, *, forbidden_values: tuple[str, ...] = ()) -> None:
    """Reject any text containing raw structured PII, active sentinels, or known unmasked values."""
    if _SENTINEL_LEAK.search(text):
        raise ValueError("Unmaterialized privacy sentinel detected before egress")
    stripped = PLACEHOLDER.sub(" ", text)
    iso_ranges = _iso_date_ranges(stripped)
    for match in CARD_PATTERN.finditer(stripped):
        if luhn_checksum_valid(match.group()):
            raise ValueError("Unmasked payment card detected before egress")
    for kind, pattern in IDENTIFIER_PATTERNS:
        for match in pattern.finditer(stripped):
            if kind == "PHONE" and _in_ranges(match.start(), match.end(), iso_ranges):
                continue
            raise ValueError(f"Unmasked {kind} detected before egress")
    for raw_val in forbidden_values:
        val = str(raw_val).strip()
        if not val:
            continue
        flags = re.IGNORECASE if len(val) >= 4 else 0
        if re.search(r"(?<!\w)" + re.escape(val) + r"(?!\w)", stripped, flags=flags):
            raise ValueError("Unmasked customer PII detected before egress")


def _validate_order_context(order_ctx: object, *, forbidden_values: tuple[str, ...] = ()) -> None:
    """Enforce canonical SuggestionRequest.order_context allowlist and raw-PII absence."""
    if not isinstance(order_ctx, dict):
        raise ValueError("Invalid order_context container")
    if not set(order_ctx.keys()) <= ORDER_CONTEXT_ALLOWED_SET:
        raise ValueError("Disallowed keys in order_context")

    for key, val in order_ctx.items():
        if val is None:
            continue
        if isinstance(val, dict):
            if set(val.keys()) != {"amount_minor", "currency"}:
                raise ValueError(f"Disallowed nested structure in order_context.{key}")
            if not isinstance(val["amount_minor"], int) or isinstance(val["amount_minor"], bool):
                raise ValueError(f"Invalid amount_minor in order_context.{key}")
            if not isinstance(val["currency"], str) or not val["currency"].strip():
                raise ValueError(f"Invalid currency in order_context.{key}")
            _assert_no_raw_pii(val["currency"], forbidden_values=forbidden_values)
        elif isinstance(val, str):
            _assert_no_raw_pii(val, forbidden_values=forbidden_values)
        else:
            raise ValueError(f"Disallowed value type in order_context.{key}")

    extract_order_facts(order_ctx, allowed_fields=ORDER_CONTEXT_ALLOWED_SET, strict=True)


def validate_egress_payload(
    payload,
    *,
    require_ner: bool = True,
    forbidden_values: tuple[str, ...] = (),
) -> None:
    """Enforce strict NER and fail-closed PII validation across the full SuggestionRequest envelope."""
    if require_ner and not is_privacy_ner_available():
        raise ValueError("Strict privacy NER model is unavailable")
    if not isinstance(payload, dict):
        raise ValueError("Invalid AI egress payload")
    keys = set(payload.keys())
    if not (_EGRESS_REQUIRED_KEYS <= keys <= _EGRESS_ALLOWED_KEYS):
        raise ValueError("Invalid AI egress payload envelope")

    msg = payload["message"]
    if not isinstance(msg, str) or not (1 <= len(msg) <= 4000) or not msg.strip():
        raise ValueError("Invalid pseudonymized egress message")
    _assert_no_raw_pii(msg, forbidden_values=forbidden_values)

    _validate_order_context(payload["order_context"], forbidden_values=forbidden_values)

    as_of = payload["as_of"]
    if not isinstance(as_of, str) or not as_of.strip():
        raise ValueError("Invalid as_of timestamp")
    try:
        parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid as_of timestamp format") from exc
    if parsed_as_of.tzinfo is None:
        raise ValueError("as_of must include timezone offset")

    intent_override = payload.get("intent_override")
    if intent_override is not None:
        if not isinstance(intent_override, str) or not intent_override.strip() or len(intent_override) > 100:
            raise ValueError("Invalid intent_override")
        _assert_no_raw_pii(intent_override, forbidden_values=forbidden_values)


def restore(message, mapping):
    if not message or not mapping:
        return message
    return PLACEHOLDER.sub(lambda match: mapping.get(match.group(), match.group()), message)

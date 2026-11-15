"""Pseudonymize known customer values and contact/identifier patterns before AI calls."""

import re
from collections import defaultdict

PLACEHOLDER = re.compile(r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(?:_[1-9][0-9]*)?\]")

CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
IDENTIFIER_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    ("ORDER_ID", re.compile(r"\bORD-[A-Za-z0-9]+\b")),
    ("TRACKING_ID", re.compile(r"\b(?:TRK-|GIAO|TIKI|VIET|VNPOST)\w+\b")),
    ("TRANSACTION_ID", re.compile(r"\b(?:TXN-|TIKI-TXN-)\w+\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d[ .()-]?){9,15}(?!\w)")),
    ("ADDRESS", re.compile(r"\b\d+\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Ward|District|City|Province)\b", re.IGNORECASE)),
]
_HIGH_SPECIFICITY_KINDS = {"EMAIL", "ORDER_ID", "TRACKING_ID", "TRANSACTION_ID"}

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


def _collision_free_sentinel(message: str, known: dict) -> str:
    known_values = [str(v) for vs in (known or {}).values() for v in vs if v]
    sentinel = "\x00"
    while sentinel in message or any(sentinel in val for val in known_values):
        sentinel += "\x00"
    return sentinel


def pseudonymize(message, known, *, require_ner: bool = True):
    if not isinstance(message, str) or not message:
        raise ValueError("Pseudonymized message exceeds the supported length")

    known = known or {}
    sentinel = _collision_free_sentinel(message, known)
    mapping, counters = {}, defaultdict(int)
    final_tokens = {}
    token_counter = 0

    def replace(kind, value):
        for placeholder, original in mapping.items():
            if original == value and placeholder.startswith(f"[{kind}_"):
                return placeholder
        counters[kind] += 1
        placeholder = f"[{kind}_{counters[kind]}]"
        mapping[placeholder] = value
        return placeholder

    def wrap(placeholder):
        nonlocal token_counter
        tok = f"{sentinel}P{token_counter}{sentinel}"
        token_counter += 1
        final_tokens[tok] = placeholder
        return tok

    # 0. Protect customer-authored placeholders first using collision-free sentinels.
    result = PLACEHOLDER.sub(lambda match: wrap(replace("LITERAL", match.group())), message)

    # 1. Credit card detection with Luhn checksum validation (before shorter identifiers / phone)
    def mask_card(match):
        raw = match.group()
        if luhn_checksum_valid(raw):
            return wrap(replace("CARD", raw))
        return raw

    result = CARD_PATTERN.sub(mask_card, result)

    # 2. High-specificity structured identifiers (prevents short known DB names fragmenting emails/IDs)
    for kind, pattern in IDENTIFIER_PATTERNS:
        if kind in _HIGH_SPECIFICITY_KINDS:
            result = pattern.sub(lambda match, k=kind: wrap(replace(k, match.group())), result)

    # 3. Known customer database fields sorted globally longest-first across all kinds
    known_entries = sorted(
        {(kind, str(val)) for kind, values in known.items() for val in values if val},
        key=lambda item: (-len(item[1]), item[0], item[1]),
    )
    for kind, value in known_entries:
        result = re.sub(
            re.escape(value),
            lambda match, k=kind: wrap(replace(k, match.group())),
            result,
            flags=re.IGNORECASE,
        )

    # 4. Free-form NER detection using spaCy; fail closed when strict NER is required or NER throws
    try:
        nlp = _get_spacy_nlp()
    except Exception as exc:
        raise ValueError("Privacy NER model load failed") from exc
    if nlp is None:
        if require_ner:
            raise ValueError("Strict privacy NER model is unavailable")
    else:
        try:
            doc = nlp(result)
            spacy_replacements = []
            for ent in doc.ents:
                ent_text = ent.text
                if sentinel in ent_text or "[" in ent_text or "]" in ent_text:
                    continue
                if ent.label_ == "PERSON" and len(ent_text.strip()) > 2:
                    spacy_replacements.append(("NAME", ent_text))
                elif ent.label_ in ("GPE", "LOC", "FAC") and len(ent_text.strip()) > 2:
                    spacy_replacements.append(("ADDRESS", ent_text))
            for kind, val in sorted(spacy_replacements, key=lambda x: len(x[1]), reverse=True):
                result = re.sub(
                    r"(?<!\w)" + re.escape(val) + r"(?!\w)",
                    lambda match, k=kind: wrap(replace(k, match.group())),
                    result,
                )
        except Exception as exc:
            raise ValueError("Privacy NER inference failed") from exc

    # 5. Remaining contact/address regex patterns
    for kind, pattern in IDENTIFIER_PATTERNS:
        if kind not in _HIGH_SPECIFICITY_KINDS:
            result = pattern.sub(lambda match, k=kind: wrap(replace(k, match.group())), result)

    # 6. Single-pass materialization from sentinels to final placeholders
    if final_tokens:
        sentinel_pattern = re.compile(re.escape(sentinel) + r"P\d+" + re.escape(sentinel))
        result = sentinel_pattern.sub(lambda match: final_tokens[match.group()], result)

    if not 1 <= len(result) <= 4000:
        raise ValueError("Pseudonymized message exceeds the supported length")
    return result, mapping


def validate_egress_payload(payload, *, require_ner: bool = True) -> None:
    """Ensure AI worker egress payload satisfies NER strictness and has no raw structured PII."""
    if require_ner and not is_privacy_ner_available():
        raise ValueError("Strict privacy NER model is unavailable")
    if not isinstance(payload, dict):
        raise ValueError("Invalid AI egress payload")
    msg = payload.get("message")
    if not isinstance(msg, str) or not (1 <= len(msg) <= 4000) or not msg.strip():
        raise ValueError("Invalid pseudonymized egress message")
    for match in CARD_PATTERN.finditer(msg):
        if luhn_checksum_valid(match.group()):
            raise ValueError("Unmasked payment card detected before egress")
    for kind, pattern in IDENTIFIER_PATTERNS:
        if kind in _HIGH_SPECIFICITY_KINDS and pattern.search(msg):
            raise ValueError("Unmasked identifier detected before egress")


def restore(message, mapping):
    if not message or not mapping:
        return message
    return PLACEHOLDER.sub(lambda match: mapping.get(match.group(), match.group()), message)

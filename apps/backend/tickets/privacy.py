"""Pseudonymize known customer values and contact/identifier patterns before AI calls."""

import re
from collections import defaultdict

PLACEHOLDER = re.compile(r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]")

CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
IDENTIFIER_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    ("ORDER_ID", re.compile(r"\bORD-[A-Za-z0-9]+\b")),
    ("TRACKING_ID", re.compile(r"\b(?:TRK-|GIAO|TIKI|VIET|VNPOST)\w+\b")),
    ("TRANSACTION_ID", re.compile(r"\b(?:TXN-|TIKI-TXN-)\w+\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d[ .()-]?){9,15}(?!\w)")),
    ("ADDRESS", re.compile(r"\b\d+\s+[A-Za-z0-9\s,.-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Ward|District|City|Province)\b", re.IGNORECASE)),
]

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


def pseudonymize(message, known):
    mapping, counters = {}, defaultdict(int)

    def replace(kind, value):
        for placeholder, original in mapping.items():
            if original == value and placeholder.startswith(f"[{kind}_"):
                return placeholder
        counters[kind] += 1
        placeholder = f"[{kind}_{counters[kind]}]"
        mapping[placeholder] = value
        return placeholder

    # Customer-authored reserved strings are kept distinct from generated placeholders.
    literals = {}
    def literal(match):
        marker = f"\x00{len(literals)}\x00"
        literals[marker] = replace("LITERAL", match.group())
        return marker
    result = PLACEHOLDER.sub(literal, message)

    # 1. Replace known customer database fields (names, emails, phones, addresses)
    for kind, values in known.items():
        for value in sorted(set(filter(None, values)), key=len, reverse=True):
            result = re.sub(re.escape(value), lambda match: replace(kind, match.group()), result, flags=re.IGNORECASE)

    # 2. Free-form NER detection using spaCy if available
    nlp = _get_spacy_nlp()
    if nlp is not None:
        try:
            doc = nlp(result)
            spacy_replacements = []
            for ent in doc.ents:
                if ent.label_ == "PERSON" and len(ent.text.strip()) > 2 and "\x00" not in ent.text:
                    if not ent.text.startswith("[") and not ent.text.endswith("]"):
                        spacy_replacements.append(("NAME", ent.text))
                elif ent.label_ in ("GPE", "LOC", "FAC") and len(ent.text.strip()) > 2 and "\x00" not in ent.text:
                    if not ent.text.startswith("[") and not ent.text.endswith("]"):
                        spacy_replacements.append(("ADDRESS", ent.text))
            for kind, val in sorted(spacy_replacements, key=lambda x: len(x[1]), reverse=True):
                result = re.sub(r"\b" + re.escape(val) + r"\b", lambda match: replace(kind, match.group()), result)
        except Exception:
            pass

    # 3. Credit card detection with Luhn checksum validation (must run before PHONE)
    def mask_card(match):
        raw = match.group()
        if luhn_checksum_valid(raw):
            return replace("CARD", raw)
        return raw
    result = CARD_PATTERN.sub(mask_card, result)

    # 4. Regex patterns for identifiers and sensitive contact data
    for kind, pattern in IDENTIFIER_PATTERNS:
        result = pattern.sub(lambda match, k=kind: replace(k, match.group()), result)

    for marker, value in literals.items():
        result = result.replace(marker, value)
    if not 1 <= len(result) <= 4000:
        raise ValueError("Pseudonymized message exceeds the supported length")
    return result, mapping


def restore(message, mapping):
    return PLACEHOLDER.sub(lambda match: mapping.get(match.group(), match.group()), message)

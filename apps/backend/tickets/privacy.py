"""Pseudonymize known customer values and contact/identifier patterns before AI calls."""

import re
from collections import defaultdict

PLACEHOLDER = re.compile(r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]")


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
    for kind, values in known.items():
        for value in sorted(set(filter(None, values)), key=len, reverse=True):
            result = re.sub(re.escape(value), lambda match: replace(kind, match.group()), result, flags=re.IGNORECASE)
    patterns = {"EMAIL": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
                "ORDER_ID": r"\bORD-[A-Za-z0-9]+\b", "TRACKING_ID": r"\b(?:TRK-|GIAO|TIKI|VIET|VNPOST)\w+\b",
                "TRANSACTION_ID": r"\b(?:TXN-|TIKI-TXN-)\w+\b",
                "PHONE": r"(?<!\w)(?:\+?\d[ .()-]?){9,15}(?!\w)"}
    for kind, pattern in patterns.items():
        result = re.sub(pattern, lambda match: replace(kind, match.group()), result)
    for marker, value in literals.items():
        result = result.replace(marker, value)
    if not 1 <= len(result) <= 4000:
        raise ValueError("Pseudonymized message exceeds the supported length")
    return result, mapping


def restore(message, mapping):
    return PLACEHOLDER.sub(lambda match: mapping.get(match.group(), match.group()), message)

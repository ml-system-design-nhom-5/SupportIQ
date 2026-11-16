"""The placeholders of a text, and the second layer of masks before every LLM call (SEC-06).

`backend` pseudonymizes every message before it leaves (FR-09). Masking is the second layer and
never replaces it: a personal-data pattern that is still present outside a placeholder becomes
`[EMAIL]`, `[PHONE]`, or `[CARD]` (ADR-0010). A mask cannot be restored, and every mask means
that pseudonymization missed a value, so the pipeline logs each one by type only.
"""

import re
from dataclasses import dataclass

from supportiq_ai_service.suggestions.domain.draft import MaskCounts

# Every placeholder matches this expression, and nothing else may (ADR-0010, Placeholder syntax).
PLACEHOLDER_PATTERN = re.compile(
    r"\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]"
)
_EMAIL = re.compile(
    r"(?<![\w.%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
)
# 13 to 19 digits, in groups split by single spaces or hyphens, that pass the Luhn check.
_CARD_CANDIDATE = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")
# 8 to 15 digits, with an optional `+` and single separators; a date is never a phone number.
_PHONE_CANDIDATE = re.compile(r"(?<![\w+])\+?\(?\d(?:[ .()-]{0,2}\d){7,14}(?!\w)")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
_LUHN_MODULUS = 10
_LUHN_DOUBLE_LIMIT = 9


@dataclass(frozen=True, slots=True)
class MaskedText:
    """A text after the second layer of masks.

    Attributes:
        text: The text, with each personal-data pattern outside a placeholder masked.
        counts: The masks applied, by type.
    """

    text: str
    counts: MaskCounts


def placeholders_in(text: str) -> frozenset[str]:
    """Return every placeholder of a text.

    Args:
        text: The text.

    Returns:
        The placeholders, such as `[ORDER_ID_1]` and `[EMAIL]`.
    """
    return frozenset(match.group(0) for match in PLACEHOLDER_PATTERN.finditer(text))


def mask_personal_data(text: str) -> MaskedText:
    """Mask every email address, payment card number, and phone number outside a placeholder.

    Args:
        text: The pseudonymized message. Confidential.

    Returns:
        The masked text and the number of masks of each type.
    """
    counts = {"email": 0, "phone": 0, "card": 0}
    parts: list[str] = []
    position = 0
    for placeholder in PLACEHOLDER_PATTERN.finditer(text):
        parts.append(_mask_part(text[position : placeholder.start()], counts))
        parts.append(placeholder.group(0))
        position = placeholder.end()
    parts.append(_mask_part(text[position:], counts))
    return MaskedText(text="".join(parts), counts=MaskCounts(**counts))


def _mask_part(part: str, counts: dict[str, int]) -> str:
    def email(match: re.Match[str]) -> str:
        del match
        counts["email"] += 1
        return "[EMAIL]"

    def card(match: re.Match[str]) -> str:
        if not _is_card_number(match.group(0)):
            return match.group(0)
        counts["card"] += 1
        return "[CARD]"

    def phone(match: re.Match[str]) -> str:
        if _DATE.fullmatch(match.group(0)):
            return match.group(0)
        counts["phone"] += 1
        return "[PHONE]"

    part = _EMAIL.sub(email, part)
    part = _CARD_CANDIDATE.sub(card, part)
    return _PHONE_CANDIDATE.sub(phone, part)


def _is_card_number(candidate: str) -> bool:
    # The pattern already holds 13 to 19 digits, so only the Luhn check remains.
    digits = [int(character) for character in candidate if character.isdigit()]
    total = 0
    for index, digit in enumerate(reversed(digits)):
        doubled = digit * 2 if index % 2 else digit
        total += doubled - _LUHN_DOUBLE_LIMIT if doubled > _LUHN_DOUBLE_LIMIT else doubled
    return total % _LUHN_MODULUS == 0

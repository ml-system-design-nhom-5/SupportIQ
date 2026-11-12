"""The detectors of ADR-0010 that need no model: literal placeholders, known values, patterns.

The named-entity detector of step 4 is an adapter that implements the same `Detector` port,
because its model is a third-party library (ARCH-28, ADR-0017).
"""

import re
from collections.abc import Callable, Iterator, Mapping
from types import MappingProxyType

from supportiq_backend.commerce import (
    ORDER_ID_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
)
from supportiq_backend.pseudonymization.domain.detection import (
    Detection,
    DetectionSource,
    KnownValue,
    find_whole_words,
    fold_text,
    fold_value,
)
from supportiq_backend.pseudonymization.domain.placeholders import (
    PLACEHOLDER_PATTERN,
    PseudonymType,
)

# A local part, `@`, and a domain with at least one dot (ADR-0010, Detection, step 3).
_EMAIL_PATTERN = re.compile(r"(?<![\w.%+-])[\w.%+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])")
# 9 to 15 digits, optionally with a leading `+`, and with one space, dot, or hyphen at most
# between two digits. The whole run of digits must match, so no part of a longer number does.
_PHONE_PATTERN = re.compile(
    r"(?<![\w+])(?<![0-9][ .-])\+?[0-9](?:[ .-]?[0-9]){8,14}(?!\w)(?![ .-][0-9])"
)
# 13 to 19 digits, optionally grouped by spaces or hyphens, as a whole run; the Luhn check
# follows.
_CARD_PATTERN = re.compile(r"(?<!\w)(?<![0-9][ -])[0-9](?:[ -]?[0-9]){12,18}(?!\w)(?![ -][0-9])")
_LUHN_DOUBLED_DIGIT_LIMIT = 9
_LUHN_MODULUS = 10

# The commerce identifiers of the seed, as whole words (backend foundation design, Tables).
_COMMERCE_PATTERNS: Mapping[PseudonymType, re.Pattern[str]] = MappingProxyType(
    {
        pseudonym_type: re.compile(rf"(?<!\w){pattern.pattern}(?!\w)")
        for pseudonym_type, pattern in (
            (PseudonymType.ORDER_ID, ORDER_ID_PATTERN),
            (PseudonymType.TRACKING_ID, TRACKING_CODE_PATTERN),
            (PseudonymType.TRANSACTION_ID, TRANSACTION_ID_PATTERN),
        )
    }
)


class LiteralPlaceholderDetector:
    """Step 1: text that already looks like a placeholder becomes a `LITERAL` pseudonym."""

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find every text that matches the placeholder syntax.

        Args:
            message: The raw message.
            _known_values: Not used by this step.

        Returns:
            One `LITERAL` detection per match.
        """
        return tuple(
            Detection(match.start(), match.end(), PseudonymType.LITERAL, DetectionSource.LITERAL)
            for match in PLACEHOLDER_PATTERN.finditer(message)
        )


class KnownValueDetector:
    """Step 2: whole-word matches of the ticket's known values, ignoring case and diacritics."""

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find every whole-word occurrence of every known value.

        Args:
            message: The raw message.
            known_values: The values that backend holds for the ticket.

        Returns:
            One detection per occurrence.
        """
        folded = fold_text(message)
        return tuple(
            detection
            for known_value in known_values
            for detection in _find_known_value(folded.text, known_value, folded.to_original_span)
        )


class PatternDetector:
    """Step 3: emails, phone numbers, card numbers, and the commerce identifiers."""

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find every value that has the format of one of the patterns.

        Args:
            message: The raw message.
            _known_values: Not used by this step.

        Returns:
            One detection per match; the overlap rule decides between them.
        """
        return (
            *_find_pattern(message, _EMAIL_PATTERN, PseudonymType.EMAIL),
            *_find_pattern(message, _PHONE_PATTERN, PseudonymType.PHONE),
            *(
                detection
                for detection in _find_pattern(message, _CARD_PATTERN, PseudonymType.CARD)
                if is_luhn_valid(message[detection.start : detection.end])
            ),
            *(
                detection
                for pseudonym_type, pattern in _COMMERCE_PATTERNS.items()
                for detection in _find_pattern(message, pattern, pseudonym_type)
            ),
        )


def is_luhn_valid(number: str) -> bool:
    """Tell whether the digits of a text pass the Luhn check of payment card numbers.

    Args:
        number: The text; every character that is not a digit is ignored.

    Returns:
        True when the checksum of the digits is valid.
    """
    digits = [int(character) for character in number if character.isdigit()]
    total = sum(
        _luhn_value(digit, is_doubled=position % 2 == 1)
        for position, digit in enumerate(reversed(digits))
    )
    return bool(digits) and total % _LUHN_MODULUS == 0


def _luhn_value(digit: int, *, is_doubled: bool) -> int:
    if not is_doubled:
        return digit
    doubled = digit * 2
    return doubled - _LUHN_DOUBLED_DIGIT_LIMIT if doubled > _LUHN_DOUBLED_DIGIT_LIMIT else doubled


def _find_known_value(
    folded_message: str,
    known_value: KnownValue,
    to_original_span: Callable[[int, int], tuple[int, int]],
) -> Iterator[Detection]:
    folded_value = fold_value(known_value.text).strip()
    if not folded_value:
        return
    for match in find_whole_words(folded_value, folded_message):
        start, end = to_original_span(match.start(), match.end())
        yield Detection(start, end, known_value.pseudonym_type, DetectionSource.KNOWN_VALUE)


def _find_pattern(
    message: str, pattern: re.Pattern[str], pseudonym_type: PseudonymType
) -> Iterator[Detection]:
    for match in pattern.finditer(message):
        yield Detection(match.start(), match.end(), pseudonym_type, DetectionSource.PATTERN)

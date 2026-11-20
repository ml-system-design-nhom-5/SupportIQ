"""The detectors of ADR-0010 that need no model: literal placeholders, known values, patterns.

The named-entity detector of step 4 is an adapter that implements the same `Detector` port,
because its model is a third-party library (ARCH-28, ADR-0017).
"""

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.commerce import (
    ORDER_ID_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
)
from app.pseudonymization.domain.detection import (
    Detection,
    DetectionSource,
    KnownValue,
    find_whole_words,
    fold_text,
    fold_value,
)
from app.pseudonymization.domain.placeholders import (
    PLACEHOLDER_PATTERN,
    PseudonymType,
)

# A local part, `@`, and a domain with at least one dot (ADR-0010, Detection, step 3).
_EMAIL_PATTERN = re.compile(r"(?<![\w.%+-])[\w.%+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])")
# A run of digit groups with one separator between two groups: spaces, dots, or hyphens and
# an optional leading `+` for phone numbers, spaces or hyphens for card numbers. A value is
# a span of whole groups of a run, so it never starts or ends inside a group of digits, and
# the text around the run may be anything but a letter or digit stuck to it ("2pm" ends no
# value, "12/27" does).
_PHONE_RUN = re.compile(r"\+?[0-9]+(?:[ .-][0-9]+)*")
_CARD_RUN = re.compile(r"[0-9]+(?:[ -][0-9]+)*")
_DIGIT_GROUP = re.compile(r"[0-9]+")
_PHONE_DIGIT_COUNT = range(9, 16)
_CARD_DIGIT_COUNT = range(13, 20)
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
            *_find_digit_values(
                message, _PHONE_RUN, _PHONE_DIGIT_COUNT, PseudonymType.PHONE, _is_any_number
            ),
            *_find_digit_values(
                message, _CARD_RUN, _CARD_DIGIT_COUNT, PseudonymType.CARD, is_luhn_valid
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


@dataclass(frozen=True, slots=True)
class _DigitGroup:
    start: int
    end: int
    digit_count: int
    can_start: bool
    can_end: bool


def _find_digit_values(
    message: str,
    run_pattern: re.Pattern[str],
    digit_counts: range,
    pseudonym_type: PseudonymType,
    is_valid: Callable[[str], bool],
) -> Iterator[Detection]:
    # From each group that can start a value, the longest span of whole groups with an
    # allowed number of digits that passes the check; the overlap rule then keeps the
    # longest of them (ADR-0010, Detection, steps 3 and 5).
    for run in run_pattern.finditer(message):
        groups = _digit_groups(message, run)
        for first, group in enumerate(groups):
            if not group.can_start:
                continue
            end = _longest_value_end(message, groups[first:], digit_counts, is_valid)
            if end is not None:
                yield Detection(group.start, end, pseudonym_type, DetectionSource.PATTERN)


def _digit_groups(message: str, run: re.Match[str]) -> tuple[_DigitGroup, ...]:
    matches = tuple(_DIGIT_GROUP.finditer(message, run.start(), run.end()))
    starts_alone = run.start() == 0 or not _is_word_character(message[run.start() - 1])
    ends_alone = run.end() == len(message) or not _is_word_character(message[run.end()])
    last = len(matches) - 1
    return tuple(
        _DigitGroup(
            # A leading `+` belongs to the first group.
            start=run.start() if position == 0 else match.start(),
            end=match.end(),
            digit_count=match.end() - match.start(),
            can_start=position > 0 or starts_alone,
            can_end=position < last or ends_alone,
        )
        for position, match in enumerate(matches)
    )


def _longest_value_end(
    message: str,
    groups: tuple[_DigitGroup, ...],
    digit_counts: range,
    is_valid: Callable[[str], bool],
) -> int | None:
    longest: int | None = None
    digit_count = 0
    for group in groups:
        digit_count += group.digit_count
        if digit_count > max(digit_counts):
            break
        is_value = (
            digit_count in digit_counts
            and group.can_end
            and is_valid(message[groups[0].start : group.end])
        )
        if is_value:
            longest = group.end
    return longest


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _is_any_number(_number: str) -> bool:
    return True


def _find_pattern(
    message: str, pattern: re.Pattern[str], pseudonym_type: PseudonymType
) -> Iterator[Detection]:
    for match in pattern.finditer(message):
        yield Detection(match.start(), match.end(), pseudonym_type, DetectionSource.PATTERN)

"""The pre-send check of layer 2 (ADR-0029, statement 4; leak fixes design, Layer 2).

It reads the pseudonymized text that pseudonymization built and fails closed while personal
data is left: a value of the map or a known value of the ticket outside a placeholder, or a
residue beside a placeholder. It reports the type of the finding, never the value (LOG-29).
"""

import re
from collections.abc import Iterator
from itertools import pairwise

from app.pseudonymization.domain.detection import (
    KnownValue,
    find_whole_words,
    fold_text,
    fold_value,
)
from app.pseudonymization.domain.detectors import PHONE_EXTENSION, PHONE_SEPARATORS
from app.pseudonymization.domain.errors import PersonalDataLeftError
from app.pseudonymization.domain.name_rules import NAME_NEIGHBOUR_STOPLIST
from app.pseudonymization.domain.placeholders import PLACEHOLDER_PATTERN, PseudonymType
from app.pseudonymization.domain.pseudonym_map import PseudonymEntry
from app.pseudonymization.domain.words import MARKS, WORD_PATTERN, nfc

# The words and signs of an amount, right before or after a number of 5 or 6 digits after an
# address (design, Layer 2, finding 5).
CURRENCY_WORDS = ("VND", "đ", "USD", "$")

_DIGIT_TYPES = frozenset({PseudonymType.PHONE, PseudonymType.CARD})
_RESIDUE_TYPES = frozenset({PseudonymType.NAME, PseudonymType.ADDRESS})
# A placeholder stands for one character that is neither a digit, a separator, nor a word
# character, so no value or digit run crosses it.
_OUTSIDE = "\x00"
_DIGIT_RUN = re.compile(rf"[0-9](?:[0-9{re.escape(PHONE_SEPARATORS)}]*[0-9])?")
_NOT_A_DIGIT = re.compile("[^0-9]")
# A letter or digit right beside a placeholder, or one "-", ".", "/", "x", or "@" away.
_JOINED_BEFORE = re.compile(rf"(?:[^\W_]|[{MARKS}])[-./x@]?\Z")
_JOINED_AFTER = re.compile(r"[-./x@]?[^\W_]")
# A whole word one or more spaces before or after a placeholder. A hyphen ends it, so "Pierre"
# of "Jean-Pierre" is the word before: the check reads no word as part of a code.
_WORD_BEFORE = re.compile(rf"(?<![^\W\d_])(?<![{MARKS}])({WORD_PATTERN}) +\Z")
_WORD_AFTER = re.compile(rf" +({WORD_PATTERN})")
_SENTENCE_START = re.compile(r"(?:\A\s*|[.!?]\s+)\Z")
_NUMBER_BEFORE = re.compile(r"(?<![\w.,])[0-9]{1,5} +\Z")
_POSTAL_NUMBER = re.compile(r"(?<![\w.,])[0-9]{5,6}(?![0-9])")
_CURRENCY = "|".join(map(re.escape, CURRENCY_WORDS))
_CURRENCY_BEFORE = re.compile(rf"(?:{_CURRENCY})\s*\Z", re.IGNORECASE)
_CURRENCY_AFTER = re.compile(rf"\s*(?:{_CURRENCY})", re.IGNORECASE)


def check_nothing_left(
    text: str, entries: tuple[PseudonymEntry, ...], known_values: tuple[KnownValue, ...]
) -> None:
    """Fail closed while the pseudonymized text still holds personal data.

    Args:
        text: The pseudonymized text. Confidential.
        entries: The map that built it.
        known_values: The values that backend holds for the ticket.

    Raises:
        PersonalDataLeftError: A finding of the design, with the type of the placeholder or
            value next to it (ADR-0029, statement 4).
    """
    values = [
        *((entry.pseudonym_type, entry.original_value) for entry in entries),
        *((known_value.pseudonym_type, known_value.text) for known_value in known_values),
    ]
    findings = (
        _value_outside(text, values),
        _joined_to_placeholder(text),
        _word_beside_name(text),
        _number_beside_placeholder(text),
    )
    finding = next((found for found in findings if found is not None), None)
    if finding is not None:
        raise PersonalDataLeftError(finding)


def _value_outside(text: str, values: list[tuple[PseudonymType, str]]) -> PseudonymType | None:
    # Findings 1 and 2: a value of the map or a known value outside a placeholder. Phone and
    # card numbers compare by their digits, without an extension, inside one run of digits and
    # separators; the other values compare as whole words, ignoring case and diacritics, as
    # step 2 does.
    outside = PLACEHOLDER_PATTERN.sub(_OUTSIDE, text)
    digit_runs = [_digits(run.group()) for run in _DIGIT_RUN.finditer(outside)]
    folded = fold_text(outside).text
    for pseudonym_type, value in values:
        if pseudonym_type is PseudonymType.LITERAL:
            continue
        if pseudonym_type in _DIGIT_TYPES:
            digits = _number_digits(pseudonym_type, value)
            if digits and any(digits in run for run in digit_runs):
                return pseudonym_type
        elif (folded_value := fold_value(value).strip()) and _holds_word(folded, folded_value):
            return pseudonym_type
    return None


def _joined_to_placeholder(text: str) -> PseudonymType | None:
    # Finding 3: a letter or digit joined to a placeholder by nothing or by a joining sign.
    for placeholder in PLACEHOLDER_PATTERN.finditer(text):
        joined_before = _JOINED_BEFORE.search(text, 0, placeholder.start()) is not None
        if joined_before or _JOINED_AFTER.match(text, placeholder.end()) is not None:
            return PseudonymType(placeholder.group(1))
    return None


def _word_beside_name(text: str) -> PseudonymType | None:
    # Finding 4: a capitalized word one or more spaces beside a name, other than a word of the
    # stoplist or a word that starts a sentence or the text.
    for name in _placeholders(text, frozenset({PseudonymType.NAME})):
        if _name_word_before(text, name.start()) or _name_word_after(text, name.end()):
            return PseudonymType.NAME
    return None


def _name_word_before(text: str, end: int) -> bool:
    word = _WORD_BEFORE.search(text, 0, end)
    if word is None or not _is_name_word(word.group(1)):
        return False
    return _SENTENCE_START.search(text, 0, word.start()) is None


def _name_word_after(text: str, start: int) -> bool:
    word = _WORD_AFTER.match(text, start)
    return word is not None and _is_name_word(word.group(1))


def _number_beside_placeholder(text: str) -> PseudonymType | None:
    # Finding 5: a house number right before a name or an address, or a postal code in the
    # comma-separated part right after the part that holds one, unless it is an amount.
    for placeholder in _placeholders(text, _RESIDUE_TYPES):
        if _NUMBER_BEFORE.search(text, 0, placeholder.start()) is not None:
            return PseudonymType(placeholder.group(1))
    for part, next_part in pairwise(text.split(",")):
        placeholder = next(_placeholders(part, _RESIDUE_TYPES), None)
        if placeholder is not None and _holds_postal_code(next_part):
            return PseudonymType(placeholder.group(1))
    return None


def _holds_postal_code(part: str) -> bool:
    # A number of 5 or 6 digits that no currency word or sign stands right before or after.
    return any(
        _CURRENCY_BEFORE.search(part, 0, number.start()) is None
        and _CURRENCY_AFTER.match(part, number.end()) is None
        for number in _POSTAL_NUMBER.finditer(part)
    )


def _placeholders(text: str, types: frozenset[PseudonymType]) -> Iterator[re.Match[str]]:
    return (
        placeholder
        for placeholder in PLACEHOLDER_PATTERN.finditer(text)
        if PseudonymType(placeholder.group(1)) in types
    )


def _is_name_word(word: str) -> bool:
    return word[0].isupper() and nfc(word) not in NAME_NEIGHBOUR_STOPLIST


def _holds_word(folded_text: str, folded_value: str) -> bool:
    return next(find_whole_words(folded_value, folded_text), None) is not None


def _number_digits(pseudonym_type: PseudonymType, value: str) -> str:
    # A phone number leaves out its extension, whose digits are no part of the number
    # (ADR-0029, statement 1).
    if pseudonym_type is PseudonymType.PHONE and (extension := PHONE_EXTENSION.search(value)):
        value = value[: extension.start()]
    return _digits(value)


def _digits(text: str) -> str:
    return _NOT_A_DIGIT.sub("", text)

"""The address rule of step 4 (ADR-0029, statement 3; leak fixes design, Layer 1, addresses).

An address is a house number, then up to 5 parts of capitalized words, address words, or a
postal code, with at least one address word. The address words include their spellings without
diacritics, except "To" and "Day", and the abbreviations "Q.", "P.", and "TP." (design,
revision 4). The lists are constants of this module, so a change of a list is a change of the
detector version (ADR-0010, Placeholder syntax, item 5).
"""

import re

from app.pseudonymization.domain.detection import Detection, DetectionSource, KnownValue
from app.pseudonymization.domain.placeholders import PseudonymType
from app.pseudonymization.domain.words import (
    NOTHING_JOINED_AFTER,
    NOTHING_JOINED_BEFORE,
    WORD_PATTERN,
    word_key,
)

# The street and administrative words of the design, compared after NFC normalization and case
# folding (design, Layer 1, addresses, item 3).
VIETNAMESE_ADDRESS_WORDS = (
    "Đường",
    "Phố",
    "Ngõ",
    "Ngách",
    "Hẻm",
    "Kiệt",
    "Tổ",
    "Khu",
    "Dãy",
    "Thôn",
    "Ấp",
    "Xóm",
    "Phường",
    "Xã",
    "Thị trấn",
    "Quận",
    "Huyện",
    "Thị xã",
    "Thành phố",
    "Tỉnh",
)
# The same words without diacritics, with "đ" written as "d", except "To" and "Day", which are
# also common English words; "Khu" has no diacritics (design, Layer 1, addresses, item 3).
VIETNAMESE_ADDRESS_WORDS_UNACCENTED = (
    "Duong",
    "Pho",
    "Ngo",
    "Ngach",
    "Hem",
    "Kiet",
    "Thon",
    "Ap",
    "Xom",
    "Phuong",
    "Xa",
    "Thi tran",
    "Quan",
    "Huyen",
    "Thi xa",
    "Thanh pho",
    "Tinh",
)
ENGLISH_ADDRESS_WORDS = (
    "Street",
    "St",
    "Avenue",
    "Ave",
    "Road",
    "Rd",
    "Lane",
    "Ln",
    "Drive",
    "Boulevard",
    "Blvd",
    "Apt",
    "Suite",
    "Unit",
)
ADDRESS_WORDS = (
    *VIETNAMESE_ADDRESS_WORDS,
    *VIETNAMESE_ADDRESS_WORDS_UNACCENTED,
    *ENGLISH_ADDRESS_WORDS,
)
# The abbreviations that a period may follow inside an address, as in "12 Main St., Springfield".
ABBREVIATED_ADDRESS_WORDS = frozenset({"St", "Ave", "Rd", "Ln", "Blvd", "Apt"})
# Quận, Phường, and Thành phố: address words only with their period and with a number or a
# capitalized word after it, as in "Q.1", "P. 5", or "TP.HCM" (design, Layer 1, addresses).
VIETNAMESE_ABBREVIATIONS = ("Q", "P", "TP")
ADDRESS_PART_COUNT = 5

# The form of a house number: 1 to 5 digits, then a letter, or "/" and digits. A number of this
# form also follows any address word, as in "Apt 5B", "Phường 5", or "Hẻm 34/5".
_NUMBER = r"[0-9]{1,5}(?:[^\W\d_]|/[0-9]+)?"
# A house number, then the spaces before the first part.
_HOUSE_NUMBER = re.compile(rf"{NOTHING_JOINED_BEFORE}{_NUMBER} +")
_NUMBER_AFTER_WORD = re.compile(rf" +{_NUMBER}{NOTHING_JOINED_AFTER}")
_NUMBER_ALONE = re.compile(rf"{_NUMBER}{NOTHING_JOINED_AFTER}")
# An abbreviation, its period, and the spaces after it, if any, compared without case.
_ABBREVIATION = re.compile(
    rf"(?:{'|'.join(map(re.escape, VIETNAMESE_ABBREVIATIONS))})\. *", re.IGNORECASE
)
_POSTAL_CODE = re.compile(rf"[0-9]{{5,6}}{NOTHING_JOINED_AFTER}")
# A word, or words joined by a hyphen or an apostrophe, as in "Rịa-Vũng" or "O'Connell".
_PLACE_WORD = re.compile(rf"{WORD_PATTERN}(?:[-']{WORD_PATTERN})*{NOTHING_JOINED_AFTER}")
_JOINED_WORD = re.compile(r"[-']")
_NEXT_WORD = re.compile(rf" +({WORD_PATTERN}){NOTHING_JOINED_AFTER}")
# Spaces inside a part; a comma, a line break, or both between two parts. Several spaces in a
# row count as one.
_SEPARATOR = re.compile(r",? *\r?\n *| +|, *")
_ADDRESS_WORD_KEYS = frozenset(map(word_key, ADDRESS_WORDS))
_ABBREVIATION_KEYS = frozenset(map(word_key, ABBREVIATED_ADDRESS_WORDS))


class AddressRuleDetector:
    """Step 4: postal addresses that start with a house number (design, Layer 1, addresses)."""

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find each address that a house number starts.

        Args:
            message: The raw message.
            _known_values: Not used by this rule.

        Returns:
            One `ADDRESS` of the rule source per address, none of them overlapping.
        """
        addresses: list[Detection] = []
        for house_number in _HOUSE_NUMBER.finditer(message):
            if addresses and house_number.start() < addresses[-1].end:
                continue
            end = _address_end(message, house_number.end())
            if end is not None:
                addresses.append(
                    Detection(
                        house_number.start(), end, PseudonymType.ADDRESS, DetectionSource.RULE
                    )
                )
        return tuple(addresses)


def _address_end(message: str, position: int) -> int | None:
    # The end of the last part that a house number starts, when one of its words is an address
    # word. A part ends at its first word that fits none of its kinds, and the address with it.
    end: int | None = None
    has_address_word = False
    parts = 1
    while (element := _element_at(message, position)) is not None:
        end, is_address_word = element
        has_address_word = has_address_word or is_address_word
        separator = _SEPARATOR.match(message, end)
        if separator is None:
            break
        if separator.group().strip(" "):
            parts += 1
        if parts > ADDRESS_PART_COUNT:
            break
        position = separator.end()
    return end if has_address_word else None


def _element_at(message: str, position: int) -> tuple[int, bool] | None:
    # The end of the abbreviation, postal code, address word, or capitalized word at `position`,
    # and whether it is an address word.
    if (abbreviation_end := _abbreviation_end(message, position)) is not None:
        return abbreviation_end, True
    if (postal_code := _POSTAL_CODE.match(message, position)) is not None:
        return postal_code.end(), False
    word = _PLACE_WORD.match(message, position)
    return _word_element(message, word) if word is not None else None


def _abbreviation_end(message: str, position: int) -> int | None:
    # The end of "Q.", "P.", or "TP." with the number or the capitalized word after its period,
    # with or without spaces between. The address rule reads "Q.1" and "TP.HCM" on its own,
    # because the word reading takes them for codes.
    abbreviation = _ABBREVIATION.match(message, position)
    if abbreviation is None:
        return None
    if (number := _NUMBER_ALONE.match(message, abbreviation.end())) is not None:
        return number.end()
    word = _PLACE_WORD.match(message, abbreviation.end())
    return word.end() if word is not None and _is_capitalized(word.group()) else None


def _word_element(message: str, word: re.Match[str]) -> tuple[int, bool] | None:
    following = _NEXT_WORD.match(message, word.end())
    if following is not None and _is_address_phrase(word.group(), following.group(1)):
        return _after_address_word(message, following.end(), is_abbreviation=False), True
    key = word_key(word.group())
    if key in _ADDRESS_WORD_KEYS:
        is_abbreviation = key in _ABBREVIATION_KEYS
        return _after_address_word(message, word.end(), is_abbreviation=is_abbreviation), True
    return (word.end(), False) if _is_capitalized(word.group()) else None


def _is_capitalized(word: str) -> bool:
    # Each piece of a word joined by a hyphen or an apostrophe starts with a capital.
    return all(piece[0].isupper() for piece in _JOINED_WORD.split(word))


def _is_address_phrase(first: str, second: str) -> bool:
    # An address word of two words, such as "Thị trấn".
    return word_key(f"{first} {second}") in _ADDRESS_WORD_KEYS


def _after_address_word(message: str, end: int, *, is_abbreviation: bool) -> int:
    # An abbreviation keeps its period, and an address word keeps the number after it.
    if is_abbreviation and message[end : end + 1] == ".":
        end += 1
    number = _NUMBER_AFTER_WORD.match(message, end)
    return number.end() if number is not None else end

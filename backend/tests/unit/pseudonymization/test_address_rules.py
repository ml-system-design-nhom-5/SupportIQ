"""Tests of the address rule of step 4 (ADR-0029, statement 3; leak fixes design, Layer 1).

The rule has at least five positive and five negative examples (ADR-0029, statement 8), each
known limit of the design has a test that states it, and the invariants of the design are
property-based tests (TEST-13). Every value is synthetic (TEST-18).
"""

import re
import unicodedata
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.pseudonymization.domain import (
    ABBREVIATED_ADDRESS_WORDS,
    ADDRESS_PART_COUNT,
    ADDRESS_WORDS,
    VIETNAMESE_ABBREVIATIONS,
    VIETNAMESE_ADDRESS_WORDS,
    VIETNAMESE_ADDRESS_WORDS_UNACCENTED,
    AddressRuleDetector,
    Detection,
    DetectionSource,
    PseudonymType,
    VietnameseNameDetector,
    resolve_overlaps,
)


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def addresses(message: str) -> list[str]:
    return [
        message[detection.start : detection.end]
        for detection in AddressRuleDetector().detect(message, ())
    ]


@pytest.mark.parametrize(
    ("message", "address"),
    [
        ("Ship to 9 Hoàng Dãy, JaneHuyện, 190841 please", "9 Hoàng Dãy, JaneHuyện, 190841"),
        ("to 22 Lê Ngõ, JohnQuận, 217827", "22 Lê Ngõ, JohnQuận, 217827"),
        ("Collect it at 12 Main Street, Springfield.", "12 Main Street, Springfield"),
        ("at 12A Lê Lợi Street", "12A Lê Lợi Street"),
        ("at 45/7 Hẻm Ba, Phường Bến Nghé, 700000", "45/7 Hẻm Ba, Phường Bến Nghé, 700000"),
        ("at 72 Hoa Lan, Bình xã, 660877", "72 Hoa Lan, Bình xã, 660877"),
        ("at 3 Lê Lợi, Thị trấn Phú Mỹ", "3 Lê Lợi, Thị trấn Phú Mỹ"),
        ("at 12 MAIN STREET, SPRINGFIELD", "12 MAIN STREET, SPRINGFIELD"),
        (nfd("at 45/7 Hẻm Ba, Phường Bến Nghé"), nfd("45/7 Hẻm Ba, Phường Bến Nghé")),
        ("at 1 Ana Street, Bb, Cc, Dd, Ee, Ff", "1 Ana Street, Bb, Cc, Dd, Ee"),
        ("Ship to 12 Main Street today", "12 Main Street"),
        ("at 12 Main Street ORD-12345", "12 Main Street"),
        ("at 12 Main Street, 1234 left", "12 Main Street"),
        ("at 12 Main Street, 1234567", "12 Main Street"),
        ("at 12 Main St., Springfield", "12 Main St., Springfield"),
        ("at 88 Oak Lane Apt. 5B, Riverton, ZZ 99999", "88 Oak Lane Apt. 5B, Riverton, ZZ 99999"),
        ("at 40 Elm Drive Unit 7, Riverton", "40 Elm Drive Unit 7, Riverton"),
        ("at 12 Lê Lợi, phường 5, quận 3 today", "12 Lê Lợi, phường 5, quận 3"),
        ("at 45 Đường 3/2, Quận 10", "45 Đường 3/2, Quận 10"),
        ("at 5 Ngõ 12, Phố Huế", "5 Ngõ 12, Phố Huế"),
        ("at 7 Hẻm 34/5, Phường 5", "7 Hẻm 34/5, Phường 5"),
        ("at 12 Lê Lợi, Tỉnh Bà Rịa-Vũng Tàu", "12 Lê Lợi, Tỉnh Bà Rịa-Vũng Tàu"),
        ("at 5 O'Connell Street, Dublin", "5 O'Connell Street, Dublin"),
        ("at 12 Main Street\nSpringfield, IL 62701", "12 Main Street\nSpringfield, IL 62701"),
        ("at 12 Main  Street, Springfield", "12 Main  Street, Springfield"),
        ("at 12 Main Street,  Springfield", "12 Main Street,  Springfield"),
        ("at 12  Main Street", "12  Main Street"),
    ],
    ids=[
        "vietnamese-round-1",
        "vietnamese-round-1-second",
        "english",
        "house-number-with-a-letter",
        "house-number-with-a-slash",
        "lowercase-address-word",
        "address-word-of-two-words",
        "capitals",
        "decomposed-diacritics",
        "at-most-5-parts",
        "a-part-ends-at-a-lowercase-word",
        "a-part-ends-at-a-code",
        "a-part-ends-at-4-digits",
        "a-part-ends-at-7-digits",
        "abbreviation-with-a-period",
        "number-after-apt",
        "number-after-unit",
        "number-after-phuong-and-quan",
        "number-with-a-slash-after-duong",
        "number-before-a-comma-after-ngo",
        "number-with-a-slash-after-hem",
        "hyphen-in-a-place-name",
        "apostrophe-in-a-place-name",
        "line-break-between-parts",
        "two-spaces-inside-a-part",
        "two-spaces-after-a-comma",
        "two-spaces-after-the-house-number",
    ],
)
def test_a_house_number_and_parts_with_an_address_word_are_an_address(
    message: str, address: str
) -> None:
    assert addresses(message) == [address]


@pytest.mark.parametrize(
    "message",
    [
        "It shipped on 2026-11-18.",
        "See (1) Street lamps below.",
        "The price is 129.00 USD.",
        "The total is 1.250.000 VND.",
        "Call me at 2pm Monday.",
        "A parcel for Springfield.",
        "I got 12 items, Thanks",
        "Order 12345 is late.",
        "I paid 250000 VND.",
        "Send 2 Lamp Shades today.",
        "Mr Lan called.",
        "ref B12 Main Street",
    ],
    ids=[
        "iso-date",
        "list-number",
        "price",
        "order-total",
        "time",
        "city-alone",
        "no-address-word",
        "order-id",
        "amount",
        "capitalized-words-without-an-address-word",
        "title-alone",
        "number-inside-a-code",
    ],
)
def test_other_numbers_and_words_are_no_address(message: str) -> None:
    assert addresses(message) == []


def test_an_address_comes_from_the_rule_source() -> None:
    (detection,) = AddressRuleDetector().detect("at 12 Main Street", ())

    assert detection.pseudonym_type is PseudonymType.ADDRESS
    assert detection.source is DetectionSource.RULE


@pytest.mark.parametrize(
    "address",
    [
        "12 Lê Lợi, Q.1, TP.HCM",
        "12 Lê Lợi, Q. 1, TP. HCM",
        "12 Nguyen Hue, Phuong Ben Nghe, Quan 1",
        "12 Hem 5, Phuong 3",
        "12 Pho Hue, Hai Ba Trung",
    ],
    ids=["abbreviations", "abbreviations-with-spaces", "without-diacritics", "hem", "pho"],
)
def test_an_address_in_everyday_typing_is_one_address(address: str) -> None:
    # The examples of the fourth revision of the design (Layer 1, addresses).
    assert addresses(f"Ship to {address} please") == [address]


UNACCENTED_FORMS = [
    form
    for spelling in VIETNAMESE_ADDRESS_WORDS_UNACCENTED
    for form in (spelling, spelling.upper(), spelling.lower())
]


@pytest.mark.parametrize("word", UNACCENTED_FORMS)
def test_an_address_word_without_diacritics_is_an_address_word(word: str) -> None:
    assert addresses(f"at 12 Le Loi, {word} 5") == [f"12 Le Loi, {word} 5"]


# The design takes 17 spellings without diacritics and leaves out 2 (Layer 1, addresses).
UNACCENTED_SPELLING_COUNT = 17


def without_diacritics(word: str) -> str:
    letters = word.replace("Đ", "D").replace("đ", "d")
    return "".join(character for character in nfd(letters) if not unicodedata.combining(character))


def test_the_spellings_without_diacritics_are_the_vietnamese_words_except_to_and_day() -> None:
    spellings = {without_diacritics(word) for word in VIETNAMESE_ADDRESS_WORDS}
    expected = spellings - set(VIETNAMESE_ADDRESS_WORDS) - {"To", "Day"}

    assert set(VIETNAMESE_ADDRESS_WORDS_UNACCENTED) == expected
    assert len(VIETNAMESE_ADDRESS_WORDS_UNACCENTED) == UNACCENTED_SPELLING_COUNT


@pytest.mark.parametrize(
    "message", ["Delivery takes 1 to 2 weeks", "I paid for 2 day shipping"], ids=["to", "day"]
)
def test_to_and_day_stay_no_address_words(message: str) -> None:
    # "To" and "Day" are also common English words (design, Layer 1, addresses, item 3).
    assert addresses(message) == []


@pytest.mark.parametrize(
    "form", ["Q.10", "P. 5", "P.Bến Nghé", "TP.Hồ Chí Minh", "TP. Hồ Chí Minh", "Tp.HCM", "q.3"]
)
def test_an_abbreviation_with_its_period_is_an_address_word(form: str) -> None:
    assert addresses(f"at 12 Lê Lợi, {form} today") == [f"12 Lê Lợi, {form}"]


def kept_rule_detections(message: str) -> list[tuple[PseudonymType, str]]:
    """The detections of the Vietnamese name rule and the address rule after the overlap rule."""
    found = [
        *VietnameseNameDetector().detect(message, ()),
        *AddressRuleDetector().detect(message, ()),
    ]
    return [(d.pseudonym_type, message[d.start : d.end]) for d in resolve_overlaps(found)]


@pytest.mark.parametrize(
    ("message", "kept"),
    [
        ("Duong Van An", [(PseudonymType.NAME, "Duong Van An")]),
        ("Ngo Van An", [(PseudonymType.NAME, "Ngo Van An")]),
        ("12 Duong Lang, Quan Dong Da", [(PseudonymType.ADDRESS, "12 Duong Lang, Quan Dong Da")]),
    ],
    ids=["duong-alone", "ngo-alone", "duong-in-an-address"],
)
def test_duong_and_ngo_are_a_name_alone_and_an_address_word_in_an_address(
    message: str, kept: list[tuple[PseudonymType, str]]
) -> None:
    assert kept_rule_detections(message) == kept


def test_a_house_number_before_a_family_name_that_is_an_address_word_gives_an_address() -> None:
    # A known limit of the design (Layer 1, addresses): the name is still replaced, with the
    # wrong type.
    assert kept_rule_detections("12 Ngo Van An") == [(PseudonymType.ADDRESS, "12 Ngo Van An")]


def test_a_number_after_to_or_day_ends_the_address() -> None:
    # A known limit of the design (Layer 1, addresses): only an address word keeps the number
    # after it.
    assert addresses("at 12 To 5, Phuong 3") == []


@pytest.mark.parametrize(
    ("message", "found"),
    [
        ("I ordered 2 Pho Bowls", ["2 Pho Bowls"]),
        ("Please send 2 Hem Tapes", ["2 Hem Tapes"]),
        ("mua 2 quan jean", ["2 quan"]),
    ],
    ids=["pho", "hem", "quan"],
)
def test_a_word_spelled_as_an_address_word_starts_an_address_after_a_number(
    message: str, found: list[str]
) -> None:
    # Over-detection, which the design accepts (Layer 1, addresses, known limits).
    assert addresses(message) == found


@pytest.mark.parametrize(
    ("message", "found"),
    [
        ("12 P. Nguyen", ["12 P. Nguyen"]),
        ("Ship to 12 Main Street, P. Nguyen", ["12 Main Street, P. Nguyen"]),
    ],
    ids=["after-a-house-number", "inside-an-address"],
)
def test_an_initial_with_a_capitalized_word_after_it_reads_as_an_abbreviation(
    message: str, found: list[str]
) -> None:
    # A known limit of the design (Layer 1, addresses): the name is still replaced, as part of
    # the address.
    assert addresses(message) == found


@pytest.mark.parametrize(
    "message",
    ["at 12 Lê Lợi, Q1, TPHCM", "at 12 Lê Lợi, tp.hcm", "at 12 Lê Lợi, TX.Thuận An"],
    ids=["without-the-period", "lowercase-after-the-period", "other-abbreviation"],
)
def test_other_forms_of_the_abbreviations_are_read_as_before(message: str) -> None:
    # A known limit of the design (Layer 1, addresses).
    assert addresses(message) == []


def test_a_line_break_joins_a_greeting_to_an_address() -> None:
    # Over-detection, which the design accepts (Layer 1, addresses, known limits).
    assert addresses("at 12 Main Street\nThanks, Lan") == ["12 Main Street\nThanks, Lan"]


def test_a_period_after_an_abbreviation_joins_the_next_sentence() -> None:
    # Over-detection, which the design accepts (Layer 1, addresses, known limits).
    assert addresses("Ship to 12 Main St. Thanks a lot") == ["12 Main St. Thanks"]


def test_p_s_on_the_line_after_an_address_joins_it() -> None:
    # Over-detection, which the design accepts (Layer 1, addresses, known limits).
    assert addresses("Ship to 12 Main Street\nP.S. Thanks") == ["12 Main Street\nP.S"]


def test_a_time_in_capitals_with_periods_after_a_number_gives_an_address() -> None:
    # Over-detection, which the design accepts (Layer 1, addresses, known limits).
    assert addresses("Please deliver before 5 P.M. tomorrow") == ["5 P.M"]


@pytest.mark.parametrize(
    ("message", "found"),
    [
        ("at 12 main street, springfield", []),
        ("at 12 đường lê lợi", ["12 đường"]),
        ("at 12 duong le loi", ["12 duong"]),
    ],
    ids=["english", "vietnamese", "vietnamese-without-diacritics"],
)
def test_a_street_name_in_lowercase_is_no_part_of_an_address(
    message: str, found: list[str]
) -> None:
    # A known limit of the design (Layer 1, addresses): only address words may be in lowercase.
    assert addresses(message) == found


def test_the_abbreviations_are_address_words() -> None:
    assert ABBREVIATED_ADDRESS_WORDS.issubset(ADDRESS_WORDS)
    assert len(set(ADDRESS_WORDS)) == len(ADDRESS_WORDS)


@pytest.mark.parametrize(
    "word", sorted({*ADDRESS_WORDS, *ABBREVIATED_ADDRESS_WORDS, *VIETNAMESE_ABBREVIATIONS})
)
def test_every_address_word_is_in_nfc(word: str) -> None:
    assert unicodedata.is_normalized("NFC", word)


HOUSE_NUMBERS = st.from_regex(r"[1-9][0-9]{0,4}(?:[A-Z]|/[0-9]{1,3})?", fullmatch=True)
PLACE_WORDS = st.sampled_from(["Lê", "Lợi", "Main", "Hoa", "Bến", "Nghé", "Riverton", "Rịa-Vũng"])
ADDRESS_WORD_FORMS = st.sampled_from(
    [
        *ADDRESS_WORDS,
        *(word.lower() for word in ADDRESS_WORDS),
        "St.",
        "Apt. 5",
        "Unit 7B",
        "phường 5",
        "Hẻm 34/5",
        "Q.1",
        "Q. 1",
        "P. 5",
        "P.Bến Nghé",
        "TP.HCM",
        "q.3",
    ]
)
POSTAL_CODES = st.from_regex(r"[0-9]{5,6}", fullmatch=True)
PART_SEPARATORS = st.sampled_from([", ", ",", "\n", ",\n", ",  "])
SPACES = st.sampled_from([" ", " ", "  "])
AFTER_AN_ADDRESS = st.sampled_from(["", " today", ", thanks", "!", " ORD-12"])


@st.composite
def address_part(draw: st.DrawFn) -> list[str]:
    """The elements of one part: capitalized words, address words, and postal codes."""
    element = st.one_of(PLACE_WORDS, ADDRESS_WORD_FORMS, POSTAL_CODES)
    return draw(st.lists(element, min_size=1, max_size=3))


@st.composite
def address_in_context(draw: st.DrawFn) -> tuple[str, int, int]:
    """A sentence in lowercase with one address of 1 to 5 parts that holds an address word."""
    parts = draw(st.lists(address_part(), min_size=1, max_size=ADDRESS_PART_COUNT))
    parts[draw(st.integers(0, len(parts) - 1))].append(draw(ADDRESS_WORD_FORMS))
    body = "".join(
        (draw(PART_SEPARATORS) if index else "") + draw(SPACES).join(part)
        for index, part in enumerate(parts)
    )
    address = f"{draw(HOUSE_NUMBERS)}{draw(SPACES)}{body}"
    form = nfd if draw(st.booleans()) else nfc
    head = "please ship it to "
    return head + form(address) + draw(AFTER_AN_ADDRESS), len(head), len(head) + len(form(address))


@given(address_in_context())
def test_an_address_is_found_whole(case: tuple[str, int, int]) -> None:
    message, start, end = case

    assert addresses(message) == [message[start:end]]


TOKENS = st.one_of(
    HOUSE_NUMBERS,
    PLACE_WORDS,
    ADDRESS_WORD_FORMS,
    POSTAL_CODES,
    st.sampled_from(["the", "parcel", "Thanks", "12", "ORD-12", "2026-11-18", "1.250.000", "x"]),
)
TOKEN_SEPARATORS = st.sampled_from([" ", " ", " ", ", ", ",", "\n", ". ", "  "])
HOUSE_NUMBER_START = re.compile(r"[0-9]{1,5}(?:[^\W\d_]|/[0-9]+)? ")
ADDRESS_WORD_KEYS = {nfc(word).casefold() for word in ADDRESS_WORDS}
ABBREVIATION_START = re.compile(rf"(?:{'|'.join(VIETNAMESE_ABBREVIATIONS)})\.", re.IGNORECASE)


@st.composite
def text_with_numbers(draw: st.DrawFn) -> str:
    """A text of house numbers, place words, address words, postal codes, and other words."""
    tokens = draw(st.lists(TOKENS, min_size=1, max_size=12))
    return "".join(token + draw(TOKEN_SEPARATORS) for token in tokens)


def address_word_flags(text: str) -> list[tuple[str, bool]]:
    """Each word of an address, and whether it is an address word or part of one of two words.

    A word that starts with "Q.", "P.", or "TP." is an address word too, as in "Q.1" or "TP.HCM".
    """
    raw_words = [nfc(word) for word in re.split(r"[\s,]+", text) if word]
    words = [word.rstrip(".") for word in raw_words]
    keys = [word.casefold() for word in words]
    pairs = {f"{first} {second}" for first, second in pairwise(keys)}
    in_pair = {key for pair in pairs & ADDRESS_WORD_KEYS for key in pair.split(" ")}
    return [
        (
            word,
            key in ADDRESS_WORD_KEYS or key in in_pair or ABBREVIATION_START.match(raw) is not None,
        )
        for word, key, raw in zip(words, keys, raw_words, strict=True)
    ]


def address_faults(message: str, detection: Detection) -> list[str]:
    """Name each invariant of the design (Layer 1, addresses) that one address breaks."""
    text = message[detection.start : detection.end]
    flags = address_word_flags(text)
    faults: list[str] = []
    if HOUSE_NUMBER_START.match(text) is None:
        faults.append("A1: an address that does not start with a house number and a space")
    if re.search(r"\w\Z|[^\W_][-./@]\Z", message[: detection.start]):
        faults.append("A1: a house number joined to the text before it")
    if len(re.findall(r",?\r?\n|,", text)) >= ADDRESS_PART_COUNT:
        faults.append("A2: more than 5 parts")
    if any(word[0].islower() and not is_address_word for word, is_address_word in flags):
        faults.append("A2: a word in lowercase that is no address word")
    if not any(is_address_word for _, is_address_word in flags):
        faults.append("A3: an address without an address word")
    return faults


def text_faults(message: str) -> list[str]:
    """Name each invariant of the design that an address found in the message breaks."""
    return [
        fault
        for detection in AddressRuleDetector().detect(message, ())
        for fault in address_faults(message, detection)
    ]


@given(text_with_numbers())
def test_an_address_keeps_every_invariant_of_the_design(message: str) -> None:
    assert text_faults(message) == []


ADDRESS_LENGTH = 42
INNER_SPANS = st.lists(st.tuples(st.integers(1, 20), st.integers(1, 20)), max_size=4)


def names_inside(start: int, inner: list[tuple[int, int]]) -> list[Detection]:
    """Names of the model at the given offsets and sizes, all inside one address."""
    return [
        Detection(
            start + offset, start + offset + size, PseudonymType.NAME, DetectionSource.NAMED_ENTITY
        )
        for offset, size in inner
    ]


@given(st.integers(0, 40), INNER_SPANS)
def test_an_address_replaces_the_names_inside_it(start: int, inner: list[tuple[int, int]]) -> None:
    address = Detection(start, start + ADDRESS_LENGTH, PseudonymType.ADDRESS, DetectionSource.RULE)

    kept = resolve_overlaps([address, *names_inside(start, inner)])

    assert kept == (address,)

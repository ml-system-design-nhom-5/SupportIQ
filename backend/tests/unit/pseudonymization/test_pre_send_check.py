"""Tests of the pre-send check of layer 2 (ADR-0029, statement 4; leak fixes design, Layer 2).

Each finding of the design has at least five positive and five negative examples (ADR-0029,
statement 8), and the invariants of the design are property-based tests (TEST-13). Every value
is synthetic (TEST-18).
"""

import unicodedata
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.pseudonymization.domain import (
    CURRENCY_WORDS,
    NAME_NEIGHBOUR_STOPLIST,
    PHONE_SEPARATORS,
    KnownValue,
    PersonalDataLeftError,
    PseudonymEntry,
    PseudonymType,
    check_nothing_left,
)
from app.pseudonymization.domain.detection import fold_value

NAME = PseudonymType.NAME
PHONE = PseudonymType.PHONE
CARD = PseudonymType.CARD
EMAIL = PseudonymType.EMAIL
ADDRESS = PseudonymType.ADDRESS
ORDER_ID = PseudonymType.ORDER_ID
LITERAL = PseudonymType.LITERAL


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def entry(pseudonym: str, pseudonym_type: PseudonymType, value: str) -> PseudonymEntry:
    return PseudonymEntry(pseudonym, pseudonym_type, value)


def finding(
    text: str,
    entries: tuple[PseudonymEntry, ...] = (),
    known_values: tuple[KnownValue, ...] = (),
) -> PseudonymType | None:
    """The type that the check reports, or None when the text passes."""
    try:
        check_nothing_left(text, entries, known_values)
    except PersonalDataLeftError as error:
        return error.pseudonym_type
    return None


LAN_ANH = entry("[NAME_1]", NAME, "Lan Anh")
BUI_THI_AN = entry("[NAME_1]", NAME, "Bùi Thị An")
PHONE_ENTRY = entry("[PHONE_1]", PHONE, "0901110001")
PHONE_WITH_AN_EXTENSION = entry("[PHONE_1]", PHONE, "0901 110 001 x12")
CARD_ENTRY = entry("[CARD_1]", CARD, "4111 1111 1111 1111")
EMAIL_ENTRY = entry("[EMAIL_1]", EMAIL, "k@example.test")


@pytest.mark.parametrize(
    ("text", "map_entry", "expected"),
    [
        ("[NAME_1] called. Later Lan Anh called again.", LAN_ANH, NAME),
        ("[NAME_1] wrote, then bui thi an wrote", BUI_THI_AN, NAME),
        (nfd("[NAME_1] wrote, then Bùi Thị An wrote"), BUI_THI_AN, NAME),
        ("[PHONE_1] or 0901 110 001", PHONE_ENTRY, PHONE),
        ("[PHONE_1], also 09011100012", PHONE_ENTRY, PHONE),
        ("[CARD_1], again 4111-1111-1111-1111", CARD_ENTRY, CARD),
        ("[EMAIL_1] or K@Example.test", EMAIL_ENTRY, EMAIL),
        ("call [PHONE_1] or 0901 110 001 x12 again", PHONE_WITH_AN_EXTENSION, PHONE),
        ("call [PHONE_1] or 0901-110-001 again", PHONE_WITH_AN_EXTENSION, PHONE),
        ("call [PHONE_1] or 0901110001", entry("[PHONE_1]", PHONE, "0901110001x12"), PHONE),
    ],
    ids=[
        "name-again",
        "name-without-case-and-diacritics",
        "name-decomposed",
        "phone-with-other-separators",
        "phone-in-a-longer-run",
        "card-with-hyphens",
        "email-in-capitals",
        "phone-with-its-extension",
        "phone-without-its-extension",
        "phone-without-its-joined-extension",
    ],
)
def test_a_value_of_the_map_outside_a_placeholder_is_found(
    text: str, map_entry: PseudonymEntry, expected: PseudonymType
) -> None:
    assert finding(text, (map_entry,)) is expected


@pytest.mark.parametrize(
    ("text", "map_entry"),
    [
        ("[NAME_1] called and left.", LAN_ANH),
        ("[NAME_1] and Lan Anhs", LAN_ANH),
        ("[PHONE_1] and code 0901 x 110001", PHONE_ENTRY),
        ("0901 [PHONE_1] 110001", PHONE_ENTRY),
        ("[LITERAL_1] and [name] too", entry("[LITERAL_1]", LITERAL, "[NAME]")),
        ("[CARD_1] paid", CARD_ENTRY),
        ("[NAME_1] and a [NAME] mask", entry("[NAME_1]", NAME, "Name")),
        ("call [PHONE_1], ext. 12", entry("[PHONE_1]", PHONE, "0901110001x12")),
    ],
    ids=[
        "value-only-in-its-placeholder",
        "part-of-a-longer-word",
        "digits-split-by-a-letter",
        "digits-split-by-a-placeholder",
        "literal-entry",
        "card-only-in-its-placeholder",
        "letters-of-a-placeholder",
        "extension-alone",
    ],
)
def test_a_value_of_the_map_only_inside_placeholders_passes(
    text: str, map_entry: PseudonymEntry
) -> None:
    assert finding(text, (map_entry,)) is None


@pytest.mark.parametrize(
    ("text", "known_value", "expected"),
    [
        ("call 0901-110-001", KnownValue(PHONE, "0901110001"), PHONE),
        ("call (090) 111-0001", KnownValue(PHONE, "0901110001"), PHONE),
        ("call 09011100012", KnownValue(PHONE, "0901110001"), PHONE),
        ("mail LAN@EXAMPLE.TEST", KnownValue(EMAIL, "lan@example.test"), EMAIL),
        ("from bui thi an", KnownValue(NAME, "Bùi Thị An"), NAME),
        ("about ord-2026-0001", KnownValue(ORDER_ID, "ORD-2026-0001"), ORDER_ID),
    ],
    ids=["hyphens", "parentheses", "longer-run", "email", "name", "order-id"],
)
def test_a_known_value_outside_a_placeholder_is_found(
    text: str, known_value: KnownValue, expected: PseudonymType
) -> None:
    assert finding(text, known_values=(known_value,)) is expected


@pytest.mark.parametrize(
    ("text", "known_value"),
    [
        ("call [PHONE_1] only", KnownValue(PHONE, "0901110001")),
        ("order 0901 11 total 0001", KnownValue(PHONE, "0901110001")),
        ("call 0901-110-002", KnownValue(PHONE, "0901110001")),
        ("Bùi Thị Anh came", KnownValue(NAME, "Bùi Thị An")),
        ("write to [EMAIL_1].", KnownValue(EMAIL, "lan@example.test")),
        ("paid by [CARD_1]", KnownValue(CARD, "4111111111111111")),
    ],
    ids=[
        "inside-its-placeholder",
        "digits-in-two-runs",
        "other-digits",
        "longer-word",
        "email-in-its-placeholder",
        "card-in-its-placeholder",
    ],
)
def test_a_known_value_only_inside_placeholders_passes(text: str, known_value: KnownValue) -> None:
    assert finding(text, known_values=(known_value,)) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("call [PHONE_1]-3701x6147", PHONE),
        ("see Vũ[NAME_1] now", NAME),
        (nfd("see Vũ[NAME_1] now"), NAME),
        ("see [NAME_1]x now", NAME),
        ("mail lan.[EMAIL_1] now", EMAIL),
        ("at [ADDRESS_1]/12 now", ADDRESS),
        ("order [ORDER_ID_1]7 now", ORDER_ID),
    ],
    ids=[
        "extension-after",
        "letters-before",
        "decomposed-letters-before",
        "letter-after",
        "dot-before",
        "slash-after",
        "digit-after",
    ],
)
def test_a_letter_or_digit_joined_to_a_placeholder_is_found(
    text: str, expected: PseudonymType
) -> None:
    assert finding(text) is expected


@pytest.mark.parametrize(
    "text",
    [
        "write to [EMAIL_1].",
        "dear [NAME_1], hi",
        "call ([PHONE_1]) now",
        "this is [NAME_1]'s order",
        "[NAME_1]-[NAME_2] came",
        "call [PHONE_1] - today",
    ],
    ids=[
        "period-at-the-end",
        "comma-after",
        "parentheses",
        "apostrophe",
        "hyphen-between-placeholders",
        "spaces-around-a-hyphen",
    ],
)
def test_punctuation_beside_a_placeholder_passes(text: str) -> None:
    assert finding(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Regards, Vũ [NAME_1]",
        nfd("Regards, Vũ [NAME_1]"),
        "please ask [NAME_1] Pham today",
        "a note from Jean-Pierre [NAME_1] today",
        "a note from [NAME_1] Pierre-Jean today",
        "call Lan [NAME_1] today",
        "so Vũ  [NAME_1] wrote",
        "ask [NAME_1]  Pham today",
    ],
    ids=[
        "word-before-in-a-sentence",
        "decomposed-word-before",
        "word-after",
        "word-before-after-a-hyphen",
        "word-after-before-a-hyphen",
        "given-name-before",
        "two-spaces-before",
        "two-spaces-after",
    ],
)
def test_a_capitalized_word_beside_a_name_is_found(text: str) -> None:
    assert finding(text) is NAME


@pytest.mark.parametrize(
    "text",
    [
        "and I [NAME_1] agree",
        "Thanks [NAME_1]",
        "Hello [NAME_1]. Please call",
        "This is [NAME_1] I want",
        "Bà [NAME_1] called",
        nfd("so Bà [NAME_1] called"),
        "Vũ [NAME_1] called.",
        "Hello. Vũ [NAME_1] called.",
        "please see [NAME_1] today",
        "see Vũ [ADDRESS_1] today",
    ],
    ids=[
        "i",
        "thanks",
        "period-and-please",
        "start-of-the-text-and-i",
        "title",
        "decomposed-title",
        "start-of-the-text",
        "start-of-a-sentence",
        "lowercase-words",
        "not-a-name-placeholder",
    ],
)
def test_other_words_beside_a_name_pass(text: str) -> None:
    assert finding(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("72 [NAME_1], [NAME_2] xã, 660877", NAME),
        ("ship to 12 [ADDRESS_1] now", ADDRESS),
        ("ship to [ADDRESS_1], 700000", ADDRESS),
        ("ship to [NAME_1] xã, 660877", NAME),
        ("I need 2 [NAME_1] shoes", NAME),
        ("ship to [ADDRESS_1],12345", ADDRESS),
        ("72  [NAME_1] called", NAME),
    ],
    ids=[
        "house-number-and-postal-code",
        "house-number-before-an-address",
        "postal-code-after-an-address",
        "postal-code-after-a-name",
        "quantity-before-a-name",
        "postal-code-without-a-space",
        "house-number-two-spaces-before",
    ],
)
def test_a_number_beside_a_name_or_an_address_is_found(text: str, expected: PseudonymType) -> None:
    assert finding(text) is expected


@pytest.mark.parametrize(
    "text",
    [
        "ship to [ADDRESS_1], 250000 VND",
        "ship to [ADDRESS_1], 250000đ",
        "ship to [ADDRESS_1], 25000 USD",
        "ship to [ADDRESS_1], 99999$",
        "ship to [ADDRESS_1], $250000 total",
        "ship to [ADDRESS_1], USD 250000",
        "dear [NAME_1], order 1234 is late",
        "send 12 [EMAIL_1] now",
        "ship to [ADDRESS_1], ok, 123456",
        "No placeholder here, 123456.",
        "ref 123456 [NAME_1] called",
    ],
    ids=[
        "amount-in-vnd",
        "amount-in-dong",
        "amount-in-usd",
        "amount-in-dollars",
        "dollar-sign-before",
        "usd-before",
        "four-digits-after",
        "not-a-name-or-an-address",
        "two-parts-after",
        "no-placeholder",
        "six-digits-before",
    ],
)
def test_other_numbers_beside_a_placeholder_pass(text: str) -> None:
    assert finding(text) is None


def test_a_placeholder_inside_a_url_path_stops_the_ticket() -> None:
    # A false stop, which the design accepts (Layer 2, known limits): "/" joins the placeholder.
    assert finding("see https://shop.test/orders/[ORDER_ID_1] now") is ORDER_ID


@pytest.mark.parametrize(
    ("phone", "digits"),
    [
        ("(00)504-5188", "005045188"),
        ("+1 (393) 722-1568", "13937221568"),
        ("590-224-0978", "5902240978"),
        ("810.651.1446", "8106511446"),
        ("+1-393-722-1568", "13937221568"),
    ],
)
def test_every_phone_format_of_layer_1_is_one_run_of_the_check(phone: str, digits: str) -> None:
    known_value = KnownValue(PHONE, digits)

    assert finding(f"call {phone} now", known_values=(known_value,)) is PHONE


def test_the_separators_of_a_card_are_phone_separators() -> None:
    assert set(" -").issubset(PHONE_SEPARATORS)


VALUES = st.sampled_from(
    [
        (NAME, "Lan Anh"),
        (NAME, "Bùi Thị An"),
        (NAME, "Đặng Thu Hà"),
        (EMAIL, "lan.anh@example.test"),
        (ADDRESS, "12 Main Street"),
        (ADDRESS, "45/7 Hẻm Ba"),
        (ORDER_ID, "ORD-2026-0001"),
    ]
)
SPELLINGS = st.sampled_from([str, str.upper, str.lower, fold_value, nfd])
BEFORE_A_VALUE = st.sampled_from(["", "about ", "(", "and "])
AFTER_A_VALUE = st.sampled_from(["", " now", ").", ", ok"])


@st.composite
def value_outside(draw: st.DrawFn) -> tuple[str, PseudonymType, str]:
    """A text with a placeholder, and its value again outside it, spelled in some way."""
    pseudonym_type, value = draw(VALUES)
    spelled = draw(SPELLINGS)(value)
    text = f"[{pseudonym_type}_1] said {draw(BEFORE_A_VALUE)}{spelled}{draw(AFTER_A_VALUE)}"
    return text, pseudonym_type, value


@given(value_outside())
def test_a_value_of_the_map_outside_a_placeholder_is_always_found(
    case: tuple[str, PseudonymType, str],
) -> None:
    text, pseudonym_type, value = case

    reported = finding(text, (entry(f"[{pseudonym_type}_1]", pseudonym_type, value),))

    assert reported is pseudonym_type


@given(value_outside())
def test_a_known_value_outside_a_placeholder_is_always_found(
    case: tuple[str, PseudonymType, str],
) -> None:
    text, pseudonym_type, value = case

    reported = finding(text, known_values=(KnownValue(pseudonym_type, value),))

    assert reported is pseudonym_type


SEPARATOR_STRINGS = st.text(alphabet=PHONE_SEPARATORS, min_size=1, max_size=2)


@st.composite
def regrouped_digits(draw: st.DrawFn) -> tuple[PseudonymType, str, str]:
    """A phone or card number, and the same digits regrouped with separators of the check."""
    pseudonym_type = draw(st.sampled_from([PHONE, CARD]))
    digits = draw(st.from_regex(r"[0-9]{9,19}", fullmatch=True))
    cuts = sorted(set(draw(st.lists(st.integers(1, len(digits) - 1), max_size=4))))
    groups = [digits[start:end] for start, end in pairwise([0, *cuts, len(digits)])]
    first = f"({groups[0]})" if draw(st.booleans()) else groups[0]
    rest = "".join(draw(SEPARATOR_STRINGS) + group for group in groups[1:])
    longer = draw(st.sampled_from([("", ""), ("84", ""), ("", "2")]))
    return pseudonym_type, digits, f"{longer[0]}{first}{rest}{longer[1]}"


@given(regrouped_digits())
def test_regrouped_digits_of_a_number_are_always_found(
    case: tuple[PseudonymType, str, str],
) -> None:
    pseudonym_type, digits, written = case
    map_entry = entry(f"[{pseudonym_type}_1]", pseudonym_type, digits)

    assert finding(f"[{pseudonym_type}_1], or {written} now", (map_entry,)) is pseudonym_type


MAP = (
    entry("[NAME_1]", NAME, "Lan Anh"),
    entry("[PHONE_1]", PHONE, "0901110001"),
    entry("[ADDRESS_1]", ADDRESS, "12 Main Street"),
    entry("[EMAIL_1]", EMAIL, "lan.anh@example.test"),
)
PLACEHOLDERS = st.sampled_from([map_entry.pseudonym for map_entry in MAP])
TYPED_PLACEHOLDERS = st.sampled_from(
    [(map_entry.pseudonym_type, map_entry.pseudonym) for map_entry in MAP]
)
JOINS = st.sampled_from([" ", ", ", ". "])


@st.composite
def placeholders_only(draw: st.DrawFn) -> str:
    """A text of placeholders of the map, joined by spaces, commas, or periods."""
    placeholders = draw(st.lists(PLACEHOLDERS, min_size=1, max_size=6))
    return "".join(draw(JOINS) + placeholder for placeholder in placeholders).strip(" ,.")


@given(placeholders_only())
def test_a_text_of_placeholders_only_always_passes(text: str) -> None:
    assert finding(text, MAP) is None


LITERAL_VALUES = st.sampled_from(["[NAME]", "[name]", "Lan Anh", "0901110001", "[PHONE_1]"])


@given(placeholders_only(), LITERAL_VALUES)
def test_a_literal_entry_never_stops_a_text(text: str, literal_value: str) -> None:
    literal = entry("[LITERAL_1]", LITERAL, literal_value)

    assert finding(f"{text} and {literal_value}", (literal,)) is None


JOINERS = st.sampled_from(["", "-", ".", "/", "x", "@"])
JOINED = st.sampled_from(["a", "Z", "7", "Vũ"])


@st.composite
def joined_text(draw: st.DrawFn) -> tuple[str, PseudonymType]:
    """A text with one placeholder that a letter or digit is joined to, on either side."""
    pseudonym_type, placeholder = draw(TYPED_PLACEHOLDERS)
    joined, joiner = draw(JOINED), draw(JOINERS)
    before = f"{joined}{joiner}{placeholder}"
    after = f"{placeholder}{joiner}{joined}"
    return f"see {before if draw(st.booleans()) else after} now", pseudonym_type


@given(joined_text())
def test_a_letter_or_digit_joined_to_a_placeholder_is_always_found(
    case: tuple[str, PseudonymType],
) -> None:
    text, pseudonym_type = case

    assert finding(text, MAP) is pseudonym_type


NAME_WORDS = st.sampled_from(["Pham", "Vũ", nfd("Vũ"), "Pierre", "Kathryn", "Ánh"])
STOPLIST_WORDS = st.sampled_from(sorted(NAME_NEIGHBOUR_STOPLIST))


SPACES = st.sampled_from([" ", "  ", "   "])


@given(NAME_WORDS, SPACES, st.booleans())
def test_a_name_word_beside_a_name_in_a_sentence_is_always_found(
    word: str, spaces: str, before: bool
) -> None:
    text = f"ask {word}{spaces}[NAME_1] today" if before else f"ask [NAME_1]{spaces}{word} today"

    assert finding(text, MAP) is NAME


@given(NAME_WORDS, st.sampled_from(["", "Hello. ", "Is it late? "]))
def test_a_name_word_that_starts_a_sentence_passes(word: str, sentence_before: str) -> None:
    assert finding(f"{sentence_before}{word} [NAME_1] called.", MAP) is None


@given(STOPLIST_WORDS, st.booleans())
def test_a_stoplist_word_beside_a_name_always_passes(word: str, before: bool) -> None:
    text = f"so {word} [NAME_1] called" if before else f"ask [NAME_1] {word} now"

    assert finding(text, MAP) is None


HOUSE_NUMBERS = st.from_regex(r"[0-9]{1,5}", fullmatch=True)
POSTAL_CODES = st.from_regex(r"[0-9]{5,6}", fullmatch=True)
RESIDUE_PLACEHOLDERS = st.sampled_from([(NAME, "[NAME_1]"), (ADDRESS, "[ADDRESS_1]")])
CURRENCIES = st.sampled_from([*CURRENCY_WORDS, *(f" {word}" for word in CURRENCY_WORDS)])


@given(HOUSE_NUMBERS, RESIDUE_PLACEHOLDERS)
def test_a_number_right_before_a_name_or_an_address_is_always_found(
    number: str, placeholder: tuple[PseudonymType, str]
) -> None:
    pseudonym_type, pseudonym = placeholder

    assert finding(f"ship to {number} {pseudonym} now", MAP) is pseudonym_type


@given(POSTAL_CODES, RESIDUE_PLACEHOLDERS)
def test_a_postal_code_in_the_part_after_is_always_found(
    code: str, placeholder: tuple[PseudonymType, str]
) -> None:
    pseudonym_type, pseudonym = placeholder

    assert finding(f"ship to {pseudonym}, {code}", MAP) is pseudonym_type


@given(POSTAL_CODES, RESIDUE_PLACEHOLDERS, CURRENCIES)
def test_an_amount_in_the_part_after_passes(
    code: str, placeholder: tuple[PseudonymType, str], currency: str
) -> None:
    assert finding(f"ship to {placeholder[1]}, {code}{currency}", MAP) is None


CURRENCIES_BEFORE = st.sampled_from(
    [
        *CURRENCY_WORDS,
        *(f"{word} " for word in CURRENCY_WORDS),
        *(word.lower() for word in CURRENCY_WORDS),
    ]
)


@given(POSTAL_CODES, RESIDUE_PLACEHOLDERS, CURRENCIES_BEFORE)
def test_an_amount_with_its_currency_first_passes(
    code: str, placeholder: tuple[PseudonymType, str], currency: str
) -> None:
    assert finding(f"ship to {placeholder[1]}, {currency}{code} total", MAP) is None


def leak_error(text: str, map_entry: PseudonymEntry) -> PersonalDataLeftError:
    """The error that the check raises for a text with a value of the map outside it."""
    with pytest.raises(PersonalDataLeftError) as raised:
        check_nothing_left(text, (map_entry,), ())
    return raised.value


@given(value_outside())
def test_the_error_holds_no_value(case: tuple[str, PseudonymType, str]) -> None:
    text, pseudonym_type, value = case
    error = leak_error(text, entry(f"[{pseudonym_type}_1]", pseudonym_type, value))

    shown = f"{error!s} {error!r} {error.args!r}"

    assert value not in shown
    assert value.lower() not in shown.lower()

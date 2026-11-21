"""Tests of the detectors, the overlap rule, the map, and restoration (ADR-0010).

Each detector has at least five positive and five negative examples, with the boundary
formats of ADR-0010 (ADR-0010, Detection). Every value is synthetic (TEST-18).
"""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.pseudonymization.domain import (
    PSEUDONYMIZED_TEXT_MAX_LENGTH,
    AddressRuleDetector,
    Detection,
    DetectionSource,
    KnownValue,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    PseudonymEntry,
    PseudonymizedTextTooLongError,
    PseudonymType,
    VietnameseNameDetector,
    build_pseudonymized_message,
    contains_placeholder,
    drop_product_names,
    is_luhn_valid,
    resolve_overlaps,
    restore_pseudonyms,
)

NAME = KnownValue(PseudonymType.NAME, "Bùi Thị An")
EMAIL = KnownValue(PseudonymType.EMAIL, "an.bui@example.test")
PHONE = KnownValue(PseudonymType.PHONE, "+84 90 111 0001")
ORDER = KnownValue(PseudonymType.ORDER_ID, "ORD-20901")
ADDRESS = KnownValue(PseudonymType.ADDRESS, "12 Example Street, Ba Dinh, Hanoi")
KNOWN_VALUES = (NAME, EMAIL, PHONE, ORDER, ADDRESS)
VALID_CARD = "4111 1111 1111 1111"


def found(detections: tuple[Detection, ...], message: str) -> list[tuple[PseudonymType, str]]:
    return [
        (detection.pseudonym_type, message[detection.start : detection.end])
        for detection in sorted(detections, key=lambda detection: detection.start)
    ]


@pytest.mark.parametrize(
    "message",
    [
        "Please check [NAME_1].",
        "[EMAIL] is mine",
        "Order [ORDER_ID_999] arrived",
        "Use [LITERAL] here",
        "Two: [PHONE_2][CARD_3]",
    ],
)
def test_literal_detector_finds_text_that_looks_like_a_placeholder(message: str) -> None:
    detections = LiteralPlaceholderDetector().detect(message, ())

    assert detections
    assert {detection.pseudonym_type for detection in detections} == {PseudonymType.LITERAL}


@pytest.mark.parametrize(
    "message",
    ["[NAME_0]", "[NAME_1000]", "[name_1]", "[ORDER]", "[ NAME_1 ]"],
)
def test_literal_detector_ignores_text_outside_the_placeholder_syntax(message: str) -> None:
    detections = LiteralPlaceholderDetector().detect(message, ())

    assert detections == ()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("I am Bui Thi An.", (PseudonymType.NAME, "Bui Thi An")),
        ("BÙI THỊ AN here", (PseudonymType.NAME, "BÙI THỊ AN")),
        ("Mail an.bui@example.test now", (PseudonymType.EMAIL, "an.bui@example.test")),
        ("Call +84 90 111 0001 please", (PseudonymType.PHONE, "+84 90 111 0001")),
        ("Ship to 12 Example Street, Ba Dinh, Hanoi.", (PseudonymType.ADDRESS, ADDRESS.text)),
        ("Order ORD-20901 is late", (PseudonymType.ORDER_ID, "ORD-20901")),
    ],
)
def test_known_value_detector_finds_whole_words_ignoring_case_and_diacritics(
    message: str, expected: tuple[PseudonymType, str]
) -> None:
    detections = KnownValueDetector().detect(message, KNOWN_VALUES)

    assert expected in found(detections, message)


@pytest.mark.parametrize(
    "message",
    [
        "Bui Thi Anh is my sister",
        "an.bui@example.testing",
        "ORD-209012",
        "My street is Example",
        "Nothing personal here",
    ],
)
def test_known_value_detector_ignores_parts_of_longer_words(message: str) -> None:
    detections = KnownValueDetector().detect(message, (NAME, EMAIL, ORDER, ADDRESS))

    assert found(detections, message) == []


def test_known_value_detector_maps_folded_positions_back_to_the_message() -> None:
    message = "Xin chào Đặng Văn Bình."

    detections = KnownValueDetector().detect(
        message, (KnownValue(PseudonymType.NAME, "Dang Van Binh"),)
    )

    assert found(detections, message) == [(PseudonymType.NAME, "Đặng Văn Bình")]


def pattern_detections(message: str) -> list[tuple[PseudonymType, str]]:
    return found(resolve_overlaps(PatternDetector().detect(message, ())), message)


def detected_types(message: str) -> set[PseudonymType]:
    return {pseudonym_type for pseudonym_type, _text in pattern_detections(message)}


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("write to lan.tran@example.test", "lan.tran@example.test"),
        ("a.b+c@sub.example.org", "a.b+c@sub.example.org"),
        ("MAIL: Minh.Le@Example.Test", "Minh.Le@Example.Test"),
        ("x_y-z@ex-ample.test.", "x_y-z@ex-ample.test"),
        ("<an@example.test>", "an@example.test"),
    ],
)
def test_email_pattern_finds_a_local_part_at_and_a_dotted_domain(
    message: str, expected: str
) -> None:
    assert pattern_detections(message) == [(PseudonymType.EMAIL, expected)]


@pytest.mark.parametrize(
    "message",
    [
        "my mail is lan at example",
        "user@localhost",
        "@example.test",
        "lan@.test",
        "lan@example.",
    ],
)
def test_email_pattern_ignores_text_without_both_parts(message: str) -> None:
    assert PseudonymType.EMAIL not in detected_types(message)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("call 090111000", "090111000"),
        ("call +84 9011 1000 12346", "+84 9011 1000 12346"),
        ("call 0901110001 2pm", "0901110001"),
        ("call 090.111.0003", "090.111.0003"),
        ("call +84 90 111 0002", "+84 90 111 0002"),
        ("reach me at 090-111-0004.", "090-111-0004"),
    ],
    ids=["9-digits", "15-digits", "before-a-time", "dots", "plus", "hyphens"],
)
def test_phone_pattern_finds_9_to_15_digits_in_whole_groups(message: str, expected: str) -> None:
    assert pattern_detections(message) == [(PseudonymType.PHONE, expected)]


@pytest.mark.parametrize(
    "message",
    [
        "call 09011100",
        "call 0901110001234567",
        "code A0901110001",
        "call 0901110001pm",
        "price 129.00 USD",
        "room 12 34 56 78",
    ],
    ids=["8-digits", "16-digits", "after-a-letter", "before-a-letter", "price", "short-groups"],
)
def test_phone_pattern_ignores_other_numbers(message: str) -> None:
    assert PseudonymType.PHONE not in detected_types(message)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("call (00)504-5188 now", "(00)504-5188"),
        ("call +1 (393) 722-1568", "+1 (393) 722-1568"),
        ("call (02838) 291-234", "(02838) 291-234"),
        ("(1) 090-111-0004", "090-111-0004"),
        ("call 590-224-0978x548", "590-224-0978x548"),
        ("call 810.651.1446x46429.", "810.651.1446x46429"),
        ("call +1-393-722-1568x72928", "+1-393-722-1568x72928"),
        ("call 0901110001ext.12", "0901110001ext.12"),
        ("call 0901110001ext123456", "0901110001ext123456"),
    ],
    ids=[
        "2-digit-parenthesis",
        "plus-country-and-parenthesis",
        "5-digit-parenthesis",
        "after-a-list-number",
        "x-extension",
        "x-extension-before-a-dot",
        "plus-and-x-extension",
        "ext-dot-extension",
        "6-digit-extension",
    ],
)
def test_phone_pattern_finds_a_first_group_in_parentheses_and_an_extension(
    message: str, expected: str
) -> None:
    assert pattern_detections(message) == [(PseudonymType.PHONE, expected)]


@pytest.mark.parametrize(
    "message",
    [
        "see (1) 2026-11-18",
        "call (123456) 789-0123",
        "meet at 2pm",
        "total 1.250.000 VND",
        "call 0901110001x1234567",
        "call 0901110001x",
        "call 0901110001ext12a",
    ],
    ids=[
        "list-number-and-date",
        "6-digit-parenthesis",
        "time",
        "order-total",
        "7-digit-extension",
        "extension-without-digits",
        "letter-after-the-extension",
    ],
)
def test_phone_pattern_ignores_a_number_with_an_unfit_parenthesis_or_extension(
    message: str,
) -> None:
    assert PseudonymType.PHONE not in detected_types(message)


def test_an_extension_after_a_space_is_not_part_of_the_value_a_known_limit() -> None:
    # The extension must come right after the last group (personal-data leak fixes design,
    # Layer 1, phone): a known limit, stated as it is.
    message = "call 0901 110 001 ext. 12"

    assert pattern_detections(message) == [(PseudonymType.PHONE, "0901 110 001")]


# The digit counts of ADR-0029, statement 1: the number, its first group in parentheses, and its
# extension.
PHONE_DIGITS = range(9, 16)
PARENTHESIZED_DIGITS = range(2, 6)
EXTENSION_DIGITS = range(1, 7)
DIGITS = "0123456789"
PHONE_EXTENSION = re.compile(r"(?:x|ext\.?)[0-9]{1,6}")
GROUP_SEPARATORS = st.sampled_from([" ", ".", "-"])


def digit_text(counts: range) -> st.SearchStrategy[str]:
    return st.text(DIGITS, min_size=counts.start, max_size=counts.stop - 1)


@st.composite
def phone_numbers(draw: st.DrawFn) -> str:
    """A phone number of the forms of ADR-0029, statement 1, with or without an extension."""
    digits = draw(digit_text(PHONE_DIGITS))
    cuts = sorted(draw(st.sets(st.integers(1, len(digits) - 1), max_size=4)))
    groups = [
        digits[start:end] for start, end in zip([0, *cuts], [*cuts, len(digits)], strict=True)
    ]
    in_parentheses = len(groups) > 1 and len(groups[0]) in PARENTHESIZED_DIGITS
    if in_parentheses and draw(st.booleans()):
        after = draw(st.sampled_from(["", " ", ".", "-"]))
        number = f"({groups[0]}){after}" + draw(GROUP_SEPARATORS).join(groups[1:])
    else:
        number = draw(st.sampled_from(["", "+"])) + draw(GROUP_SEPARATORS).join(groups)
    extension = draw(st.sampled_from(["", "x", "ext", "ext."]))
    if extension:
        extension += draw(digit_text(EXTENSION_DIGITS))
    return number + extension


def phone_detections(text: str) -> list[Detection]:
    # Before the overlap rule, where a card number of equal length would win.
    return [
        detection
        for detection in PatternDetector().detect(text, ())
        if detection.pseudonym_type is PseudonymType.PHONE
    ]


def phone_value_faults(text: str) -> list[str]:
    """Name each rule of ADR-0029, statement 1, that a phone value found in the text breaks."""
    faults: list[str] = []
    for detection in phone_detections(text):
        value = text[detection.start : detection.end]
        extension = PHONE_EXTENSION.search(value)
        number = value[: extension.start()] if extension else value
        if extension is not None and extension.end() != len(value):
            faults.append(f"{value!r}: the extension is not at the end")
        if sum(character.isdigit() for character in number) not in PHONE_DIGITS:
            faults.append(f"{value!r}: not 9 to 15 digits besides the extension")
        groups = re.findall(r"\(([0-9]*)\)", number)
        if any(len(group) not in PARENTHESIZED_DIGITS for group in groups):
            faults.append(f"{value!r}: a group in parentheses without 2 to 5 digits")
        if detection.end < len(text) and text[detection.end].isalnum():
            faults.append(f"{value!r}: a letter or digit right after the value")
    return faults


@given(phone_numbers())
def test_a_phone_number_of_the_statement_is_found_whole(number: str) -> None:
    message = f"call {number} now"

    longest = max(phone_detections(message), key=lambda detection: detection.length)

    assert message[longest.start : longest.end] == number


@given(st.text("0123456789 .-()+xet", max_size=60))
def test_every_phone_value_holds_9_to_15_digits_besides_its_extension(text: str) -> None:
    assert phone_value_faults(text) == []


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("card 4222222222222", "4222222222222"),
        ("card 4111 1111 1111 1111 003", "4111 1111 1111 1111 003"),
        ("card 4111 1111 1111 1111 12/27", VALID_CARD),
        ("card 4111 1111 1111 1111 123", VALID_CARD),
        ("card 4111-1111-1111-1111", "4111-1111-1111-1111"),
        ("card 5555 5555 5555 4444", "5555 5555 5555 4444"),
        ("amex 378282246310005", "378282246310005"),
    ],
    ids=["13-digits", "19-digits", "before-a-date", "before-digits", "hyphens", "spaces", "15"],
)
def test_card_pattern_finds_13_to_19_digits_that_pass_the_luhn_check(
    message: str, expected: str
) -> None:
    assert pattern_detections(message) == [(PseudonymType.CARD, expected)]


@pytest.mark.parametrize(
    "message",
    [
        "card 4111111111111112",
        "card 4111111111111",
        "card 411111111111",
        "card 41111111111111111111",
        "card x4111111111111111",
        "card 4111111111111111y",
    ],
    ids=["luhn", "13-invalid", "12-digits", "20-digits", "after-a-letter", "before-a-letter"],
)
def test_card_pattern_ignores_numbers_outside_the_format(message: str) -> None:
    assert PseudonymType.CARD not in detected_types(message)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("order ORD-20999", (PseudonymType.ORDER_ID, "ORD-20999")),
        ("(ORD-20901)", (PseudonymType.ORDER_ID, "ORD-20901")),
        ("tracking TRK-0000020902", (PseudonymType.TRACKING_ID, "TRK-0000020902")),
        ("payment TXN-00020901", (PseudonymType.TRANSACTION_ID, "TXN-00020901")),
        ("TXN-00020901.", (PseudonymType.TRANSACTION_ID, "TXN-00020901")),
    ],
)
def test_commerce_patterns_find_the_identifiers_of_the_seed(
    message: str, expected: tuple[PseudonymType, str]
) -> None:
    assert pattern_detections(message) == [expected]


@pytest.mark.parametrize(
    "message",
    ["ORD-2090", "TRK-123", "TXN-1234567", "XORD-20901", "ORD-209012"],
)
def test_commerce_patterns_ignore_other_formats(message: str) -> None:
    assert pattern_detections(message) == []


@pytest.mark.parametrize(
    ("number", "is_valid"),
    [
        ("4111111111111111", True),
        ("5555 5555 5555 4444", True),
        ("378282246310005", True),
        ("4111111111111112", False),
        ("1234567890123", False),
        ("", False),
    ],
)
def test_luhn_check_accepts_only_valid_card_numbers(number: str, *, is_valid: bool) -> None:
    assert is_luhn_valid(number) is is_valid


def named_entity(message: str, phrase: str) -> Detection:
    start = message.index(phrase)
    return Detection(start, start + len(phrase), PseudonymType.NAME, DetectionSource.NAMED_ENTITY)


def test_a_named_entity_on_a_product_name_is_dropped_whatever_its_case_and_diacritics() -> None:
    message = "My JORDAN RÚNNER shoes are torn."

    kept = drop_product_names(
        (named_entity(message, "JORDAN RÚNNER"),), message, ("Jordan Runner",)
    )

    assert kept == ()


def test_a_known_value_on_a_product_name_is_kept() -> None:
    message = "Ask Jordan Runner about it."
    known = KnownValueDetector().detect(message, (KnownValue(PseudonymType.NAME, "Jordan Runner"),))

    assert drop_product_names(known, message, ("Jordan Runner",)) == known


def test_a_named_entity_that_holds_a_product_name_inside_a_longer_word_is_kept() -> None:
    message = "Ask Lampson about it."
    detection = named_entity(message, "Lampson")

    assert drop_product_names((detection,), message, ("Lamp",)) == (detection,)


def rule_name(message: str, phrase: str) -> Detection:
    start = message.index(phrase)
    return Detection(start, start + len(phrase), PseudonymType.NAME, DetectionSource.RULE)


def test_a_rule_detection_on_a_product_name_is_dropped_whatever_its_case_and_diacritics() -> None:
    message = "My JORDAN RÚNNER shoes are torn."

    kept = drop_product_names((rule_name(message, "JORDAN RÚNNER"),), message, ("Jordan Runner",))

    assert kept == ()


def test_a_rule_detection_away_from_every_product_name_is_kept() -> None:
    message = "Nguyễn Văn An bought the Jordan Runner."
    detection = rule_name(message, "Nguyễn Văn An")

    assert drop_product_names((detection,), message, ("Jordan Runner",)) == (detection,)


def test_overlap_keeps_the_longer_span() -> None:
    message = "TRK-0000020902"

    detections = resolve_overlaps(PatternDetector().detect(message, ()))

    assert found(detections, message) == [(PseudonymType.TRACKING_ID, message)]


def test_overlap_prefers_a_known_value_over_a_pattern_of_equal_length() -> None:
    message = "Order ORD-20901"
    detections = (
        *PatternDetector().detect(message, ()),
        *KnownValueDetector().detect(message, (ORDER,)),
    )

    (kept,) = resolve_overlaps(detections)

    assert kept.source is DetectionSource.KNOWN_VALUE


def test_overlap_prefers_a_pattern_over_the_named_entity_detector() -> None:
    pattern = Detection(0, 9, PseudonymType.ORDER_ID, DetectionSource.PATTERN)
    named = Detection(0, 9, PseudonymType.NAME, DetectionSource.NAMED_ENTITY)

    kept = resolve_overlaps((named, pattern))

    assert kept == (pattern,)


def test_overlap_prefers_the_named_entity_detector_over_a_rule_of_equal_length() -> None:
    # A choice of the code, not of the design: the model reads the context, and a rule is the
    # fallback (detection.py, the comment on _SOURCE_PRECEDENCE). ADDRESS comes before NAME
    # among the types, so only the source can decide for the model.
    named = Detection(0, 12, PseudonymType.NAME, DetectionSource.NAMED_ENTITY)
    rule = Detection(0, 12, PseudonymType.ADDRESS, DetectionSource.RULE)

    kept = resolve_overlaps((rule, named))

    assert kept == (named,)


def test_overlap_lets_a_longer_rule_address_replace_the_names_inside_it() -> None:
    address = Detection(0, 30, PseudonymType.ADDRESS, DetectionSource.RULE)
    names = (
        Detection(3, 10, PseudonymType.NAME, DetectionSource.NAMED_ENTITY),
        Detection(12, 20, PseudonymType.NAME, DetectionSource.NAMED_ENTITY),
    )

    kept = resolve_overlaps((*names, address))

    assert kept == (address,)


def test_map_numbers_each_type_in_order_of_first_appearance() -> None:
    message = "Lan Tran and Minh Le wrote; Lan Tran again."
    detections = (
        Detection(0, 8, PseudonymType.NAME, DetectionSource.KNOWN_VALUE),
        Detection(13, 20, PseudonymType.NAME, DetectionSource.KNOWN_VALUE),
        Detection(28, 36, PseudonymType.NAME, DetectionSource.KNOWN_VALUE),
    )

    result = build_pseudonymized_message(message, detections)

    assert result.text == "[NAME_1] and [NAME_2] wrote; [NAME_1] again."
    assert result.entries == (
        PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Lan Tran"),
        PseudonymEntry("[NAME_2]", PseudonymType.NAME, "Minh Le"),
    )


def test_map_gives_two_spellings_of_one_value_one_pseudonym_and_keeps_the_first() -> None:
    message = "Bùi Thị An, also Bui Thi An"
    detections = KnownValueDetector().detect(message, (NAME,))

    result = build_pseudonymized_message(message, resolve_overlaps(detections))

    assert result.text == "[NAME_1], also [NAME_1]"
    assert result.entries == (PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Bùi Thị An"),)


def test_map_compares_phone_numbers_by_their_digits() -> None:
    message = "0901110001 or 090 111 0001"
    detections = resolve_overlaps(PatternDetector().detect(message, ()))

    result = build_pseudonymized_message(message, detections)

    assert result.text == "[PHONE_1] or [PHONE_1]"


def test_text_longer_than_the_limit_fails_closed() -> None:
    message = "a" * (PSEUDONYMIZED_TEXT_MAX_LENGTH + 1)

    with pytest.raises(PseudonymizedTextTooLongError):
        build_pseudonymized_message(message, ())


def test_text_exactly_at_the_limit_is_accepted() -> None:
    message = "a" * PSEUDONYMIZED_TEXT_MAX_LENGTH

    result = build_pseudonymized_message(message, ())

    assert len(result.text) == PSEUDONYMIZED_TEXT_MAX_LENGTH


def test_restore_replaces_pseudonyms_and_keeps_masks_and_unknown_pseudonyms() -> None:
    entries = (PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Lan Tran"),)

    restored = restore_pseudonyms("Hi [NAME_1], [EMAIL] and [ORDER_ID_4].", entries)

    assert restored.text == "Hi Lan Tran, [EMAIL] and [ORDER_ID_4]."
    assert restored.missing_pseudonym_count == 1


def test_restored_literal_is_the_customers_text_and_still_a_placeholder() -> None:
    entries = (PseudonymEntry("[LITERAL_1]", PseudonymType.LITERAL, "[NAME_1]"),)

    restored = restore_pseudonyms("You wrote [LITERAL_1].", entries)

    assert restored.text == "You wrote [NAME_1]."
    assert contains_placeholder(restored.text)


@given(st.text(max_size=300))
def test_pseudonymization_is_deterministic_and_restores_the_message(message: str) -> None:
    detectors = (
        LiteralPlaceholderDetector(),
        KnownValueDetector(),
        PatternDetector(),
        VietnameseNameDetector(),
        AddressRuleDetector(),
    )
    detections = resolve_overlaps(
        detection for detector in detectors for detection in detector.detect(message, KNOWN_VALUES)
    )

    first = build_pseudonymized_message(message, detections)
    second = build_pseudonymized_message(message, detections)

    assert first == second
    assert restore_pseudonyms(first.text, first.entries).text == message

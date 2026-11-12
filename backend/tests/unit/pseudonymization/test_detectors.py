"""Tests of the detectors, the overlap rule, the map, and restoration (ADR-0010).

Each detector has at least five positive and five negative examples, with the boundary
formats of ADR-0010 (ADR-0010, Detection). Every value is synthetic (TEST-18).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from supportiq_backend.pseudonymization.domain import (
    PSEUDONYMIZED_TEXT_MAX_LENGTH,
    Detection,
    DetectionSource,
    KnownValue,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    PseudonymEntry,
    PseudonymizedTextTooLongError,
    PseudonymType,
    build_pseudonymized_message,
    contains_placeholder,
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
    detectors = (LiteralPlaceholderDetector(), KnownValueDetector(), PatternDetector())
    detections = resolve_overlaps(
        detection for detector in detectors for detection in detector.detect(message, KNOWN_VALUES)
    )

    first = build_pseudonymized_message(message, detections)
    second = build_pseudonymized_message(message, detections)

    assert first == second
    assert restore_pseudonyms(first.text, first.entries).text == message

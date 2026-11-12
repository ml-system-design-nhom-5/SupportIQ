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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("write to lan.tran@example.test", (PseudonymType.EMAIL, "lan.tran@example.test")),
        ("a.b+c@sub.example.org", (PseudonymType.EMAIL, "a.b+c@sub.example.org")),
        ("call 0901110001", (PseudonymType.PHONE, "0901110001")),
        ("call +84 90 111 0002", (PseudonymType.PHONE, "+84 90 111 0002")),
        ("call 090.111.0003", (PseudonymType.PHONE, "090.111.0003")),
        ("card 4111-1111-1111-1111", (PseudonymType.CARD, "4111-1111-1111-1111")),
        ("tracking TRK-0000020902", (PseudonymType.TRACKING_ID, "TRK-0000020902")),
        ("payment TXN-00020901", (PseudonymType.TRANSACTION_ID, "TXN-00020901")),
        ("order ORD-20999", (PseudonymType.ORDER_ID, "ORD-20999")),
    ],
)
def test_pattern_detector_finds_values_with_their_format(
    message: str, expected: tuple[PseudonymType, str]
) -> None:
    detections = resolve_overlaps(PatternDetector().detect(message, ()))

    assert found(detections, message) == [expected]


@pytest.mark.parametrize(
    "message",
    [
        "my mail is lan at example",
        "user@localhost",
        "call 12345678",
        "card 4111 1111 1111 1112",
        "ORD-2090 and TRK-123 and TXN-1234567",
        "price 129.00 USD",
    ],
)
def test_pattern_detector_ignores_values_outside_the_formats(message: str) -> None:
    detections = resolve_overlaps(PatternDetector().detect(message, ()))

    assert found(detections, message) == []


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

"""Tests of the named-entity detector on the pinned model (ADR-0010, step 4; ADR-0017).

Each type has at least five positive and five negative examples (ADR-0010, Detection), and the
name rules of ADR-0029, statement 2, have a few cases on the model. The label filter of the
person-cue rule needs no model. Every value is synthetic (TEST-18).
"""

import pytest

from app.pseudonymization.adapters import named_entity_detector
from app.pseudonymization.adapters.named_entity_detector import (
    SpacyNamedEntityDetector,
    cue_spans,
)
from app.pseudonymization.domain import (
    DetectionSource,
    DetectorError,
    NamedEntityModelMissingError,
    PseudonymType,
    TextSpan,
)

# spaCy refuses a text longer than its default `max_length` of 1 000 000 characters.
TOO_LONG_FOR_THE_MODEL = "a" * 1_000_001


@pytest.fixture(scope="module")
def detector() -> SpacyNamedEntityDetector:
    return SpacyNamedEntityDetector()


def found(detector: SpacyNamedEntityDetector, message: str, kind: PseudonymType) -> list[str]:
    return [
        message[detection.start : detection.end]
        for detection in detector.detect(message, ())
        if detection.pseudonym_type is kind
    ]


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("Please ask Robert Johnson about the refund.", "Robert Johnson"),
        ("Thank you, Anna Kowalski.", "Anna Kowalski"),
        ("My son Peter Brown needs a new charger.", "Peter Brown"),
        ("Nguyen Thi Thu Ha ordered two mugs.", "Nguyen Thi Thu Ha"),
        ("Please call me, I am Hoang Van Tuan.", "Hoang Van Tuan"),
    ],
)
def test_a_person_is_a_name(detector: SpacyNamedEntityDetector, message: str, name: str) -> None:
    assert found(detector, message, PseudonymType.NAME) == [name]


@pytest.mark.parametrize(
    ("message", "address"),
    [
        ("Ship to 60 Sunset Boulevard, Los Angeles.", "60 Sunset Boulevard, Los Angeles"),
        ("Send the parcel to 4 Baker Street, London please.", "4 Baker Street, London"),
        ("Collect it at 12 Main Street, Springfield.", "12 Main Street, Springfield"),
        ("Elizabeth Taylor works at 9 Oak Avenue, Leeds.", "9 Oak Avenue, Leeds"),
        ("My office is at 100 Park Avenue in New York.", "100 Park Avenue"),
    ],
)
def test_a_facility_grows_to_its_house_number_and_the_place_after_it(
    detector: SpacyNamedEntityDetector, message: str, address: str
) -> None:
    assert found(detector, message, PseudonymType.ADDRESS) == [address]


@pytest.mark.parametrize(
    "message",
    [
        "Do you ship to Japan?",
        "The parcel is stuck in Singapore.",
        "Order 3 lamps and 2 mugs for March.",
        "Is the warehouse open on Sunday?",
        "Please refund the full amount today.",
    ],
)
def test_a_message_without_a_person_or_a_facility_has_no_name_or_address(
    detector: SpacyNamedEntityDetector, message: str
) -> None:
    assert detector.detect(message, ()) == ()


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("Regards, Vũ Thị Lan", "Vũ Thị Lan"),
        ("I am Dang Quoc Bao (b@example.test).", "Dang Quoc Bao"),
        ("Thanks, Quach Gia Han", "Quach Gia Han"),
    ],
    ids=["model-found-thi-lan", "model-found-quoc-bao", "model-found-quach-gia"],
)
def test_a_person_name_that_the_model_cut_short_grows(
    detector: SpacyNamedEntityDetector, message: str, name: str
) -> None:
    assert found(detector, message, PseudonymType.NAME) == [name]


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("Thanks Marcus Whitfield for the help.", "Marcus Whitfield"),
        ("Hi Thu Trang Đỗ, the parcel is late.", "Thu Trang Đỗ"),
        ("Please Lan Anh call back.", "Lan Anh"),
    ],
    ids=["thanks", "hi", "please"],
)
def test_a_stoplist_word_does_not_join_a_person_name(
    detector: SpacyNamedEntityDetector, message: str, name: str
) -> None:
    assert found(detector, message, PseudonymType.NAME) == [name]


def test_growth_joins_a_capitalized_word_that_starts_the_sentence(
    detector: SpacyNamedEntityDetector,
) -> None:
    # Over-detection, which the design accepts (Layer 1, names, items 1 and 6).
    message = "Ask Robert Johnson about the refund."

    assert found(detector, message, PseudonymType.NAME) == ["Ask Robert Johnson"]


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("I write on behalf of Marcus Whitfield (m@example.test).", "Marcus Whitfield"),
        ("On behalf of Florence Hart, I ask for a refund.", "Florence Hart"),
        ("Regards, Georgia Bell", "Georgia Bell"),
    ],
    ids=["on-behalf-of", "on-behalf-of-first", "regards"],
)
def test_an_organization_after_a_person_cue_is_a_name_of_the_rule(
    detector: SpacyNamedEntityDetector, message: str, name: str
) -> None:
    detections = detector.detect(message, ())

    assert found(detector, message, PseudonymType.NAME) == [name]
    assert {detection.source for detection in detections} == {DetectionSource.RULE}


@pytest.mark.parametrize(
    "message",
    ["I ordered from Acme Home Goods.", "The lamp from Hanoi Lighting broke."],
)
def test_an_organization_without_a_person_cue_is_no_name(
    detector: SpacyNamedEntityDetector, message: str
) -> None:
    assert detector.detect(message, ()) == ()


def test_a_name_or_address_of_the_model_comes_from_the_named_entity_step(
    detector: SpacyNamedEntityDetector,
) -> None:
    detections = detector.detect("Elizabeth Taylor works at 9 Oak Avenue, Leeds.", ())

    assert {detection.source for detection in detections} == {DetectionSource.NAMED_ENTITY}


@pytest.mark.parametrize("label", ["ORG", "GPE", "LOC"])
def test_an_organization_or_a_place_is_read_by_the_person_cue_rule(label: str) -> None:
    assert cue_spans([(label, 3, 9)]) == (TextSpan(3, 9),)


@pytest.mark.parametrize("label", ["PERSON", "FAC", "DATE", "NORP", "UNKNOWN"])
def test_another_label_is_not_read_by_the_person_cue_rule(label: str) -> None:
    assert cue_spans([(label, 3, 9)]) == ()


def test_a_missing_model_stops_the_detector_from_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    def load_nothing(name: str, *, exclude: tuple[str, ...]) -> None:
        del exclude
        raise OSError(name)

    monkeypatch.setattr(named_entity_detector.spacy, "load", load_nothing)

    with pytest.raises(NamedEntityModelMissingError):
        SpacyNamedEntityDetector()


def test_a_message_that_the_model_refuses_fails_closed(
    detector: SpacyNamedEntityDetector,
) -> None:
    with pytest.raises(DetectorError):
        detector.detect(TOO_LONG_FOR_THE_MODEL, ())

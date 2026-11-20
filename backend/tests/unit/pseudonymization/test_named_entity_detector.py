"""Tests of the named-entity detector on the pinned model (ADR-0010, step 4; ADR-0017).

Each type has at least five positive and five negative examples (ADR-0010, Detection). Every
value is synthetic (TEST-18).
"""

import pytest

from app.pseudonymization.adapters import named_entity_detector
from app.pseudonymization.adapters.named_entity_detector import (
    SpacyNamedEntityDetector,
)
from app.pseudonymization.domain import (
    DetectionSource,
    DetectorError,
    NamedEntityModelMissingError,
    PseudonymType,
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
        ("Ask Robert Johnson about the refund.", "Robert Johnson"),
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


def test_every_detection_comes_from_the_named_entity_step(
    detector: SpacyNamedEntityDetector,
) -> None:
    detections = detector.detect("Elizabeth Taylor works at 9 Oak Avenue, Leeds.", ())

    assert {detection.source for detection in detections} == {DetectionSource.NAMED_ENTITY}


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

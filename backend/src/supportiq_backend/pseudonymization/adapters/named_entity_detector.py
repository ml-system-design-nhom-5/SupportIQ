"""The named-entity detector of ADR-0010, step 4, on spaCy and `en_core_web_sm` (ADR-0017)."""

from collections.abc import Iterator

import spacy
from spacy.tokens import Doc, Span

from supportiq_backend.pseudonymization.domain import (
    Detection,
    DetectionSource,
    DetectorError,
    KnownValue,
    NamedEntityModelMissingError,
    PseudonymType,
)

MODEL_NAME = "en_core_web_sm"
# Only the entity recognizer runs: it has its own token vectors, and it finds the same entities
# without the other components of the pipeline.
_UNUSED_COMPONENTS = ("tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer")
_PLACE_LABELS = frozenset({"GPE", "LOC"})


class SpacyNamedEntityDetector:
    """Step 4: person names and postal addresses that the earlier steps did not find.

    Pseudonymization drops its detections on product names (`drop_product_names`).
    """

    def __init__(self) -> None:
        """Load the pinned model.

        Raises:
            NamedEntityModelMissingError: The model is not installed (ERR-17).
        """
        try:
            self._nlp = spacy.load(MODEL_NAME, exclude=_UNUSED_COMPONENTS)
        except OSError as error:
            raise NamedEntityModelMissingError from error

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find the names and addresses of the message.

        Args:
            message: The raw message.
            _known_values: Not used by this step.

        Returns:
            One detection per name or address.

        Raises:
            DetectorError: The model failed on the message.
        """
        try:
            doc = self._nlp(message)
        except Exception as error:
            # Any failure of the model fails closed (SEC-36).
            raise DetectorError from error
        return (
            *(
                _detection(entity, PseudonymType.NAME)
                for entity in doc.ents
                if entity.label_ == "PERSON"
            ),
            *(_detection(span, PseudonymType.ADDRESS) for span in _find_addresses(doc)),
        )


def _find_addresses(doc: Doc) -> Iterator[Span]:
    """Find postal addresses around the facilities (FAC) that the model labels.

    A facility, such as "Main Street", grows to the house number just before it and to the place
    names (GPE, LOC) right after it, with or without a comma: "12 Main Street, Springfield". A
    place name alone, such as "Vietnam" or "Hanoi", is no address.
    """
    places = {entity.start: entity for entity in doc.ents if entity.label_ in _PLACE_LABELS}
    for entity in doc.ents:
        if entity.label_ != "FAC":
            continue
        start = entity.start
        if start > 0 and doc[start - 1].like_num:
            start -= 1
        end = entity.end
        while (place := _place_after(doc, places, end)) is not None:
            end = place.end
        yield doc[start:end]


def _place_after(doc: Doc, places: dict[int, Span], end: int) -> Span | None:
    # A place name that starts at token `end`, or right after a comma there.
    if end < len(doc) and doc[end].text == ",":
        end += 1
    return places.get(end)


def _detection(span: Span, pseudonym_type: PseudonymType) -> Detection:
    return Detection(span.start_char, span.end_char, pseudonym_type, DetectionSource.NAMED_ENTITY)

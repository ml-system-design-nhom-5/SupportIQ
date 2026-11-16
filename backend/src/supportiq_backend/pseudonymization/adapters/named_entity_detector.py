"""The named-entity detector of ADR-0010, step 4, on spaCy and `en_core_web_sm` (ADR-0017)."""

from collections.abc import Iterable, Iterator

import spacy
from spacy.tokens import Doc, Span

from supportiq_backend.pseudonymization.domain import (
    Detection,
    DetectionSource,
    DetectorError,
    KnownValue,
    PseudonymType,
)
from supportiq_backend.pseudonymization.domain.detection import (
    find_whole_words,
    fold_text,
    fold_value,
)

MODEL_NAME = "en_core_web_sm"
# Only the entity recognizer runs: it has its own token vectors, and it finds the same entities
# without the other components of the pipeline.
_UNUSED_COMPONENTS = ("tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer")
_PLACE_LABELS = frozenset({"GPE", "LOC"})


class SpacyNamedEntityDetector:
    """Step 4: person names and postal addresses that the earlier steps did not find."""

    def __init__(self, product_names: Iterable[str]) -> None:
        """Load the pinned model, which fails when it is not installed (ERR-17).

        Args:
            product_names: The names of the catalog, which are never personal data.

        Raises:
            OSError: The model is not installed.
        """
        self._nlp = spacy.load(MODEL_NAME, exclude=_UNUSED_COMPONENTS)
        self._product_names = tuple(fold_value(name) for name in product_names)

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find the names and addresses of the message, outside the product names.

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
        found = (
            *(
                _detection(entity, PseudonymType.NAME)
                for entity in doc.ents
                if entity.label_ == "PERSON"
            ),
            *(_detection(span, PseudonymType.ADDRESS) for span in _find_addresses(doc)),
        )
        products = tuple(self._find_products(message))
        return tuple(
            detection
            for detection in found
            if not any(detection.start < end and start < detection.end for start, end in products)
        )

    def _find_products(self, message: str) -> Iterator[tuple[int, int]]:
        folded = fold_text(message)
        for name in self._product_names:
            for match in find_whole_words(name, folded.text):
                yield folded.to_original_span(match.start(), match.end())


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

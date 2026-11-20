"""Detections of personal data in a message, and the overlap rule (ADR-0010, Detection).

Every detector returns spans of the raw message. The overlap rule then keeps, for every
character, at most one detection: the longer span wins; for spans of equal length, a literal
placeholder wins over a known value, a known value over a pattern, and a pattern over the
named-entity detector (ADR-0010, step 5).
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.pseudonymization.domain.placeholders import PseudonymType

# Letters that Unicode does not decompose into a base letter and a mark, so that "Đặng"
# compares equal to "Dang" (ADR-0010, Detection, step 2).
_LETTER_FOLDS = str.maketrans({"đ": "d", "Đ": "D"})


class DetectionSource(StrEnum):
    """Which step of ADR-0010 found a span, in the order of precedence of the overlap rule."""

    LITERAL = "literal"
    KNOWN_VALUE = "known_value"
    PATTERN = "pattern"
    NAMED_ENTITY = "named_entity"


_SOURCE_PRECEDENCE = tuple(DetectionSource)
# Between two patterns of equal length, the more specific one wins: a commerce identifier over
# a card number, which passes the Luhn check, over an email, over a phone number. The rule
# only has to be deterministic (ADR-0010, item 5).
_TYPE_PRECEDENCE = (
    PseudonymType.LITERAL,
    PseudonymType.ORDER_ID,
    PseudonymType.TRACKING_ID,
    PseudonymType.TRANSACTION_ID,
    PseudonymType.CARD,
    PseudonymType.EMAIL,
    PseudonymType.PHONE,
    PseudonymType.ADDRESS,
    PseudonymType.NAME,
)


@dataclass(frozen=True, slots=True)
class Detection:
    """One span of the raw message that holds a personal value.

    It holds positions only, never the value, so it can be compared and logged safely.

    Attributes:
        start: The index of the first character.
        end: The index after the last character.
        pseudonym_type: The type of the value.
        source: The step that found it.
    """

    start: int
    end: int
    pseudonym_type: PseudonymType
    source: DetectionSource

    @property
    def length(self) -> int:
        """Return the number of characters of the span."""
        return self.end - self.start

    def overlaps(self, other: Detection) -> bool:
        """Tell whether two spans share at least one character.

        Args:
            other: The other detection.

        Returns:
            True when the spans overlap.
        """
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True, repr=False)
class KnownValue:
    """A personal value that backend holds for the ticket. Confidential.

    Attributes:
        pseudonym_type: The type of the value.
        text: The value as stored.
    """

    pseudonym_type: PseudonymType
    text: str


class Detector(Protocol):
    """One detection step of ADR-0010. The named-entity detector implements it too.

    A detector that cannot run raises `DetectorError`, which fails pseudonymization closed
    (SEC-36). Finding nothing is no failure.
    """

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find the spans of personal data in a message.

        Args:
            message: The raw message. Confidential.
            known_values: The values that backend holds for the ticket.

        Returns:
            Every span found, in any order; spans may overlap.

        Raises:
            DetectorError: The detector could not run.
        """
        ...


@dataclass(frozen=True, slots=True)
class FoldedText:
    """A text in lowercase without diacritics, with the origin of every character.

    Attributes:
        text: The folded text.
        origins: For each character of `text`, the index of the character it came from.
    """

    text: str
    origins: tuple[int, ...]

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a span of the folded text back to the original text.

        Args:
            start: The first index in the folded text.
            end: The index after the last one, greater than `start`.

        Returns:
            The span in the original text.
        """
        return self.origins[start], self.origins[end - 1] + 1


def fold_text(text: str) -> FoldedText:
    """Fold a text for comparisons that ignore case and diacritics.

    Args:
        text: The text.

    Returns:
        The folded text with the origin of each of its characters.
    """
    characters: list[str] = []
    origins: list[int] = []
    for index, character in enumerate(text):
        for folded in fold_value(character):
            characters.append(folded)
            origins.append(index)
    return FoldedText("".join(characters), tuple(origins))


def fold_value(text: str) -> str:
    """Return a text in lowercase without diacritics, so "Bùi Thị An" equals "bui thi an".

    Args:
        text: The text.

    Returns:
        The folded text.
    """
    decomposed = unicodedata.normalize("NFD", text.translate(_LETTER_FOLDS))
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).lower()


def find_whole_words(pattern: str, text: str) -> Iterator[re.Match[str]]:
    """Find the matches of a literal pattern that are not part of a longer word.

    Args:
        pattern: The literal text to find.
        text: The text to search.

    Returns:
        The matches, from left to right.
    """
    return re.finditer(rf"(?<!\w){re.escape(pattern)}(?!\w)", text)


def drop_product_names(
    detections: Iterable[Detection], message: str, product_names: Iterable[str]
) -> tuple[Detection, ...]:
    """Drop the named-entity detections that overlap a product name of the catalog.

    Product names are no personal data, so "Apple Watch" stays as written; the detections of
    the earlier steps are all kept (ADR-0010, Detection, step 4).

    Args:
        detections: Every detection of every detector.
        message: The raw message.
        product_names: The names of the catalog, compared without case and diacritics.

    Returns:
        The detections without those of the named-entity step on a product name.
    """
    folded = fold_text(message)
    products = [
        folded.to_original_span(match.start(), match.end())
        for name in product_names
        if name
        for match in find_whole_words(fold_value(name), folded.text)
    ]
    return tuple(
        detection
        for detection in detections
        if detection.source is not DetectionSource.NAMED_ENTITY
        or not any(detection.start < end and start < detection.end for start, end in products)
    )


def resolve_overlaps(detections: Iterable[Detection]) -> tuple[Detection, ...]:
    """Keep at most one detection for every character (ADR-0010, Detection, step 5).

    Args:
        detections: Every detection of every detector.

    Returns:
        The detections that win, ordered by position.
    """
    kept: list[Detection] = []
    for detection in sorted(detections, key=_precedence):
        if not any(detection.overlaps(other) for other in kept):
            kept.append(detection)
    return tuple(sorted(kept, key=lambda detection: detection.start))


def _precedence(detection: Detection) -> tuple[int, int, int, int]:
    return (
        -detection.length,
        _SOURCE_PRECEDENCE.index(detection.source),
        _TYPE_PRECEDENCE.index(detection.pseudonym_type),
        detection.start,
    )

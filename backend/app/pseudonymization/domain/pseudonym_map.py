"""Pseudonyms for detected values, the pseudonymized text, and restoration (ADR-0010).

Pseudonymization is deterministic: the same message, the same known values, and the same
detectors give the same text and the same map (ADR-0010, item 5).
"""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.pseudonymization.domain.detection import Detection, fold_value
from app.pseudonymization.domain.errors import (
    PseudonymizedTextTooLongError,
    PseudonymLimitExceededError,
)
from app.pseudonymization.domain.placeholders import (
    PLACEHOLDER_PATTERN,
    PSEUDONYM_NUMBER_MAXIMUM,
    PseudonymType,
    format_pseudonym,
)

# The `maxLength` of `PseudonymizedText` in the ai-service contract, in code points.
PSEUDONYMIZED_TEXT_MAX_LENGTH = 4_000


def _digits_only(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _exact(value: str) -> str:
    return value


# How two spellings are compared, so the same value always gets the same pseudonym
# (ADR-0010, item 4).
_NORMALIZERS: Mapping[PseudonymType, Callable[[str], str]] = MappingProxyType(
    {
        PseudonymType.NAME: fold_value,
        PseudonymType.ADDRESS: fold_value,
        PseudonymType.EMAIL: str.lower,
        PseudonymType.PHONE: _digits_only,
        PseudonymType.CARD: _digits_only,
        PseudonymType.ORDER_ID: _exact,
        PseudonymType.TRACKING_ID: _exact,
        PseudonymType.TRANSACTION_ID: _exact,
        PseudonymType.LITERAL: _exact,
    }
)


@dataclass(frozen=True, slots=True, repr=False)
class PseudonymEntry:
    """One row of a ticket's pseudonym map. The original value is Confidential.

    Attributes:
        pseudonym: The pseudonym, such as `[NAME_1]`.
        pseudonym_type: Its type.
        original_value: The spelling that appears first in the message.
    """

    pseudonym: str
    pseudonym_type: PseudonymType
    original_value: str


@dataclass(frozen=True, slots=True, repr=False)
class PseudonymizedMessage:
    """A message with every detected value replaced, and the map that restores it.

    Attributes:
        text: The pseudonymized text. Confidential: it holds the customer's own words.
        entries: The map, in the order of first appearance.
    """

    text: str
    entries: tuple[PseudonymEntry, ...]

    def count_by_type(self) -> Mapping[PseudonymType, int]:
        """Count the pseudonyms of each type, for the audit log (ADR-0010, item 5).

        Returns:
            The number of distinct pseudonyms of each type, 0 for absent types.
        """
        counts = Counter(entry.pseudonym_type for entry in self.entries)
        return {pseudonym_type: counts[pseudonym_type] for pseudonym_type in PseudonymType}


@dataclass(frozen=True, slots=True, repr=False)
class RestoredText:
    """A text with every pseudonym of the map replaced by its original value.

    Attributes:
        text: The restored text. Masks and unknown pseudonyms stay as written.
        missing_pseudonym_count: Pseudonyms that the map does not hold, which is a defect.
    """

    text: str
    missing_pseudonym_count: int


def build_pseudonymized_message(
    message: str, detections: tuple[Detection, ...]
) -> PseudonymizedMessage:
    """Replace each detected value with its pseudonym.

    Args:
        message: The raw message.
        detections: The detections that won the overlap rule, ordered by position.

    Returns:
        The pseudonymized text and its map.

    Raises:
        PseudonymLimitExceededError: A type would need more than 999 pseudonyms.
        PseudonymizedTextTooLongError: The text is longer than `PseudonymizedText` allows.
    """
    pseudonym_by_value: dict[tuple[PseudonymType, str], str] = {}
    entries: list[PseudonymEntry] = []
    parts: list[str] = []
    position = 0
    for detection in detections:
        value = message[detection.start : detection.end]
        key = (detection.pseudonym_type, _NORMALIZERS[detection.pseudonym_type](value))
        if key not in pseudonym_by_value:
            entry = _new_entry(detection.pseudonym_type, value, entries)
            pseudonym_by_value[key] = entry.pseudonym
            entries.append(entry)
        parts.extend((message[position : detection.start], pseudonym_by_value[key]))
        position = detection.end
    parts.append(message[position:])
    text = "".join(parts)
    if len(text) > PSEUDONYMIZED_TEXT_MAX_LENGTH:
        raise PseudonymizedTextTooLongError
    return PseudonymizedMessage(text, tuple(entries))


def restore_pseudonyms(text: str, entries: tuple[PseudonymEntry, ...]) -> RestoredText:
    """Replace each pseudonym of a ticket's map by its original value (ADR-0010, Restoring).

    Args:
        text: AI text with placeholders, as stored.
        entries: The ticket's map.

    Returns:
        The restored text. A mask, or a pseudonym missing from the map, stays visible.
    """
    original_by_pseudonym = {entry.pseudonym: entry.original_value for entry in entries}
    missing_count = 0
    parts: list[str] = []
    position = 0
    for match in PLACEHOLDER_PATTERN.finditer(text):
        placeholder = match.group(0)
        is_pseudonym = match.group(2) is not None
        replacement = original_by_pseudonym.get(placeholder, placeholder)
        if is_pseudonym and placeholder not in original_by_pseudonym:
            missing_count += 1
        parts.extend((text[position : match.start()], replacement))
        position = match.end()
    parts.append(text[position:])
    return RestoredText("".join(parts), missing_count)


def _new_entry(
    pseudonym_type: PseudonymType, value: str, entries: list[PseudonymEntry]
) -> PseudonymEntry:
    number = 1 + sum(1 for entry in entries if entry.pseudonym_type is pseudonym_type)
    if number > PSEUDONYM_NUMBER_MAXIMUM:
        raise PseudonymLimitExceededError
    return PseudonymEntry(format_pseudonym(pseudonym_type, number), pseudonym_type, value)

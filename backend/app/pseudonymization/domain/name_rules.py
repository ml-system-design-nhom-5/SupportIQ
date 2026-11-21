"""The name rules of step 4 (ADR-0029, statement 2; leak fixes design, Layer 1, names).

The named-entity model finds most person names. These rules widen a name that it cut short, find
a Vietnamese name by its family name, and find a name that the model labeled as something else.
Every list is a constant of this module, so a change of a list is a change of the detector
version (ADR-0010, Placeholder syntax, item 5).

Each rule reads words as the module `words` defines them, so it never takes a word that is part
of a code, such as "ORD" in "ORD-12345", and its spans index the message as it came (design,
Layer 1, names, opening paragraphs).
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

from app.pseudonymization.domain.detection import Detection, DetectionSource, KnownValue
from app.pseudonymization.domain.placeholders import PseudonymType
from app.pseudonymization.domain.words import (
    NOTHING_JOINED_AFTER,
    NOTHING_JOINED_BEFORE,
    WORD_PATTERN,
    nfc,
    word_key,
)

# A title alone is no personal data (design, Layer 1, names, item 1).
TITLES = frozenset({"Mr", "Mrs", "Ms", "Miss", "Dr", "Ông", "Bà", "Chị", "Cô", "Chú"})
# The nine words that never join a name and never belong to a window of the Vietnamese name rule
# (design, Layer 1, names, items 1 and 2).
NAME_STOP_WORDS = frozenset(
    {"I", "Thanks", "Thank", "Regards", "Best", "Dear", "Hi", "Hello", "Please"}
)
# The words that span growth never adds and that the pre-send check accepts beside a name
# (design, Layer 1, names, item 1; Layer 2, finding 4).
NAME_NEIGHBOUR_STOPLIST = TITLES | NAME_STOP_WORDS
NAME_WORD_COUNTS = range(2, 5)
# The cues right before a name that the model labeled an organization or a place (design,
# Layer 1, names, item 3).
RELATIVE_WORDS = (
    "mother",
    "father",
    "mom",
    "dad",
    "sister",
    "brother",
    "wife",
    "husband",
    "son",
    "daughter",
    "aunt",
    "uncle",
    "cousin",
    "grandmother",
    "grandfather",
    "neighbour",
    "neighbor",
)
# The common family names of Wikipedia, "Vietnamese name", revision 1382972547 of 2026-10-31,
# read on 2026-11-20: https://en.wikipedia.org/w/index.php?title=Vietnamese_name&oldid=1382972547
VIETNAMESE_FAMILY_NAMES = frozenset(
    {
        "Nguyễn",
        "Trần",
        "Lê",
        "Phạm",
        "Hoàng",
        "Huỳnh",
        "Vũ",
        "Võ",
        "Phan",
        "Trương",
        "Bùi",
        "Đỗ",
        "Đặng",
        "Ngô",
        "Hồ",
        "Dương",
        "Lý",
    }
)
# The same names without diacritics, except "Do", "Ho", and "Le", which are also common words
# (design, Layer 1, names, item 2).
VIETNAMESE_FAMILY_NAMES_UNACCENTED = frozenset(
    {
        "Nguyen",
        "Tran",
        "Pham",
        "Hoang",
        "Huynh",
        "Vu",
        "Vo",
        "Phan",
        "Truong",
        "Bui",
        "Dang",
        "Ngo",
        "Duong",
        "Ly",
    }
)
# Without diacritics, these are family names only right before a middle name.
AMBIGUOUS_UNACCENTED_FAMILY_NAMES = frozenset({"Do", "Ho", "Le"})
# The usual padding names of the same source, Thị for women and Văn for men, in its section
# "Padding name (middle name)", read on 2026-11-21, with their unaccented spellings.
VIETNAMESE_MIDDLE_NAMES = frozenset({"Văn", "Thị", "Van", "Thi"})

_PERSON_CUE = re.compile(
    rf"(?:\b(?:my name is|I am|this is|on behalf of|my (?:{'|'.join(RELATIVE_WORDS)}))"
    r"|\b(?:Regards|Thanks),) \Z",
    re.IGNORECASE,
)
_WORD = re.compile(NOTHING_JOINED_BEFORE + WORD_PATTERN + NOTHING_JOINED_AFTER)
_WORD_BEFORE = re.compile(NOTHING_JOINED_BEFORE + WORD_PATTERN + r" \Z")
_WORD_AFTER = re.compile(f" ({WORD_PATTERN}){NOTHING_JOINED_AFTER}")
_FAMILY_NAME_KEYS = frozenset(
    map(word_key, VIETNAMESE_FAMILY_NAMES | VIETNAMESE_FAMILY_NAMES_UNACCENTED)
)
_AMBIGUOUS_FAMILY_NAME_KEYS = frozenset(map(word_key, AMBIGUOUS_UNACCENTED_FAMILY_NAMES))
_MIDDLE_NAME_KEYS = frozenset(map(word_key, VIETNAMESE_MIDDLE_NAMES))


@dataclass(frozen=True, slots=True)
class TextSpan:
    """A span of a message, from its first character to the one after its last.

    Attributes:
        start: The index of the first character.
        end: The index after the last character.
    """

    start: int
    end: int


class VietnameseNameDetector:
    """Step 4: Vietnamese names found by their family name (design, Layer 1, names, item 2)."""

    def detect(
        self, message: str, _known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find the longest window of each run of capitalized words that is a name.

        A window has 2 to 4 words, one space apart, and its first or last word is a family name.
        The nine stop words never belong to a window, and a title, with or without a period, may
        only start one; the name leaves the title out, so "Mr. Tran" becomes "Mr. [NAME_1]".

        Args:
            message: The raw message.
            _known_values: Not used by this rule.

        Returns:
            At most one `NAME` of the rule source per run of capitalized words.
        """
        return tuple(
            name for run in _capitalized_runs(message) if (name := _longest_name(run)) is not None
        )


def grow_person_span(message: str, start: int, end: int) -> TextSpan:
    """Grow a person name of the model over the capitalized words right next to it.

    The name grows one word at a time, first to the left, over each capitalized word one space
    away, up to 4 words in total. A title or a word of the stoplist never joins it, so "Thanks
    Lan" stays "Thanks [NAME_1]", and nor does a word of a code, so "Robert Johnson ORD-12345"
    keeps its order ID (design, Layer 1, names, item 1).

    Args:
        message: The raw message.
        start: The first index of the name that the model found.
        end: The index after its last character.

    Returns:
        The grown span; the same span when no word may join it.
    """
    words = len(_WORD.findall(message, start, end))
    while words < max(NAME_WORD_COUNTS):
        before = _WORD_BEFORE.search(message, 0, start)
        after = _WORD_AFTER.match(message, end)
        if before is not None and _may_join(before.group().rstrip()):
            start = before.start()
        elif after is not None and _may_join(after.group(1)):
            end = after.end()
        else:
            break
        words += 1
    return TextSpan(start, end)


def person_cue_names(message: str, spans: tuple[TextSpan, ...]) -> tuple[Detection, ...]:
    """Find the names that the model labeled an organization or a place, after a person cue.

    Args:
        message: The raw message.
        spans: The spans that the model labeled `ORG`, `GPE`, or `LOC`.

    Returns:
        One `NAME` of the rule source for each span of 2 to 4 capitalized words that a cue
        such as "my name is" or "on behalf of" comes right before (design, Layer 1, names,
        item 3).
    """
    return tuple(
        Detection(span.start, span.end, PseudonymType.NAME, DetectionSource.RULE)
        for span in spans
        if _is_capitalized_name(message[span.start : span.end])
        and _PERSON_CUE.search(message, 0, span.start) is not None
    )


def _may_join(word: str) -> bool:
    return word[0].isupper() and nfc(word) not in NAME_NEIGHBOUR_STOPLIST


def _is_capitalized_name(text: str) -> bool:
    words = _WORD.findall(text)
    return len(words) in NAME_WORD_COUNTS and all(word[0].isupper() for word in words)


def _capitalized_runs(message: str) -> Iterator[list[re.Match[str]]]:
    # Runs of capitalized words one space apart. A stop word or a word in lowercase ends a run,
    # and a title starts a new one, so that a title can only be the first word of a window.
    run: list[re.Match[str]] = []
    for word in _WORD.finditer(message):
        text = nfc(word.group())
        if not text[0].isupper() or text in NAME_STOP_WORDS:
            yield run
            run = []
        elif run and text not in TITLES and _joins(message, run[-1], word):
            run.append(word)
        else:
            yield run
            run = [word]
    yield run


def _joins(message: str, previous: re.Match[str], word: re.Match[str]) -> bool:
    # One space joins two words of a run; a title may also end with a period, as in "Mr. Tran".
    gap = message[previous.end() : word.start()]
    return gap == " " or (gap == ". " and nfc(previous.group()) in TITLES)


def _longest_name(run: list[re.Match[str]]) -> Detection | None:
    keys = tuple(word_key(word.group()) for word in run)
    is_family = tuple(_is_family_name(keys, index) for index in range(len(keys)))
    windows = [
        (first, first + size)
        for size in NAME_WORD_COUNTS
        for first in range(len(run) - size + 1)
        if is_family[first] or is_family[first + size - 1]
    ]
    if not windows:
        return None
    # The longest window wins, then the one that starts with a family name, then the left one.
    first, stop = max(
        windows, key=lambda window: (window[1] - window[0], is_family[window[0]], -window[0])
    )
    if nfc(run[first].group()) in TITLES:
        first += 1
    return Detection(
        run[first].start(), run[stop - 1].end(), PseudonymType.NAME, DetectionSource.RULE
    )


def _is_family_name(keys: tuple[str, ...], index: int) -> bool:
    if keys[index] in _FAMILY_NAME_KEYS:
        return True
    is_before_a_middle_name = index + 1 < len(keys) and keys[index + 1] in _MIDDLE_NAME_KEYS
    return keys[index] in _AMBIGUOUS_FAMILY_NAME_KEYS and is_before_a_middle_name

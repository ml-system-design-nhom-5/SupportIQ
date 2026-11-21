"""Tests of the name rules of step 4 (ADR-0029, statement 2; leak fixes design, Layer 1, names).

Each rule has at least five positive and five negative examples (ADR-0029, statement 8), each
known limit of the design has a test that states it, and the invariants of the design are
property-based tests (TEST-13). Every value is synthetic (TEST-18).
"""

import re
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.pseudonymization.domain import (
    AMBIGUOUS_UNACCENTED_FAMILY_NAMES,
    NAME_NEIGHBOUR_STOPLIST,
    NAME_STOP_WORDS,
    NAME_WORD_COUNTS,
    TITLES,
    VIETNAMESE_FAMILY_NAMES,
    VIETNAMESE_FAMILY_NAMES_UNACCENTED,
    VIETNAMESE_MIDDLE_NAMES,
    Detection,
    DetectionSource,
    PseudonymType,
    TextSpan,
    VietnameseNameDetector,
    grow_person_span,
    person_cue_names,
)
from app.pseudonymization.domain.detection import fold_value

# A word of the design: a letter, then letters and the combining marks U+0300 to U+036F (Layer 1,
# names, opening), written with `chr` so that the source holds no lone combining character.
WORD = re.compile(rf"[^\W\d_](?:[^\W\d_]|[{chr(0x0300)}-{chr(0x036F)}])*")
# A capitalized word that ends a sentence still joins a name beside it.
SENTENCE_PUNCTUATION = ".,!?;:"
LIST_WORDS = sorted(
    TITLES
    | NAME_STOP_WORDS
    | VIETNAMESE_FAMILY_NAMES
    | VIETNAMESE_FAMILY_NAMES_UNACCENTED
    | AMBIGUOUS_UNACCENTED_FAMILY_NAMES
    | VIETNAMESE_MIDDLE_NAMES
)


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def nfd(text: str) -> str:
    return unicodedata.normalize("NFD", text)


def grown(message: str, name: str) -> str:
    start = message.index(name)
    span = grow_person_span(message, start, start + len(name))
    return message[span.start : span.end]


@pytest.mark.parametrize(
    ("message", "name", "expected"),
    [
        ("Regards, Vũ Thị Lan", "Thị Lan", "Vũ Thị Lan"),
        ("ask Trần Thị Lan now", "Lan", "Trần Thị Lan"),
        ("Kathryn Reynolds called", "Kathryn", "Kathryn Reynolds"),
        ("ask Nguyễn Văn An Bình now", "Văn", "Nguyễn Văn An Bình"),
        ("Ana Bea Cia Dea Eva", "Cia", "Ana Bea Cia Dea"),
        ("from Đặng Thu Hà today", "Thu Hà", "Đặng Thu Hà"),
        (nfd("Regards, Vũ Thị Lan"), nfd("Thị Lan"), nfd("Vũ Thị Lan")),
        ("ask Robert Johnson Smith.", "Robert Johnson", "Robert Johnson Smith"),
        ("ask Robert Johnson Smith, please", "Robert Johnson", "Robert Johnson Smith"),
    ],
    ids=[
        "left",
        "left-twice",
        "right",
        "both-sides",
        "stops-at-4-words",
        "diacritics",
        "decomposed-diacritics",
        "before-a-full-stop",
        "before-a-comma",
    ],
)
def test_a_person_name_grows_over_the_capitalized_words_next_to_it(
    message: str, name: str, expected: str
) -> None:
    assert grown(message, name) == expected


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("Bà Hương Nguyễn", "Hương Nguyễn"),
        ("Thanks Lan", "Lan"),
        ("see Lan today", "Lan"),
        ("Vũ, Lan", "Lan"),
        ("Room 12 Lan", "Lan"),
        ("Xa Ana Bea Cia Dea", "Ana Bea Cia Dea"),
        ("Vũ  Lan", "Lan"),
        ("Vũ\nLan", "Lan"),
        (nfd("Bà Hương"), nfd("Hương")),
        ("Robert Johnson ORD-12345", "Robert Johnson"),
        ("ORD-ABC Robert Johnson", "Robert Johnson"),
        ("Anh.Vu Lan Anh", "Lan Anh"),
        ("Lan Anh Vu@example", "Lan Anh"),
    ],
    ids=[
        "title",
        "stoplist-word",
        "lowercase-words",
        "comma",
        "digits",
        "already-4-words",
        "two-spaces",
        "line-break",
        "decomposed-title",
        "order-id-after",
        "code-before",
        "dotted-code-before",
        "at-sign-after",
    ],
)
def test_a_person_name_does_not_grow_over_other_neighbours(message: str, name: str) -> None:
    assert grown(message, name) == name


def cue_detections(message: str, name: str) -> tuple[Detection, ...]:
    start = message.index(name)
    return person_cue_names(message, (TextSpan(start, start + len(name)),))


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("I write on behalf of Kathryn Reynolds (k@example.test).", "Kathryn Reynolds"),
        ("Hi, my name is Lan Anh.", "Lan Anh"),
        ("Regards, Kathryn Reynolds", "Kathryn Reynolds"),
        ("Thanks, Minh Tuan Le", "Minh Tuan Le"),
        ("A box went to my neighbour Hoang Lan.", "Hoang Lan"),
        ("I am Lan Anh, the buyer.", "Lan Anh"),
        ("This is Lan Anh speaking.", "Lan Anh"),
        (nfd("my name is Vũ Lan"), nfd("Vũ Lan")),
    ],
    ids=[
        "on-behalf-of",
        "my-name-is",
        "regards",
        "thanks",
        "my-neighbour",
        "i-am",
        "this-is",
        "decomposed-diacritics",
    ],
)
def test_capitalized_words_after_a_person_cue_are_a_name(message: str, name: str) -> None:
    (detection,) = cue_detections(message, name)

    assert message[detection.start : detection.end] == name
    assert detection.pseudonym_type is PseudonymType.NAME
    assert detection.source is DetectionSource.RULE


@pytest.mark.parametrize(
    ("message", "name"),
    [
        ("Please call Kathryn Reynolds.", "Kathryn Reynolds"),
        ("my name is really Lan Anh", "Lan Anh"),
        ("my name is Lan", "Lan"),
        ("my name is Ana Bea Cia Dea Eva", "Ana Bea Cia Dea Eva"),
        ("my name is lan anh", "lan anh"),
        ("my friend Lan Anh", "Lan Anh"),
    ],
    ids=["no-cue", "word-between", "one-word", "five-words", "lowercase", "friend-is-no-cue"],
)
def test_other_words_after_a_cue_or_without_one_are_no_name(message: str, name: str) -> None:
    assert cue_detections(message, name) == ()


def test_a_message_in_vietnamese_gets_no_person_cue() -> None:
    # A known limit of the design (Layer 1, names, item 6): the person cues are English.
    assert cue_detections("Tôi là Lan Anh.", "Lan Anh") == ()


def vietnamese_names(message: str) -> list[str]:
    return [
        message[detection.start : detection.end]
        for detection in VietnameseNameDetector().detect(message, ())
    ]


@pytest.mark.parametrize(
    ("message", "names"),
    [
        ("it came from Hương Nguyễn today", ["Hương Nguyễn"]),
        ("ask Phương Hữu Bùi", ["Phương Hữu Bùi"]),
        ("ask Anh Anh Lê", ["Anh Anh Lê"]),
        ("from Trần Thị Bích Ngọc", ["Trần Thị Bích Ngọc"]),
        ("ask Nguyễn Văn An Bình Minh", ["Nguyễn Văn An Bình"]),
        ("Hi Nguyễn Văn An, the lamp broke.", ["Nguyễn Văn An"]),
        ("Dear Pham Minh,", ["Pham Minh"]),
        ("Bà Hương Nguyễn called", ["Hương Nguyễn"]),
        ("a call from Mr Tran", ["Tran"]),
        ("Dear Mr Tran", ["Tran"]),
        ("Mr. Tran called", ["Tran"]),
        ("Dear Mrs. Nguyen, thanks", ["Nguyen"]),
        ("Dr. Pham Minh wrote", ["Pham Minh"]),
        ("NGUYEN VAN AN paid twice", ["NGUYEN VAN AN"]),
        (nfd("from Vũ Thị Lan"), [nfd("Vũ Thị Lan")]),
        ("call Pham Lan Tran", ["Pham Lan Tran"]),
        ("from Bui Tran Lan Minh Thu", ["Bui Tran Lan Minh"]),
        ("from Nguyen Van An", ["Nguyen Van An"]),
        ("from Huong Tran", ["Huong Tran"]),
        ("from Vo Minh Tam", ["Vo Minh Tam"]),
        ("from Le Van An", ["Le Van An"]),
        ("from Do Thi Mai", ["Do Thi Mai"]),
        ("from Ho Van Nam", ["Ho Van Nam"]),
    ],
    ids=[
        "family-name-last",
        "three-words",
        "repeated-given-name",
        "four-words",
        "longest-window-of-a-long-run",
        "after-a-stop-word",
        "after-dear",
        "after-a-title",
        "title-and-one-word",
        "stop-word-and-title",
        "title-with-a-period",
        "stop-word-and-title-with-a-period",
        "title-with-a-period-and-two-words",
        "capitals",
        "decomposed-diacritics",
        "longer-window-beats-equal-ones",
        "left-window-beats-an-equal-one",
        "unaccented",
        "unaccented-last",
        "unaccented-vo",
        "le-before-a-middle-name",
        "do-before-a-middle-name",
        "ho-before-a-middle-name",
    ],
)
def test_capitalized_words_around_a_family_name_are_a_name(message: str, names: list[str]) -> None:
    assert vietnamese_names(message) == names


@pytest.mark.parametrize(
    "message",
    [
        "ask Nguyễn today",
        "ship it to 12 Main Street",
        "from nguyễn văn an",
        "Bà called twice",
        "Do You Ship to Japan?",
        "Le Monde wrote about it",
        "Ho Ho Ho",
        "the bus to Ho Chi Minh",
        "a trip to Hà Nội",
        "ref Tran-01 Minh",
        "Thanks Pham",
    ],
    ids=[
        "family-name-alone",
        "no-family-name",
        "lowercase",
        "title-alone",
        "do-before-a-word",
        "le-before-a-word",
        "ho-before-ho",
        "ho-before-chi",
        "ha-is-no-family-name",
        "family-name-in-a-code",
        "stop-word-and-one-word",
    ],
)
def test_other_capitalized_words_are_no_vietnamese_name(message: str) -> None:
    assert vietnamese_names(message) == []


@pytest.mark.parametrize(
    "place", ["Hồ Chí Minh", "Phan Thiết", "Hoàng Mai", "Phan Thiet", "Lê Lợi", "Nguyễn Huệ"]
)
def test_a_place_that_starts_or_ends_with_a_family_name_is_taken_for_a_name(place: str) -> None:
    # Over-detection, which the design accepts (Layer 1, names, item 6).
    assert vietnamese_names(f"a parcel to {place} today") == [place]


@pytest.mark.parametrize("name", ["Do Minh", "Le Thu Ha"])
def test_le_do_or_ho_without_diacritics_and_a_middle_name_is_not_found(name: str) -> None:
    # A known limit of the design (Layer 1, names, item 6).
    assert vietnamese_names(f"from {name} today") == []


def test_a_family_name_off_the_list_is_not_found() -> None:
    # A known limit of the design (Layer 1, names, item 6): the list never grows to fit a test.
    assert vietnamese_names("from Lâm Thu Hà today") == []


def test_a_given_name_before_a_window_of_two_words_stays_outside_it() -> None:
    # A known limit of the design (Layer 1, names, item 6); the pre-send check stops "Lan".
    assert vietnamese_names("call Lan Pham Minh") == ["Pham Minh"]


@pytest.mark.parametrize(
    ("message", "names"),
    [("TP.Hồ Chí Minh", []), ("12 Lê Lợi, Q.1, TP.HCM", ["Lê Lợi"])],
    ids=["city-after-tp", "address-with-abbreviations"],
)
def test_the_name_rules_read_the_address_abbreviations_as_codes(
    message: str, names: list[str]
) -> None:
    # Only the address rule reads "Q.", "P.", and "TP." (design, Layer 1, addresses).
    assert vietnamese_names(message) == names


def test_every_vietnamese_name_comes_from_the_rule_source() -> None:
    (detection,) = VietnameseNameDetector().detect("from Hương Nguyễn", ())

    assert detection.pseudonym_type is PseudonymType.NAME
    assert detection.source is DetectionSource.RULE


def test_the_unaccented_lists_are_the_family_names_without_diacritics() -> None:
    unaccented = VIETNAMESE_FAMILY_NAMES_UNACCENTED | AMBIGUOUS_UNACCENTED_FAMILY_NAMES

    assert set(map(fold_value, VIETNAMESE_FAMILY_NAMES)) == set(map(fold_value, unaccented))
    assert len(unaccented) == len(VIETNAMESE_FAMILY_NAMES)
    assert VIETNAMESE_FAMILY_NAMES_UNACCENTED.isdisjoint(AMBIGUOUS_UNACCENTED_FAMILY_NAMES)


@pytest.mark.parametrize(
    "name", sorted(VIETNAMESE_FAMILY_NAMES_UNACCENTED | AMBIGUOUS_UNACCENTED_FAMILY_NAMES)
)
def test_an_unaccented_family_name_is_ascii_with_one_capital(name: str) -> None:
    assert name.isascii()
    assert name.istitle()


@pytest.mark.parametrize("word", LIST_WORDS)
def test_every_word_of_a_list_is_in_nfc(word: str) -> None:
    assert unicodedata.is_normalized("NFC", word)


def test_the_stoplist_is_the_titles_and_the_nine_stop_words() -> None:
    assert NAME_NEIGHBOUR_STOPLIST == TITLES | NAME_STOP_WORDS
    assert TITLES.isdisjoint(NAME_STOP_WORDS)


NAMES = st.sampled_from(["Ana", "Bình", "Đức", "Kathryn", "Lan", "Minh", "Reynolds", "Vũ"])
NEIGHBOURS = st.one_of(
    NAMES,
    st.sampled_from(sorted(NAME_NEIGHBOUR_STOPLIST)),
    st.sampled_from(["call", "near", "today", "12", "B2", "ORD-12", "ORD-AB", "A.Lan", "Vu@x"]),
)
SEPARATORS = st.sampled_from([" ", " ", " ", "  ", ", ", "\n", ". "])


@st.composite
def name_in_context(draw: st.DrawFn) -> tuple[str, int, int]:
    """A message with a span of 1 to 5 names that the model found, and neighbours around it."""
    before = draw(st.lists(NEIGHBOURS, max_size=4))
    names = draw(st.lists(NAMES, min_size=1, max_size=5))
    after = draw(st.lists(NEIGHBOURS, max_size=4))
    form = nfd if draw(st.booleans()) else nfc
    head = form("".join(word + draw(SEPARATORS) for word in before))
    name = form(" ".join(names))
    tail = form("".join(draw(SEPARATORS) + word for word in after))
    return head + name + tail, len(head), len(head) + len(name)


def joinable_neighbour(token: str) -> bool:
    is_word = WORD.fullmatch(token) is not None
    return is_word and token[0].isupper() and nfc(token) not in NAME_NEIGHBOUR_STOPLIST


def neighbour_tokens(message: str, span: TextSpan) -> list[str]:
    # The tokens one space away on each side. A full stop or a comma after the right one is not
    # part of it, while a code such as "ORD-12" or "A.Lan" stays one token that is no word.
    left = re.search(r"(?:\A|\s)(\S+) \Z", message[: span.start])
    right = re.match(r" (\S+)", message[span.end :])
    return [
        *([left.group(1)] if left else []),
        *([right.group(1).rstrip(SENTENCE_PUNCTUATION)] if right else []),
    ]


def growth_faults(message: str, start: int, end: int) -> list[str]:
    """Name each invariant of the design (Layer 1, names, item 1) that the grown span breaks."""
    span = grow_person_span(message, start, end)
    faults: list[str] = []
    if not span.start <= start <= end <= span.end:
        faults.append("G1: the grown span does not hold the name")
    added = [*message[span.start : start].split(" ")[:-1], *message[end : span.end].split(" ")[1:]]
    if not all(joinable_neighbour(word) for word in added):
        faults.append("G2, G4: an added word is not a capitalized word one space away, or a stop")
    words = len(WORD.findall(message, span.start, span.end))
    original = len(WORD.findall(message, start, end))
    grew = span != TextSpan(start, end)
    if grew and words > max(NAME_WORD_COUNTS):
        faults.append("G3: the grown name has more than 4 words")
    if grew and original >= max(NAME_WORD_COUNTS):
        faults.append("G3: a name of 4 words or more grew")
    stopped_early = any(joinable_neighbour(token) for token in neighbour_tokens(message, span))
    if words < max(NAME_WORD_COUNTS) and stopped_early:
        faults.append("G5: a capitalized word that may join is left beside the name")
    return faults


@given(name_in_context())
def test_a_grown_name_keeps_every_invariant_of_the_design(case: tuple[str, int, int]) -> None:
    message, start, end = case

    assert growth_faults(message, start, end) == []


CUES = st.sampled_from(
    ["", "my name is ", "I am ", "this is ", "on behalf of ", "Regards, ", "Thanks, ", "my sister "]
)
WORDS = st.sampled_from(["Lan", "Anh", "Reynolds", "Vũ", "lan", "anh", "co"])


@st.composite
def labeled_span_after_a_cue(draw: st.DrawFn) -> tuple[str, TextSpan, bool]:
    """A message whose span the model labeled, and whether the design makes it a name."""
    cue = draw(CUES)
    words = draw(st.lists(WORDS, min_size=1, max_size=5))
    message = f"Hello. {cue}" + " ".join(words) + " here."
    start = len(f"Hello. {cue}")
    is_name = bool(cue) and len(words) in NAME_WORD_COUNTS and all(w[0].isupper() for w in words)
    return message, TextSpan(start, start + len(" ".join(words))), is_name


@given(labeled_span_after_a_cue())
def test_a_labeled_span_is_a_name_exactly_after_a_cue(case: tuple[str, TextSpan, bool]) -> None:
    message, span, is_name = case

    names = person_cue_names(message, (span,))

    name = Detection(span.start, span.end, PseudonymType.NAME, DetectionSource.RULE)
    assert names == ((name,) if is_name else ())


FAMILY_NAMES = st.sampled_from(sorted(VIETNAMESE_FAMILY_NAMES | VIETNAMESE_FAMILY_NAMES_UNACCENTED))
GIVEN_NAMES = st.sampled_from(["Văn", "Thị", "Lan", "An", "Bình", "Minh", "Thu", "Hà", "Ngọc"])
BEFORE_A_NAME = st.sampled_from(["", "Hi ", "Dear ", "Thanks ", "Mr ", "Mr. ", "Bà ", "Dear Mr "])
AFTER_A_NAME = st.sampled_from(["", " called.", ", thanks", ".", " today", " ORD-12"])


@st.composite
def vietnamese_name_in_context(draw: st.DrawFn) -> tuple[str, int, int]:
    """A sentence in lowercase with one Vietnamese name, its family name first or last."""
    family = draw(FAMILY_NAMES)
    given_names = draw(st.lists(GIVEN_NAMES, min_size=1, max_size=3))
    words = [family, *given_names] if draw(st.booleans()) else [*given_names, family]
    name = " ".join(words).upper() if draw(st.booleans()) else " ".join(words)
    form = nfd if draw(st.booleans()) else nfc
    head = form("please ask " + draw(BEFORE_A_NAME))
    return head + form(name) + form(draw(AFTER_A_NAME)), len(head), len(head) + len(form(name))


@given(vietnamese_name_in_context())
def test_a_vietnamese_name_is_found_once_with_its_whole_span(case: tuple[str, int, int]) -> None:
    message, start, end = case

    assert vietnamese_names(message) == [message[start:end]]


TOKENS = st.one_of(
    FAMILY_NAMES,
    GIVEN_NAMES,
    st.sampled_from(sorted(TITLES | NAME_STOP_WORDS | AMBIGUOUS_UNACCENTED_FAMILY_NAMES)),
    st.sampled_from(["the", "lamp", "Main", "Street", "12", "ORD-12", "Tran-01", "x@Le", "You"]),
)
TOKEN_SEPARATORS = st.sampled_from([" ", " ", " ", "  ", ", ", ". ", "\n"])


@st.composite
def capitalized_text(draw: st.DrawFn) -> str:
    """A text of family names, given names, titles, stop words, codes, and other words."""
    tokens = draw(st.lists(TOKENS, min_size=1, max_size=10))
    return "".join(token + draw(TOKEN_SEPARATORS) for token in tokens)


def key(word: str) -> str:
    return nfc(word).casefold()


FAMILY_NAME_KEYS = set(map(key, VIETNAMESE_FAMILY_NAMES | VIETNAMESE_FAMILY_NAMES_UNACCENTED))
AMBIGUOUS_KEYS = set(map(key, AMBIGUOUS_UNACCENTED_FAMILY_NAMES))
MIDDLE_NAME_KEYS = set(map(key, VIETNAMESE_MIDDLE_NAMES))
RULE_NAME = (PseudonymType.NAME, DetectionSource.RULE)


def is_family_name_at(words: list[str], index: int) -> bool:
    after = {key(word) for word in words[index + 1 : index + 2]}
    is_ambiguous = key(words[index]) in AMBIGUOUS_KEYS
    return key(words[index]) in FAMILY_NAME_KEYS or (
        is_ambiguous and bool(after & MIDDLE_NAME_KEYS)
    )


# A token of a run: a word, then at most one mark of punctuation.
RUN_TOKEN = re.compile(rf"({WORD.pattern})([.,!?;:]?)")


def capitalized_runs(message: str) -> list[list[TextSpan]]:
    """The runs of the design, read token by token (Layer 1, names, item 2).

    A run holds capitalized words one space apart. A stop word, a word in lowercase, or a code
    ends it, punctuation after a word ends it too, except a period after a title, and a title
    starts a new run.
    """
    runs: list[list[TextSpan]] = [[]]
    joins_next = False
    previous_end = 0
    for token in re.finditer(r"\S+", message):
        parts = RUN_TOKEN.fullmatch(token.group())
        word = parts.group(1) if parts else ""
        is_title = nfc(word) in TITLES
        if not word or not word[0].isupper() or nfc(word) in NAME_STOP_WORDS:
            runs.append([])
            joins_next = False
            continue
        if is_title or not joins_next or message[previous_end : token.start()] != " ":
            runs.append([])
        runs[-1].append(TextSpan(token.start(), token.start() + len(word)))
        punctuation = token.group()[len(word) :]
        joins_next = punctuation == "" or (punctuation == "." and is_title)
        previous_end = token.end()
    return [run for run in runs if run]


def is_window(words: list[str], first: int, stop: int) -> bool:
    # A window of the design: 2 to 4 words of a run whose first or last word is a family name.
    has_family_end = is_family_name_at(words, first) or is_family_name_at(words, stop - 1)
    return stop - first in NAME_WORD_COUNTS and has_family_end


def longest_window(words: list[str]) -> int:
    lengths = [
        stop - first
        for first in range(len(words))
        for stop in range(first + 1, len(words) + 1)
        if is_window(words, first, stop)
    ]
    return max(lengths, default=0)


def found_name_faults(message: str, detection: Detection, run: list[TextSpan]) -> list[str]:
    """Name each invariant of the design (Layer 1, names, item 2) that one found name breaks."""
    words = [message[span.start : span.end] for span in run]
    starts = [span.start for span in run]
    ends = [span.end for span in run]
    first = starts.index(detection.start)
    stop = ends.index(detection.end) + 1
    # A title left out of the name still counts in its window.
    has_title = first == 1 and nfc(words[0]) in TITLES and is_window(words, 0, stop)
    window_start = first - 1 if has_title else first
    faults: list[str] = []
    if (detection.pseudonym_type, detection.source) != RULE_NAME:
        faults.append("V1: a name that is no NAME of the rule source")
    if stop - first == 1 and not has_title:
        faults.append("V1: a name of one word without a title before it")
    if any(nfc(word) in NAME_NEIGHBOUR_STOPLIST for word in words[first:stop]):
        faults.append("V3: a title or a stop word inside a name")
    if not is_window(words, window_start, stop):
        faults.append("V2: the name is no window of 2 to 4 words with a family name at one end")
    if stop - window_start != longest_window(words):
        faults.append("V3: a longer window of the same run")
    return faults


def run_faults(message: str, detection: Detection, runs: list[list[TextSpan]]) -> list[str]:
    """Name the fault of a found name that does not start and end on words of one run."""
    in_run = [
        run
        for run in runs
        if detection.start in {span.start for span in run}
        and detection.end in {span.end for span in run}
    ]
    return found_name_faults(message, detection, in_run[0]) if in_run else ["V1: not in a run"]


def code_faults(message: str, detection: Detection) -> list[str]:
    """Name each side on which a found name is joined to a code (Layer 1, names, opening)."""
    joined_before = re.search(r"[^\W_][-./@]\Z", message[: detection.start]) is not None
    joined_after = re.match(r"[-./@][^\W_]", message[detection.end :]) is not None
    return [
        *(["a name joined to a code before it"] if joined_before else []),
        *(["a name joined to a code after it"] if joined_after else []),
    ]


def vietnamese_name_faults(message: str) -> list[str]:
    """Name each invariant of the design that a name found in the message breaks."""
    runs = capitalized_runs(message)
    return [
        fault
        for detection in VietnameseNameDetector().detect(message, ())
        for fault in (*run_faults(message, detection, runs), *code_faults(message, detection))
    ]


@given(capitalized_text())
def test_a_vietnamese_name_keeps_every_invariant_of_the_design(message: str) -> None:
    assert vietnamese_name_faults(message) == []


@given(capitalized_text())
def test_decomposed_diacritics_give_the_same_vietnamese_names(message: str) -> None:
    decomposed = [nfc(name) for name in vietnamese_names(nfd(message))]

    assert decomposed == vietnamese_names(nfc(message))

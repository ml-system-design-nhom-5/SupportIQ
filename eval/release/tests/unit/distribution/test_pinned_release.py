"""The pinned file holds exactly two LF lines of ASCII: the release ID and the archive size."""

import pytest

from supportiq_release.distribution.domain import (
    MAX_ARCHIVE_SIZE_BYTES,
    PinnedRelease,
    PinnedReleaseInvalidError,
    PinnedReleaseProblem,
    format_pinned_release,
    parse_pinned_release,
)

VALID = "release_id=release-2026-11-18-02\narchive_size_bytes=383912345\n"


def test_a_valid_pinned_file_gives_its_release_id_and_archive_size() -> None:
    pinned = parse_pinned_release(VALID)

    assert pinned == PinnedRelease("release-2026-11-18-02", 383_912_345)


def test_formatting_writes_the_two_lines_that_parsing_reads_back() -> None:
    pinned = PinnedRelease("release-2026-11-18-02", 383_912_345)

    text = format_pinned_release(pinned)

    assert text == VALID
    assert parse_pinned_release(text) == pinned


@pytest.mark.parametrize(
    "text",
    [
        VALID.replace("\n", "\r\n"),
        "# pinned\n" + VALID,
        VALID + "extra=1\n",
        VALID.rstrip("\n"),
        VALID + "\n",
        VALID.replace("release-2026", "rélease-2026"),
        "",
    ],
    ids=["crlf", "comment", "third-line", "no-final-lf", "empty-third-line", "not-ascii", "empty"],
)
def test_a_file_that_is_not_two_lf_lines_of_ascii_is_refused(text: str) -> None:
    with pytest.raises(PinnedReleaseInvalidError) as refused:
        parse_pinned_release(text)

    assert refused.value.problem is PinnedReleaseProblem.NOT_TWO_LINES


@pytest.mark.parametrize(
    "first_line",
    [
        "release_id=../x",
        "release_id=a/b",
        "release_id=.x",
        "release_id=" + "a" * 65,
        "release_id=",
        "release=release-2026-11-18-02",
        "release_id release-2026-11-18-02",
        " release_id=release-2026-11-18-02",
    ],
)
def test_a_release_id_line_that_breaks_its_rule_is_refused(first_line: str) -> None:
    with pytest.raises(PinnedReleaseInvalidError) as refused:
        parse_pinned_release(f"{first_line}\narchive_size_bytes=1\n")

    assert refused.value.problem is PinnedReleaseProblem.RELEASE_ID_INVALID


@pytest.mark.parametrize(
    "second_line",
    [
        "archive_size_bytes=0",
        "archive_size_bytes=0123",
        f"archive_size_bytes={MAX_ARCHIVE_SIZE_BYTES + 1}",
        "archive_size_bytes=" + "9" * 11,
        # More digits than int() takes, so the length is refused before any conversion.
        "archive_size_bytes=" + "9" * 4300,
        "archive_size_bytes=-1",
        "archive_size_bytes=1.5",
        "archive_size_bytes=",
        "archive_size_bytes= 12",
        "size=12",
    ],
)
def test_a_size_line_that_breaks_its_rule_is_refused(second_line: str) -> None:
    with pytest.raises(PinnedReleaseInvalidError) as refused:
        parse_pinned_release(f"release_id=fake-release-1\n{second_line}\n")

    assert refused.value.problem is PinnedReleaseProblem.ARCHIVE_SIZE_INVALID


def test_the_largest_size_that_github_takes_is_accepted() -> None:
    text = f"release_id=fake-release-1\narchive_size_bytes={MAX_ARCHIVE_SIZE_BYTES}\n"

    assert parse_pinned_release(text).archive_size_bytes == MAX_ARCHIVE_SIZE_BYTES


def test_formatting_refuses_a_release_that_the_file_cannot_hold() -> None:
    with pytest.raises(PinnedReleaseInvalidError):
        format_pinned_release(PinnedRelease("fake-release-1", 0))


def test_the_message_names_the_file_and_the_problem_only() -> None:
    with pytest.raises(PinnedReleaseInvalidError) as refused:
        parse_pinned_release("release_id=secret-looking/value\narchive_size_bytes=1\n")

    assert "secret-looking" not in str(refused.value)
    assert "pinned-release.txt" in str(refused.value)

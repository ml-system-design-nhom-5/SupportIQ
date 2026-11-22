"""The pinned file: the newest published release and the size of its archive, in plain text.

`eval/releases/pinned-release.txt` holds exactly two lines, `release_id=<id>` and
`archive_size_bytes=<n>`, each ended by LF, in ASCII, without comments or spaces, so that bash
reads it before anything is installed (release download and Modal deploy design, The pinned
file). Release IDs are opaque (CON-15): the newest release is the one that this file names.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.candidate.domain import RELEASE_ID_PATTERN
from supportiq_release.errors import ReleaseCommandError

PINNED_RELEASE_FILE_NAME = "pinned-release.txt"
# GitHub takes each file of a release only under 2 GiB (GitHub: About releases).
MAX_ARCHIVE_SIZE_BYTES = 2**31 - 1
_RELEASE_ID_KEY = "release_id"
_ARCHIVE_SIZE_KEY = "archive_size_bytes"
_LINE_END = "\n"
# Two lines split at LF give three parts: the two lines and the empty rest after the final LF.
_PARTS_OF_TWO_LINES = 3
# A size without a leading zero, from 1, of at most 10 digits, the digits of the largest size, so
# a long value is refused before it becomes a number.
_SIZE_PATTERN = re.compile(r"[1-9][0-9]{0,9}")


class PinnedReleaseProblem(StrEnum):
    """Why a pinned file is refused."""

    UNREADABLE = "missing_or_unreadable"
    NOT_TWO_LINES = "not_two_lf_lines_of_ascii"
    RELEASE_ID_INVALID = "release_id_line_invalid"
    ARCHIVE_SIZE_INVALID = "archive_size_bytes_line_invalid"


class PinnedReleaseInvalidError(ReleaseCommandError):
    """The pinned file breaks its format. The message names the problem only."""

    def __init__(self, problem: PinnedReleaseProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the pinned file is refused.
        """
        super().__init__(f"The pinned file {PINNED_RELEASE_FILE_NAME} is refused: {problem}.")
        self.problem = problem


@dataclass(frozen=True, slots=True)
class PinnedRelease:
    """The newest published release, as the pinned file names it.

    Attributes:
        release_id: The release ID, with the pattern of `release_id` in the contract.
        archive_size_bytes: The size of `<release_id>.tar.gz`, from 1 to 2 GiB minus 1 byte.
    """

    release_id: str
    archive_size_bytes: int


def parse_pinned_release(text: str) -> PinnedRelease:
    """Read the text of a pinned file strictly.

    Args:
        text: The whole text of the file.

    Returns:
        The pinned release.

    Raises:
        PinnedReleaseInvalidError: The text is not two LF lines of ASCII, or a line breaks its
            rule.
    """
    lines = text.split(_LINE_END)
    is_two_lines = len(lines) == _PARTS_OF_TWO_LINES and not lines[-1]
    if not text.isascii() or "\r" in text or not is_two_lines:
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.NOT_TWO_LINES)
    release_id = _value(lines[0], _RELEASE_ID_KEY, PinnedReleaseProblem.RELEASE_ID_INVALID)
    if RELEASE_ID_PATTERN.fullmatch(release_id) is None:
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.RELEASE_ID_INVALID)
    size = _value(lines[1], _ARCHIVE_SIZE_KEY, PinnedReleaseProblem.ARCHIVE_SIZE_INVALID)
    if _SIZE_PATTERN.fullmatch(size) is None or int(size) > MAX_ARCHIVE_SIZE_BYTES:
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.ARCHIVE_SIZE_INVALID)
    return PinnedRelease(release_id=release_id, archive_size_bytes=int(size))


def format_pinned_release(pinned: PinnedRelease) -> str:
    """Write the text of a pinned file, which `parse_pinned_release` reads back.

    Args:
        pinned: The pinned release.

    Returns:
        The two lines, each ended by LF.

    Raises:
        PinnedReleaseInvalidError: The release ID or the size breaks its rule.
    """
    text = (
        f"{_RELEASE_ID_KEY}={pinned.release_id}{_LINE_END}"
        f"{_ARCHIVE_SIZE_KEY}={pinned.archive_size_bytes}{_LINE_END}"
    )
    parse_pinned_release(text)
    return text


def _value(line: str, key: str, problem: PinnedReleaseProblem) -> str:
    name, separator, value = line.partition("=")
    if name != key or not separator:
        raise PinnedReleaseInvalidError(problem)
    return value

"""Read and write the pinned file, `eval/releases/pinned-release.txt`.

Only `pack-release --pin` writes it, both lines at once: into a new temporary file next to it,
then renamed over the old one, so a failure leaves the old file whole (release download and Modal
deploy design, The pinned file).
"""

from pathlib import Path

from supportiq_release.distribution.adapters.release_archive import FILE_MODE
from supportiq_release.distribution.domain import (
    PINNED_RELEASE_FILE_NAME,
    PinnedRelease,
    PinnedReleaseInvalidError,
    PinnedReleaseProblem,
    format_pinned_release,
    parse_pinned_release,
)
from supportiq_release.files import hidden_partial_path

_ENCODING = "ascii"


def read_pinned_release(records: Path) -> PinnedRelease:
    """Read the pinned file of the release records.

    Args:
        records: The folder of the records of every release, such as `eval/releases`.

    Returns:
        The pinned release.

    Raises:
        PinnedReleaseInvalidError: The file is missing, a link, unreadable, or breaks its format.
    """
    path = records / PINNED_RELEASE_FILE_NAME
    if path.is_symlink() or not path.is_file():
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.UNREADABLE)
    try:
        text = path.read_bytes().decode(_ENCODING)
    except OSError as error:
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.UNREADABLE) from error
    except UnicodeDecodeError as error:
        raise PinnedReleaseInvalidError(PinnedReleaseProblem.NOT_TWO_LINES) from error
    return parse_pinned_release(text)


def write_pinned_release(records: Path, pinned: PinnedRelease) -> Path:
    """Write the pinned file, replacing the old one only once the new one is whole.

    Args:
        records: The folder of the records of every release.
        pinned: The release and the size of its archive.

    Returns:
        The pinned file.

    Raises:
        PinnedReleaseInvalidError: The release ID or the size breaks its rule.
        OSError: The file cannot be written; the old one is left as it was.
    """
    data = format_pinned_release(pinned).encode(_ENCODING)
    path = records / PINNED_RELEASE_FILE_NAME
    temporary = hidden_partial_path(path)
    try:
        with temporary.open("xb") as file:
            file.write(data)
        temporary.chmod(FILE_MODE)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path

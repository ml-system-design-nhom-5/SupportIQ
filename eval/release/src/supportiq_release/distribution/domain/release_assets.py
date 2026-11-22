"""The GitHub Release of a release ID: exactly one uploaded asset, its archive, of a known size.

Each published release has exactly one GitHub Release asset, `<release_id>.tar.gz`, and its tag
is the release ID itself (ADR-0030, Release archives, statement 1). The pinned file states the
size of that archive, and a change of the pinned file is checked against it (statement 5).
"""

from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.candidate.domain import RELEASE_ID_PATTERN
from supportiq_release.distribution.domain.archive_contents import archive_name
from supportiq_release.errors import ReleaseCheckFailedError, ReleaseCommandError


class AssetState(StrEnum):
    """The state of a release asset, as the GitHub REST API states it."""

    UPLOADED = "uploaded"
    OPEN = "open"


class ReleaseProblem(StrEnum):
    """Why the GitHub Release of a release ID is refused."""

    NOT_PUBLISHED = "no_published_github_release_for_the_tag"
    NOT_ONE_ASSET = "not_exactly_one_asset"
    NOT_THE_ARCHIVE = "asset_is_not_the_archive_of_the_release"
    NOT_UPLOADED = "asset_not_uploaded"
    SIZE_DIFFERS_FROM_THE_PINNED_FILE = "archive_size_differs_from_the_pinned_file"
    DOWNLOAD_SIZE_DIFFERS = "downloaded_size_differs_from_the_asset"


class ReleaseRefusedError(ReleaseCheckFailedError):
    """The GitHub Release of a release ID fails a check. The message names the problem only."""

    def __init__(self, problem: ReleaseProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the GitHub Release is refused.
        """
        super().__init__(f"The GitHub Release is refused: {problem}.")
        self.problem = problem


class ReleaseIdInvalidError(ReleaseCommandError):
    """A release ID breaks the pattern of the contract, so no path is built from it."""

    def __init__(self) -> None:
        """Build the error with a message that names the pattern, never the value."""
        super().__init__(
            f"The release ID is refused: it does not match {RELEASE_ID_PATTERN.pattern}."
        )


@dataclass(frozen=True, slots=True)
class ReleaseAsset:
    """One asset of a GitHub Release.

    Attributes:
        asset_id: The ID that the download of the asset names.
        name: The file name of the asset.
        state: Whether the upload is finished.
        size_bytes: The size that GitHub states.
    """

    asset_id: int
    name: str
    state: AssetState
    size_bytes: int


def checked_release_id(text: str) -> str:
    """Return a release ID once it matches the pattern of `release_id` in the contract.

    Args:
        text: The release ID as given.

    Returns:
        The same text.

    Raises:
        ReleaseIdInvalidError: It breaks the pattern, for example it holds `/` or starts with `.`.
    """
    if RELEASE_ID_PATTERN.fullmatch(text) is None:
        raise ReleaseIdInvalidError
    return text


def archive_asset(release_id: str, assets: tuple[ReleaseAsset, ...]) -> ReleaseAsset:
    """Return the one asset of a GitHub Release, once it is the uploaded archive of the release.

    Args:
        release_id: The release ID, which is also the tag.
        assets: Every asset of the GitHub Release.

    Returns:
        The asset `<release_id>.tar.gz`.

    Raises:
        ReleaseRefusedError: The release has not exactly one asset, or it has another name, or
            its upload is not finished.
    """
    if len(assets) != 1:
        raise ReleaseRefusedError(ReleaseProblem.NOT_ONE_ASSET)
    asset = assets[0]
    if asset.name != archive_name(release_id):
        raise ReleaseRefusedError(ReleaseProblem.NOT_THE_ARCHIVE)
    if asset.state is not AssetState.UPLOADED:
        raise ReleaseRefusedError(ReleaseProblem.NOT_UPLOADED)
    return asset


def check_pinned_size(asset: ReleaseAsset, archive_size_bytes: int) -> None:
    """Check that the archive on GitHub has the size that the pinned file states.

    Args:
        asset: The archive asset.
        archive_size_bytes: The size of the pinned file.

    Raises:
        ReleaseRefusedError: The sizes differ.
    """
    if asset.size_bytes != archive_size_bytes:
        raise ReleaseRefusedError(ReleaseProblem.SIZE_DIFFERS_FROM_THE_PINNED_FILE)

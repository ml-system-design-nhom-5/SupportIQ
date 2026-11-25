"""Read the manifest of a published release from the repository, the source of trust.

A release is published when `eval/releases/<release_id>/release-manifest.json` is in git and
links a passing gate run (release command README, Publish). Its bytes decide whether an archive,
a cached folder, or a folder to deploy holds that release (ADR-0030, Download, statement 3).
The format is read with `read_release_manifest` of `ai-service`, never a copy of its rules.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.release.manifest import ReleaseInvalidError, read_release_manifest

from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.distribution.domain import ArchiveContents, archive_contents
from supportiq_release.errors import ReleaseCommandError


class PublishedProblem(StrEnum):
    """Why a release ID has no published manifest in the repository."""

    MISSING = "no_manifest_in_the_release_records"
    INVALID = "manifest_breaks_its_format"
    OTHER_RELEASE = "manifest_of_another_release_id"
    NOT_PUBLISHED = "manifest_links_no_passing_gate_run"


class ReleaseNotPublishedError(ReleaseCommandError):
    """A release ID has no published manifest in the repository. The message names the problem."""

    def __init__(self, problem: PublishedProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the release is not published.
        """
        super().__init__(f"The release is not published in the release records: {problem}.")
        self.problem = problem


@dataclass(frozen=True, slots=True)
class PublishedManifest:
    """The manifest of a published release, as it is in the repository.

    Attributes:
        release_id: The release ID.
        path: `<records>/<release_id>/release-manifest.json`.
        content: Every byte of the manifest.
        size_bytes_by_path: The size of each file that the manifest names, by its path.
    """

    release_id: str
    path: Path
    content: bytes
    size_bytes_by_path: Mapping[str, int]

    def contents(self) -> ArchiveContents:
        """Return the members that the archive of this release must hold.

        Returns:
            The manifest and every file it names, with their sizes.
        """
        return archive_contents(len(self.content), self.size_bytes_by_path)


def read_published_manifest(records: Path, release_id: str) -> PublishedManifest:
    """Read the manifest of a published release from the release records.

    Args:
        records: The folder of the records of every release, such as `eval/releases`.
        release_id: A release ID that matches the pattern of the contract.

    Returns:
        The manifest with its bytes and the size of each file.

    Raises:
        ReleaseNotPublishedError: The manifest is missing, a link, or unreadable, breaks its
            format, names another release ID, or links no passing gate run.
    """
    path = records / release_id / MANIFEST_FILE_NAME
    if path.is_symlink() or not path.is_file():
        raise ReleaseNotPublishedError(PublishedProblem.MISSING)
    try:
        content = path.read_bytes()
        manifest = read_release_manifest(path)
    except (OSError, ReleaseInvalidError) as error:
        raise ReleaseNotPublishedError(PublishedProblem.INVALID) from error
    if manifest.release_id != release_id:
        raise ReleaseNotPublishedError(PublishedProblem.OTHER_RELEASE)
    if manifest.gate_run is None:
        raise ReleaseNotPublishedError(PublishedProblem.NOT_PUBLISHED)
    sizes = {entry.path: entry.size_bytes for _asset, entry in manifest.assets.named_files()}
    return PublishedManifest(
        release_id=release_id, path=path, content=content, size_bytes_by_path=sizes
    )

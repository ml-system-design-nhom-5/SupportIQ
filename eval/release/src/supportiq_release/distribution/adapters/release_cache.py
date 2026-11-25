"""The release cache: checked release folders, made visible only by an atomic rename.

A release is the folder `<cache>/<release_id>/`. It is created only by renaming a staging
folder, `<cache>/.<release_id>.partial-<hex>`, once every member of the archive and every file
passed its check (ADR-0030, Download, statement 4). A cached folder is never repaired, replaced,
or deleted: when it fails its check, the command says to remove it by hand.
"""

import shutil
from enum import StrEnum
from pathlib import Path

from app.release.manifest import ReleaseInvalidError, verify_release

from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.distribution.adapters.published_manifest import PublishedManifest
from supportiq_release.distribution.adapters.release_archive import unpack_archive
from supportiq_release.distribution.domain import (
    ArchiveProblem,
    ArchiveRefusedError,
    archive_name,
)
from supportiq_release.errors import ReleaseCheckFailedError
from supportiq_release.files import describe_release_refusal, hidden_partial_path, new_output_folder


class CachedReleaseProblem(StrEnum):
    """Why a folder of the cache is not a checked release."""

    NOT_A_FOLDER = "not_a_folder"
    MANIFEST_UNREADABLE = "manifest_missing_or_unreadable"
    MANIFEST_DIFFERS_FROM_GIT = "manifest_differs_from_git"
    REFUSED_BY_VERIFY_RELEASE = "refused_by_verify_release"


class CachedReleaseInvalidError(ReleaseCheckFailedError):
    """A folder of the cache fails its check. The message names the folder and the reason."""

    def __init__(self, folder: Path, problem: CachedReleaseProblem, reason: str = "") -> None:
        """Build the error with a message that names the folder, the problem, and the remedy.

        Args:
            folder: The folder of the cache.
            problem: Why it is not a checked release.
            reason: The refusal of `verify_release`, when it refused the folder.
        """
        detail = f" ({reason})" if reason else ""
        super().__init__(
            f"The cached release {folder} fails its check: {problem}{detail}."
            " Remove that folder to download the release again."
        )
        self.folder = folder
        self.problem = problem


class ReleaseFilesRefusedError(ReleaseCheckFailedError):
    """`verify_release` refuses the files of a downloaded archive. The message is its reason."""

    def __init__(self, error: ReleaseInvalidError) -> None:
        """Build the error with the reason, the asset, and the path of the refusal.

        Args:
            error: The refusal of `verify_release`.
        """
        super().__init__(describe_release_refusal(error))


def release_folder(cache: Path, release_id: str) -> Path:
    """Return the folder of a release in the cache.

    Args:
        cache: The cache folder, an absolute path.
        release_id: The release ID, already checked against its pattern.

    Returns:
        `<cache>/<release_id>`.
    """
    return cache / release_id


def is_cached(folder: Path) -> bool:
    """Tell whether the cache holds an entry for a release, whatever it is.

    Args:
        folder: The folder of the release in the cache.

    Returns:
        True when the path exists, as a link too.
    """
    return folder.is_symlink() or folder.exists()


def check_cached_release(folder: Path, published: PublishedManifest) -> None:
    """Check that a folder of the cache holds exactly the published release.

    Args:
        folder: The folder of the release in the cache.
        published: The manifest of the release in git.

    Raises:
        CachedReleaseInvalidError: The entry is not a folder, its manifest is missing or differs
            from git by one byte, or `verify_release` refuses it.
    """
    manifest = folder / MANIFEST_FILE_NAME
    if folder.is_symlink() or not folder.is_dir():
        raise CachedReleaseInvalidError(folder, CachedReleaseProblem.NOT_A_FOLDER)
    try:
        content = manifest.read_bytes()
    except OSError as error:
        raise CachedReleaseInvalidError(folder, CachedReleaseProblem.MANIFEST_UNREADABLE) from error
    if content != published.content:
        raise CachedReleaseInvalidError(folder, CachedReleaseProblem.MANIFEST_DIFFERS_FROM_GIT)
    try:
        verify_release(manifest)
    except ReleaseInvalidError as error:
        reason = describe_release_refusal(error)
        problem = CachedReleaseProblem.REFUSED_BY_VERIFY_RELEASE
        raise CachedReleaseInvalidError(folder, problem, reason) from error


def new_partial_archive(cache: Path, release_id: str) -> Path:
    """Return the path of a new hidden partial archive in the cache, on the same file system.

    Args:
        cache: The cache folder.
        release_id: The release ID.

    Returns:
        `<cache>/.<release_id>.tar.gz.partial-<hex>`, which does not exist yet.
    """
    return hidden_partial_path(cache / archive_name(release_id))


def free_bytes(cache: Path) -> int:
    """Return the free space of the file system that the cache is or will be on.

    The cache folder may not exist yet: a run that is declined or fails creates nothing, so the
    space is measured on the nearest folder above it that exists.

    Args:
        cache: The cache folder, an absolute path.

    Returns:
        The free bytes.
    """
    existing = next(folder for folder in (cache, *cache.parents) if folder.is_dir())
    return shutil.disk_usage(existing).free


def install_release(archive: Path, published: PublishedManifest, folder: Path) -> None:
    """Unpack and check an archive, and rename it to the folder of the release in the cache.

    Args:
        archive: The downloaded archive.
        published: The manifest of the release in git.
        folder: The folder of the release in the cache, which does not exist.

    Raises:
        ArchiveRefusedError: A member is refused, or the manifest differs from git.
        ReleaseFilesRefusedError: `verify_release` refuses the files.
        OutputFolderError: The folder exists or cannot be written.
        OSError: A file cannot be written.
    """
    with new_output_folder(folder, (published.path,)) as staging:
        unpack_archive(archive, published.contents(), staging)
        manifest = staging / MANIFEST_FILE_NAME
        if manifest.read_bytes() != published.content:
            problem = ArchiveProblem.MANIFEST_DIFFERS_FROM_GIT
            raise ArchiveRefusedError(problem, MANIFEST_FILE_NAME)
        try:
            verify_release(manifest)
        except ReleaseInvalidError as error:
            raise ReleaseFilesRefusedError(error) from error

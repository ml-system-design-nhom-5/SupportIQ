"""What the archive of a release may hold, and the checks of each member while it is read.

An archive holds `release-manifest.json` and every file that the manifest in git names, at its
path in the release folder, each once and as a regular file of its stated size, and nothing
else (ADR-0030, Release archives, statement 1). The manifest in git is the source of trust
(ADR-0030, Download, statement 3), so the allowed names are its paths: an absolute name, a name
with `..`, or any other name is refused by the name alone.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.errors import ReleaseCheckFailedError, ReleaseCommandError

_ARCHIVE_SUFFIX = ".tar.gz"
_BYTES_PER_MIB = 1024 * 1024


class MemberType(StrEnum):
    """The kind of an archive member that the checks tell apart."""

    REGULAR_FILE = "regular_file"
    OTHER = "other"


class ArchiveProblem(StrEnum):
    """Why an archive is refused."""

    UNREADABLE = "archive_unreadable"
    MEMBER_NOT_ALLOWED = "member_not_named_by_the_manifest"
    MEMBER_NOT_A_REGULAR_FILE = "member_not_a_regular_file"
    MEMBER_REPEATED = "member_repeated"
    MEMBER_SIZE_DIFFERS = "member_size_differs_from_the_manifest"
    MEMBER_MISSING = "member_missing"
    MANIFEST_DIFFERS_FROM_GIT = "manifest_differs_from_git"


class ArchiveRefusedError(ReleaseCheckFailedError):
    """An archive fails a check. The message names a member only when the manifest names it."""

    def __init__(self, problem: ArchiveProblem, member: str | None = None) -> None:
        """Build the error with a message that names the problem and an allowed member.

        Args:
            problem: Why the archive is refused.
            member: The path of the member, only when it is a path of the manifest in git; the
                name of any other member could hold any text, so it is never printed.
        """
        where = "" if member is None else f" member={member}"
        super().__init__(f"The archive is refused: {problem}.{where}")
        self.problem = problem
        self.member = member


class NotEnoughSpaceError(ReleaseCommandError):
    """The file system of the cache has too little free space for the archive and its files."""

    def __init__(self, needed_bytes: int, free_bytes: int) -> None:
        """Build the error with a message that names both amounts.

        Args:
            needed_bytes: The bytes of the archive and of every file it holds.
            free_bytes: The free bytes of the file system of the cache.
        """
        super().__init__(
            f"Not enough free space in the cache: {mebibytes(needed_bytes)} MiB needed,"
            f" {mebibytes(free_bytes)} MiB free."
        )
        self.needed_bytes = needed_bytes
        self.free_bytes = free_bytes


@dataclass(frozen=True, slots=True)
class ArchiveContents:
    """The members that the archive of one release must hold, each once.

    Attributes:
        size_bytes_by_path: The size of each allowed member, by its path in the release folder.
    """

    size_bytes_by_path: Mapping[str, int]

    def check_member(
        self, path: str, member_type: MemberType, size_bytes: int, seen: frozenset[str]
    ) -> None:
        """Check one member before any of its bytes is written.

        Args:
            path: The name of the member, as the archive states it.
            member_type: Whether the member is a regular file.
            size_bytes: The size that the archive states for it.
            seen: The members already read.

        Raises:
            ArchiveRefusedError: The member is not named by the manifest, is not a regular file,
                is repeated, or has another size than the manifest states.
        """
        expected = self.size_bytes_by_path.get(path)
        if expected is None:
            raise ArchiveRefusedError(ArchiveProblem.MEMBER_NOT_ALLOWED)
        if member_type is not MemberType.REGULAR_FILE:
            raise ArchiveRefusedError(ArchiveProblem.MEMBER_NOT_A_REGULAR_FILE, path)
        if path in seen:
            raise ArchiveRefusedError(ArchiveProblem.MEMBER_REPEATED, path)
        if size_bytes != expected:
            raise ArchiveRefusedError(ArchiveProblem.MEMBER_SIZE_DIFFERS, path)

    def check_complete(self, seen: frozenset[str]) -> None:
        """Check that every allowed member was read.

        Args:
            seen: The members read.

        Raises:
            ArchiveRefusedError: A member is missing; the message names the first one by path.
        """
        missing = sorted(self.size_bytes_by_path.keys() - seen)
        if missing:
            raise ArchiveRefusedError(ArchiveProblem.MEMBER_MISSING, missing[0])

    def check_free_space(self, archive_size_bytes: int, free_bytes: int) -> None:
        """Check that the cache can hold the archive and every file it holds at once.

        Args:
            archive_size_bytes: The size of the archive.
            free_bytes: The free bytes of the file system of the cache.

        Raises:
            NotEnoughSpaceError: The archive and its files need more than the free space.
        """
        needed = archive_size_bytes + sum(self.size_bytes_by_path.values())
        if needed > free_bytes:
            raise NotEnoughSpaceError(needed, free_bytes)


def archive_name(release_id: str) -> str:
    """Return the name of the archive of a release, which is also the name of its asset.

    Args:
        release_id: The release ID.

    Returns:
        `<release_id>.tar.gz`.
    """
    return f"{release_id}{_ARCHIVE_SUFFIX}"


def mebibytes(size_bytes: int) -> int:
    """Return a size in whole mebibytes, rounded up, for a message.

    Args:
        size_bytes: The size.

    Returns:
        The size in MiB, rounded up.
    """
    return -(-size_bytes // _BYTES_PER_MIB)


def archive_contents(manifest_size_bytes: int, files: Mapping[str, int]) -> ArchiveContents:
    """Return the members of an archive: the manifest and every file it names.

    Args:
        manifest_size_bytes: The size of the manifest in git.
        files: The size of each file of the manifest, by its path.

    Returns:
        The allowed members with their sizes.
    """
    return ArchiveContents(size_bytes_by_path={**files, MANIFEST_FILE_NAME: manifest_size_bytes})

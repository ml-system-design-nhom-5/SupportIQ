"""Write the archive of a release, and unpack an archive safely into a staging folder.

`write_archive` gives the same bytes for the same files with the same versions of Python and
zlib: members sorted by path, in the ustar format, each a regular file with mode 0644, owner and
group 0, empty owner names, and modification time 0, in a gzip stream with modification time 0,
no file name, and level 9 (ADR-0030, Release archives, statement 2).

`unpack_archive` treats the archive as untrusted. It reads the members in order, checks each one
against the manifest in git before any byte is written, streams it into a new file created with
`O_EXCL` and without following a link, and never calls `extractall`. Files get mode 0644 and
folders 0755 whatever the umask, so a server under another user can read them.
"""

import gzip
import os
import tarfile
import zlib
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import IO

from supportiq_release.distribution.domain import (
    ArchiveContents,
    ArchiveProblem,
    ArchiveRefusedError,
    MemberType,
)
from supportiq_release.errors import ReleaseCommandError

FILE_MODE = 0o644
FOLDER_MODE = 0o755
_COMPRESS_LEVEL = 9
_CHUNK_BYTES = 1024 * 1024
_NEW_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


class PackProblem(StrEnum):
    """Why an archive cannot be written."""

    MANIFEST_DIFFERS_FROM_GIT = "release_folder_manifest_differs_from_git"
    PATH_TOO_LONG = "path_longer_than_the_ustar_format_allows"


class PackRefusedError(ReleaseCommandError):
    """An archive cannot be written. The message names the problem only."""

    def __init__(self, problem: PackProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the archive cannot be written.
        """
        super().__init__(f"The archive is not written: {problem}.")
        self.problem = problem


def write_archive(folder: Path, paths: Iterable[str], archive: Path) -> int:
    """Write the archive of a release folder into a new file.

    Args:
        folder: The release folder, already checked with `verify_release`.
        paths: The manifest and every file it names, by their paths in the folder.
        archive: The new archive file. An existing file is never overwritten.

    Returns:
        The size of the archive.

    Raises:
        PackRefusedError: A path is longer than the ustar format allows.
        OSError: A file cannot be read, or the archive cannot be written.
    """
    with (
        archive.open("xb") as raw,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, compresslevel=_COMPRESS_LEVEL, mtime=0
        ) as stream,
        tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as tar,
    ):
        for path in sorted(paths):
            _add_member(tar, folder / path, path)
    return archive.stat().st_size


def unpack_archive(archive: Path, contents: ArchiveContents, staging: Path) -> None:
    """Unpack an untrusted archive into an empty staging folder, checking every member.

    Args:
        archive: The downloaded archive.
        contents: The members that the manifest in git allows, with their sizes.
        staging: The empty staging folder.

    Raises:
        ArchiveRefusedError: The archive cannot be read, or a member is not allowed, not a
            regular file, repeated, of another size, or missing.
        OSError: A file cannot be written.
    """
    staging.chmod(FOLDER_MODE)
    seen: frozenset[str] = frozenset()
    try:
        with tarfile.open(archive, mode="r|gz") as tar:
            for member in tar:
                member_type = MemberType.REGULAR_FILE if member.isreg() else MemberType.OTHER
                contents.check_member(member.name, member_type, member.size, seen)
                seen |= {member.name}
                _write_member(tar, member, staging)
    except (tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as error:
        raise ArchiveRefusedError(ArchiveProblem.UNREADABLE) from error
    contents.check_complete(seen)


def _add_member(tar: tarfile.TarFile, source: Path, path: str) -> None:
    info = tarfile.TarInfo(path)
    info.size = source.stat().st_size
    info.mode = FILE_MODE
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.type = tarfile.REGTYPE
    try:
        with source.open("rb") as content:
            tar.addfile(info, content)
    except ValueError as error:
        # tarfile refuses a name that the ustar format cannot hold.
        raise PackRefusedError(PackProblem.PATH_TOO_LONG) from error


def _write_member(tar: tarfile.TarFile, member: tarfile.TarInfo, staging: Path) -> None:
    content = tar.extractfile(member)
    if content is None:
        raise ArchiveRefusedError(ArchiveProblem.MEMBER_NOT_A_REGULAR_FILE, member.name)
    target = _new_parents(staging, PurePosixPath(member.name))
    descriptor = os.open(target, _NEW_FILE_FLAGS, FILE_MODE)
    with os.fdopen(descriptor, "wb") as file:
        os.fchmod(file.fileno(), FILE_MODE)
        written = _copy(content, file)
    if written != member.size:
        raise ArchiveRefusedError(ArchiveProblem.MEMBER_SIZE_DIFFERS, member.name)


def _new_parents(staging: Path, path: PurePosixPath) -> Path:
    # The path is one of the manifest in git, so its segments hold no `.` or `..` and no link
    # can exist below the staging folder: every folder is made here.
    folder = staging
    for segment in path.parts[:-1]:
        folder /= segment
        if not folder.is_dir():
            folder.mkdir()
            folder.chmod(FOLDER_MODE)
    return folder / path.name


def _copy(content: IO[bytes], file: IO[bytes]) -> int:
    written = 0
    while chunk := content.read(_CHUNK_BYTES):
        file.write(chunk)
        written += len(chunk)
    return written

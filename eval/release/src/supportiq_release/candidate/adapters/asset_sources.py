"""Copy the sources of the six assets into the release folder, as real files only.

A release holds only regular files and folders, and `ai-service` refuses any symbolic link in
it (`ai-service/README.md`, Release manifest). So every source is checked before any byte is
copied: a source that is a link, or a link anywhere inside a folder source, even one that
points inside it, stops the build. So does any entry that is not a regular file or a folder,
a hidden entry such as `.DS_Store`, which would change what the release serves, and a folder
that cannot be listed, whose files would otherwise be left out without a word. A folder in the
cache of Hugging Face holds only links to its blobs, so it is refused with a message that asks
for the real files.

Each file is copied byte for byte into a file that did not exist, and its SHA-256 is computed
from the bytes that were written.
"""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from supportiq_release.candidate.domain import AssetName, AssetSpec, ReleaseSpec, is_release_path
from supportiq_release.errors import ReleaseCommandError

# A copy reads 1 MiB at a time, so a large file of weights never sits in memory whole.
_CHUNK_BYTES = 1024 * 1024


class SourceProblem(StrEnum):
    """Why the source of an asset cannot be copied."""

    MISSING = "missing"
    LINK = "symbolic_link"
    NOT_REGULAR = "not_a_regular_file_or_folder"
    HIDDEN = "hidden_entry"
    UNREADABLE = "unreadable"
    EMPTY_FOLDER = "empty_folder"
    NAME_INVALID = "file_name_not_allowed_in_a_release"
    FILE_EXPECTED = "one_file_expected"
    VERSION_MISMATCH = "version_not_that_of_the_spec"


_HINTS = {
    SourceProblem.LINK: (
        " Copy the real files first: a folder of the Hugging Face cache holds only links."
    ),
}


class SourceInvalidError(ReleaseCommandError):
    """A source cannot be copied. The message names the problem and the asset only."""

    def __init__(self, problem: SourceProblem, asset: AssetName) -> None:
        """Build the error with a message that names the problem and the asset.

        Args:
            problem: Why the source is refused.
            asset: The asset whose source it is.
        """
        super().__init__(
            f"The source of asset {asset} is refused: {problem}.{_HINTS.get(problem, '')}"
        )
        self.problem = problem
        self.asset = asset


@dataclass(frozen=True, slots=True)
class PlannedCopy:
    """One file to copy.

    Attributes:
        asset: The asset of the file.
        source: The file to copy.
        path: Its path in the release folder.
    """

    asset: AssetName
    source: Path
    path: str


@dataclass(frozen=True, slots=True)
class CopiedFile:
    """One file of the release, copied.

    Attributes:
        asset: The asset of the file.
        path: Its path in the release folder.
        sha256: The SHA-256 of its bytes, in lowercase hexadecimal.
        size_bytes: Its size.
    """

    asset: AssetName
    path: str
    sha256: str
    size_bytes: int


def plan_copies(spec: ReleaseSpec, base: Path) -> tuple[PlannedCopy, ...]:
    """Check every source and list the files to copy, before anything is written.

    Args:
        spec: The checked spec.
        base: The folder that the sources are relative to.

    Returns:
        Every file to copy, ordered by its path in the release folder.

    Raises:
        SourceInvalidError: A source is missing, is or holds a link, a hidden entry, or
            another kind of entry, is an empty folder or a folder that cannot be listed, or
            holds a file name that a release cannot hold.
    """
    planned = [copy for asset in spec.assets for copy in _asset_copies(asset, base / asset.source)]
    return tuple(sorted(planned, key=lambda copy: copy.path))


def copy_files(planned: tuple[PlannedCopy, ...], folder: Path) -> tuple[CopiedFile, ...]:
    """Copy each planned file into the release folder, never over an existing file.

    Args:
        planned: The files to copy.
        folder: The release folder, new and empty.

    Returns:
        The copied files, in the order of the plan.

    Raises:
        SourceInvalidError: A source file cannot be read.
        OSError: A file of the release cannot be written, or exists.
    """
    return tuple(_copy(copy, folder / copy.path) for copy in planned)


def _asset_copies(asset: AssetSpec, source: Path) -> list[PlannedCopy]:
    if source.is_symlink():
        raise SourceInvalidError(SourceProblem.LINK, asset.name)
    if source.is_file():
        return [PlannedCopy(asset=asset.name, source=source, path=asset.path)]
    if not source.is_dir():
        problem = SourceProblem.NOT_REGULAR if source.exists() else SourceProblem.MISSING
        raise SourceInvalidError(problem, asset.name)
    copies = [
        PlannedCopy(asset=asset.name, source=file, path=f"{asset.path}/{relative}")
        for file, relative in _folder_files(asset.name, source)
    ]
    if not copies:
        raise SourceInvalidError(SourceProblem.EMPTY_FOLDER, asset.name)
    if not all(is_release_path(copy.path) for copy in copies):
        raise SourceInvalidError(SourceProblem.NAME_INVALID, asset.name)
    return copies


def _folder_files(asset: AssetName, folder: Path) -> list[tuple[Path, str]]:
    # `Path.walk` does not follow links, and every entry is checked before it is listed.
    def refuse_unreadable_folder(error: OSError) -> None:
        # Otherwise the walk would skip that folder, and every entry in it, without a word.
        raise SourceInvalidError(SourceProblem.UNREADABLE, asset) from error

    files: list[tuple[Path, str]] = []
    for current, folder_names, file_names in folder.walk(on_error=refuse_unreadable_folder):
        for name in (*folder_names, *file_names):
            _check_entry(asset, current / name)
        for name in file_names:
            entry = current / name
            if not entry.is_file():
                raise SourceInvalidError(SourceProblem.NOT_REGULAR, asset)
            files.append((entry, entry.relative_to(folder).as_posix()))
    return files


def _check_entry(asset: AssetName, entry: Path) -> None:
    if entry.is_symlink():
        raise SourceInvalidError(SourceProblem.LINK, asset)
    if entry.name.startswith("."):
        raise SourceInvalidError(SourceProblem.HIDDEN, asset)


def _copy(copy: PlannedCopy, target: Path) -> CopiedFile:
    digest = hashlib.sha256()
    size = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as writer:
        for chunk in _chunks(copy):
            digest.update(chunk)
            writer.write(chunk)
            size += len(chunk)
    return CopiedFile(asset=copy.asset, path=copy.path, sha256=digest.hexdigest(), size_bytes=size)


def _chunks(copy: PlannedCopy) -> Iterator[bytes]:
    # A failure to open or to read the source is the source's; a failure to write is the
    # output's, and reaches the caller as an `OSError`.
    try:
        with copy.source.open("rb") as reader:
            while chunk := reader.read(_CHUNK_BYTES):
                yield chunk
    except OSError as error:
        raise SourceInvalidError(SourceProblem.UNREADABLE, copy.asset) from error

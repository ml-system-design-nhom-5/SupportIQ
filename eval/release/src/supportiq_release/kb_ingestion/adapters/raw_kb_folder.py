"""Read a raw KB folder, `data/raw/kb/<kb_version>/`, only to read it (DATA-06).

The folder holds the release file of the KB holder, `kb-release.json`, and the KB file that its
`source` names, both kept byte for byte (ADR-0021, KB ingestion, statement 1). The folder is
opened for reading only, and the SHA-256 of each file goes into the report, so a change of the
raw KB shows (DATA-12).

A release file or a KB file that breaks its shape stops the run: ingestion quarantines records,
never the files that list them.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import JsonFile, read_json_file
from supportiq_release.kb_ingestion.domain import KB_IDENTIFIER_PATTERN, DocumentVersionKey, RawKb

RELEASE_FILE_NAME = "kb-release.json"
_RELEASE_FIELDS = frozenset({"release", "source", "documents"})
_RELEASED_VERSION_FIELDS = frozenset({"document_id", "version"})
# A plain file name of at most 100 characters, so the `source` of a version fits the contract.
_KB_FILE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


class KbFolderProblem(StrEnum):
    """Why a raw KB folder is refused."""

    FOLDER_NAME_INVALID = "folder_name_invalid"
    RELEASE_FILE_INVALID = "release_file_invalid"
    KB_FILE_INVALID = "kb_file_invalid"


class KbFolderInvalidError(ReleaseCommandError):
    """A raw KB folder cannot be ingested. The message names the problem, never content."""

    def __init__(self, problem: KbFolderProblem) -> None:
        """Build the error with a message that names only the problem.

        Args:
            problem: Why the folder is refused.
        """
        super().__init__(f"The raw KB folder is refused: {problem}.")
        self.problem = problem


@dataclass(frozen=True, slots=True)
class InputFile:
    """One file of the raw KB folder, as the report names it.

    Attributes:
        name: The name of the file.
        sha256: The SHA-256 of its bytes, in lowercase hexadecimal.
    """

    name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RawKbFolder:
    """A raw KB folder, read.

    Attributes:
        kb: What ingestion checks.
        kb_release: The name of the release of the KB holder, such as `current-policies-v1`.
        inputs: The release file and the KB file, in that order.
    """

    kb: RawKb
    kb_release: str
    inputs: tuple[InputFile, InputFile]


def content_sha256(text: str) -> str:
    """Return the SHA-256 of a text in UTF-8, as the field `content_hash` declares it.

    Args:
        text: A text that UTF-8 can hold.

    Returns:
        The checksum, in lowercase hexadecimal.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_raw_kb_folder(folder: Path) -> RawKbFolder:
    """Read the release file and the KB file of a raw KB folder.

    Args:
        folder: The folder, whose name is the KB version.

    Returns:
        The folder, read.

    Raises:
        KbFolderInvalidError: The folder name is not a KB identifier, or a file breaks its
            shape.
        JsonFileInvalidError: A file is missing, a link, unreadable, or not strict JSON in
            UTF-8.
    """
    if KB_IDENTIFIER_PATTERN.fullmatch(folder.name) is None:
        raise KbFolderInvalidError(KbFolderProblem.FOLDER_NAME_INVALID)
    release_file = read_json_file(folder / RELEASE_FILE_NAME)
    release = _release_object(release_file.content)
    kb_file_name = _kb_file_name(release["source"])
    kb_file = read_json_file(folder / kb_file_name)
    return RawKbFolder(
        kb=RawKb(
            kb_version=folder.name,
            kb_file_name=kb_file_name,
            released=_released_versions(release["documents"]),
            records=_records(kb_file),
        ),
        kb_release=_identifier(release["release"]),
        inputs=(
            InputFile(release_file.name, release_file.sha256),
            InputFile(kb_file.name, kb_file.sha256),
        ),
    )


# Each cast below only names the type that `isinstance` found in a JSON value (PY-12).
def _release_object(content: object) -> Mapping[str, object]:
    release = cast("dict[str, object]", content) if isinstance(content, dict) else None
    if release is None or frozenset(release) != _RELEASE_FIELDS:
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    return release


def _kb_file_name(source: object) -> str:
    # The release file names the KB file by its path on `main`; the file is in the same folder.
    # A path that ends with `/` names a folder.
    if not isinstance(source, str) or source.endswith("/"):
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    name = PurePosixPath(source).name
    if _KB_FILE_NAME_PATTERN.fullmatch(name) is None or name == RELEASE_FILE_NAME:
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    return name


def _identifier(value: object) -> str:
    if not isinstance(value, str) or KB_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    return value


def _released_versions(documents: object) -> frozenset[DocumentVersionKey]:
    entries = cast("list[object]", documents) if isinstance(documents, list) else None
    if entries is None:
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    keys = [_released_version(entry) for entry in entries]
    if len(set(keys)) != len(keys):
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    return frozenset(keys)


def _released_version(entry: object) -> DocumentVersionKey:
    fields = cast("dict[str, object]", entry) if isinstance(entry, dict) else None
    if fields is None or frozenset(fields) != _RELEASED_VERSION_FIELDS:
        raise KbFolderInvalidError(KbFolderProblem.RELEASE_FILE_INVALID)
    return (_identifier(fields["document_id"]), _identifier(fields["version"]))


def _records(kb_file: JsonFile) -> tuple[Mapping[str, object], ...]:
    content = kb_file.content
    entries = cast("list[object]", content) if isinstance(content, list) else None
    if entries is None or not all(isinstance(entry, dict) for entry in entries):
        raise KbFolderInvalidError(KbFolderProblem.KB_FILE_INVALID)
    return tuple(cast("dict[str, object]", entry) for entry in entries)

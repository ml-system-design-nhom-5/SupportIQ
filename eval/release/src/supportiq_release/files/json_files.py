"""Read and write the JSON files of the release command, strictly and the same way every time."""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from supportiq_release.errors import ReleaseCommandError


class JsonFileProblem(StrEnum):
    """Why a JSON file cannot be read."""

    NOT_A_REGULAR_FILE = "missing_or_not_a_regular_file"
    UNREADABLE = "unreadable"
    NOT_STRICT_JSON = "not_strict_json_in_utf8"


class JsonFileInvalidError(ReleaseCommandError):
    """A JSON file cannot be read. The message names the file and the problem, never content."""

    def __init__(self, file_name: str, problem: JsonFileProblem) -> None:
        """Build the error with a message that names only the file and the problem.

        Args:
            file_name: The name of the file.
            problem: Why the file cannot be read.
        """
        super().__init__(f"The file {file_name} is refused: {problem}.")
        self.file_name = file_name
        self.problem = problem


@dataclass(frozen=True, slots=True)
class JsonFile:
    """The content of a JSON file, and the SHA-256 of its bytes.

    Attributes:
        name: The name of the file.
        sha256: The SHA-256 of its bytes, in lowercase hexadecimal.
        content: The decoded JSON value.
    """

    name: str
    sha256: str
    content: object


def read_json_file(path: Path) -> JsonFile:
    """Read a regular JSON file, and refuse a duplicate key or a value that is not JSON.

    Args:
        path: The file. A symbolic link is refused, so the checksum is that of the named file.

    Returns:
        The content and the checksum.

    Raises:
        JsonFileInvalidError: The file is missing, a link, unreadable, not UTF-8, or not
            strict JSON.
    """
    if path.is_symlink() or not path.is_file():
        raise JsonFileInvalidError(path.name, JsonFileProblem.NOT_A_REGULAR_FILE)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise JsonFileInvalidError(path.name, JsonFileProblem.UNREADABLE) from error
    try:
        content: object = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_without_duplicate_keys,
            parse_constant=_refuse_constant,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise JsonFileInvalidError(path.name, JsonFileProblem.NOT_STRICT_JSON) from error
    return JsonFile(name=path.name, sha256=hashlib.sha256(data).hexdigest(), content=content)


def write_json_file(path: Path, document: object) -> None:
    """Write a JSON document with two-space indents, in UTF-8, with LF and a final newline.

    The text is encoded before the file is opened, so a value that UTF-8 cannot hold leaves no
    file behind.

    Args:
        path: The new file. An existing file is never overwritten.
        document: The document.

    Raises:
        FileExistsError: The file exists.
        OSError: The file cannot be written.
    """
    data = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("xb") as file:
        file.write(data)


def _without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    # The standard library keeps the last of two equal keys; a strict file has none.
    document = dict(pairs)
    if len(document) != len(pairs):
        message = "duplicate key"
        raise ValueError(message)
    return document


def _refuse_constant(name: str) -> object:
    # NaN and the infinities are not JSON.
    message = f"not JSON: {name}"
    raise ValueError(message)

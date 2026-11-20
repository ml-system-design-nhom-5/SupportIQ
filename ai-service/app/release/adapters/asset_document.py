"""The files of each asset of a verified release, and the strict reading of those files.

After every checksum of a release matched (DATA-56), `VerifiedReleaseSource.asset_files`
hands the files of one asset to the adapter that reads it. Each adapter reads its interim
format with the types of this module. A file that breaks its format stops startup with the
reason `asset_invalid`, the asset, and the path, never the content of the file (ERR-17). A
data contract in `contracts/` replaces these interim formats (ADR-0021, Follow-ups).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    PlainValidator,
    StringConstraints,
    ValidationError,
)

from app.platform import TIMESTAMP_PATTERN
from app.release.domain import ReleaseInvalidError, ReleaseInvalidReason

# The six assets of a release, as the manifest names them (DATA-56).
type AssetName = Literal["model", "kb", "mapping", "prompts", "routing", "index"]

# The pattern of `AssetVersion` in the contract, so every version of a release can be served
# as it is (contracts/schemas/AssetVersion.yaml).
_ASSET_VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
# A relative POSIX path: segments of letters, digits, `.`, `_`, and `-`, so no absolute path,
# no backslash, and no empty segment fits. `_has_no_dot_segment` refuses `.` and `..`.
_RELATIVE_PATH_PATTERN = r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$"
_RELATIVE_PATH_MAX_LENGTH = 255
_DOT_SEGMENTS = frozenset({".", ".."})


def _has_no_dot_segment(path: str) -> str:
    # Split by hand: `PurePosixPath` drops `.` segments, so it would hide them.
    if any(segment in _DOT_SEGMENTS for segment in path.split("/")):
        message = "a path has no `.` or `..` segment"
        raise ValueError(message)
    return path


def _read_timestamp(value: object) -> datetime:
    # A plain validator, because Pydantic cannot apply a pattern to a datetime.
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        message = "a timestamp is RFC 3339 in UTC with `Z`"
        raise ValueError(message)
    return datetime.fromisoformat(value)


AssetVersionText = Annotated[str, StringConstraints(pattern=_ASSET_VERSION_PATTERN)]
Sha256 = Annotated[str, StringConstraints(pattern=_SHA256_PATTERN)]
RelativePath = Annotated[
    str,
    StringConstraints(max_length=_RELATIVE_PATH_MAX_LENGTH, pattern=_RELATIVE_PATH_PATTERN),
    AfterValidator(_has_no_dot_segment),
]
# A contract `Timestamp`, read as a timezone-aware time in UTC.
UtcTimestamp = Annotated[datetime, PlainValidator(_read_timestamp)]


class StrictDocument(BaseModel):
    """A part of a file of a release: read strictly, every other field refused."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


@dataclass(frozen=True, slots=True)
class AssetFile:
    """One file of an asset, whose size and SHA-256 matched the manifest.

    Attributes:
        asset: The asset that the file belongs to.
        file_path: Its path inside the release folder, as the manifest names it.
        location: Where it is on disk.
    """

    asset: AssetName
    file_path: str
    location: Path

    def invalid(self) -> ReleaseInvalidError:
        """Return the refusal of this file.

        Returns:
            The error that names the asset and the path of the file, never its content.
        """
        return ReleaseInvalidError(
            ReleaseInvalidReason.ASSET_INVALID, asset=self.asset, file_path=self.file_path
        )


@dataclass(frozen=True, slots=True)
class AssetFiles:
    """Every file of one asset of a verified release.

    Attributes:
        asset: The asset.
        version: Its version in the manifest.
        folder: The release folder.
        files: Its files, in the order of the manifest.
        other_file_paths: The paths of the files of every other asset.
    """

    asset: AssetName
    version: str
    folder: Path
    files: tuple[AssetFile, ...]
    other_file_paths: frozenset[str]

    def file(self, file_path: str) -> AssetFile:
        """Return the file of this path.

        Args:
            file_path: The path inside the release folder.

        Returns:
            The file.

        Raises:
            ReleaseInvalidError: The asset has no file of this path.
        """
        for asset_file in self.files:
            if asset_file.file_path == file_path:
                return asset_file
        raise self.invalid(file_path)

    def sole(self) -> AssetFile:
        """Return the file of an asset that holds exactly one file.

        Returns:
            The file.

        Raises:
            ReleaseInvalidError: The asset holds more than one file.
        """
        if len(self.files) != 1:
            raise self.invalid()
        return self.files[0]

    def named(self, name: str) -> AssetFile:
        """Return the one file of this name, in any folder of the asset.

        Args:
            name: The name of the file, without its folder.

        Returns:
            The file.

        Raises:
            ReleaseInvalidError: The asset holds no file of this name, or several.
        """
        matches = [
            asset_file
            for asset_file in self.files
            if PurePosixPath(asset_file.file_path).name == name
        ]
        if len(matches) != 1:
            raise self.invalid()
        return matches[0]

    def directory(self, directory_path: str) -> Path:
        """Return a folder that holds files of this asset and no file of another asset.

        A model library reads a whole folder, so the folder of a model holds only the files of
        its asset (ADR-0018, decision driver 2).

        Args:
            directory_path: The path of the folder inside the release folder.

        Returns:
            Where the folder is on disk.

        Raises:
            ReleaseInvalidError: The folder holds no file of this asset, or a file of another.
        """
        prefix = f"{directory_path}/"
        holds_this_asset = any(asset_file.file_path.startswith(prefix) for asset_file in self.files)
        holds_another_asset = any(path.startswith(prefix) for path in self.other_file_paths)
        if not holds_this_asset or holds_another_asset:
            raise self.invalid(directory_path)
        return self.folder / directory_path

    def invalid(self, file_path: str | None = None) -> ReleaseInvalidError:
        """Return the refusal of this asset.

        Args:
            file_path: The path that the asset lacks or that breaks its format, when one does.

        Returns:
            The error that names the asset and the path, never the content of a file.
        """
        return ReleaseInvalidError(
            ReleaseInvalidReason.ASSET_INVALID, asset=self.asset, file_path=file_path
        )


def read_json_asset[DocumentT: BaseModel](
    asset_file: AssetFile, document: type[DocumentT]
) -> DocumentT:
    """Read a JSON file of an asset with the model of its format.

    Args:
        asset_file: The file.
        document: The model of the format.

    Returns:
        The content of the file.

    Raises:
        ReleaseInvalidError: The file is unreadable, is not JSON in UTF-8, or breaks the
            format.
    """
    try:
        return document.model_validate_json(asset_file.location.read_bytes())
    except (OSError, ValidationError) as error:
        raise asset_file.invalid() from error


def read_text_asset(asset_file: AssetFile) -> str:
    """Read a text file of an asset: UTF-8, with at least one character other than a space.

    Args:
        asset_file: The file.

    Returns:
        The text, as the file holds it.

    Raises:
        ReleaseInvalidError: The file is unreadable, is not UTF-8, or holds only spaces.
    """
    try:
        text = asset_file.location.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise asset_file.invalid() from error
    if not text.strip():
        raise asset_file.invalid()
    return text

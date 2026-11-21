"""What a candidate release is built from, and the rules that its layout follows.

A release is one folder: the manifest and every file of the six assets, by a path relative to
that folder (`ai-service/README.md`, Release manifest). The spec names, for each asset, its
version, its source, and its path in the release. The patterns are those of the contract and
of `ai-service`, so a spec that breaks one is refused before any file is copied.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.errors import ReleaseCommandError


class AssetName(StrEnum):
    """The six assets of a release, in the order of the manifest (DATA-56)."""

    MODEL = "model"
    KB = "kb"
    MAPPING = "mapping"
    PROMPTS = "prompts"
    ROUTING = "routing"
    INDEX = "index"


ASSET_NAMES = tuple(AssetName)
MANIFEST_FILE_NAME = "release-manifest.json"
# The pattern of `release_id` in the contract (`contracts/schemas/AssetVersions.yaml`).
RELEASE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# The pattern of `AssetVersion` in the contract (`contracts/schemas/AssetVersion.yaml`).
ASSET_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}")
# A path of a release file, as `ai-service` reads it: segments of letters, digits, `.`, `_`, and
# `-`, at most 255 characters, and no `.` or `..` segment (`release/adapters/asset_document.py`).
_RELEASE_PATH_PATTERN = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")
_RELEASE_PATH_MAX_LENGTH = 255
_DOT_SEGMENTS = frozenset({".", ".."})


@dataclass(frozen=True, slots=True)
class AssetSpec:
    """One asset of the candidate.

    Attributes:
        name: The asset.
        version: The version that results report.
        source: The file or folder to copy: absolute, or relative to the folder of the spec.
        path: Where the asset goes in the release folder: a file path for a file, a folder
            path for a folder.
        model_version: For `routing` only, the model version it was tuned for (DATA-58).
    """

    name: AssetName
    version: str
    source: str
    path: str
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseSpec:
    """The candidate release to build.

    Attributes:
        release_id: The identifier of the release, never reused (ARCH-40).
        assets: The six assets, in the order of `ASSET_NAMES`.
    """

    release_id: str
    assets: tuple[AssetSpec, ...]


class SpecProblem(StrEnum):
    """Why a spec is refused."""

    SHAPE_INVALID = "shape_invalid"
    RELEASE_ID_INVALID = "release_id_invalid"
    ASSET_VERSION_INVALID = "asset_version_invalid"
    PATH_INVALID = "path_invalid"
    PATHS_OVERLAP = "paths_overlap"
    ROUTING_MODEL_MISMATCH = "routing_model_mismatch"


class SpecInvalidError(ReleaseCommandError):
    """A spec cannot build a candidate. The message names the problem and the asset only."""

    def __init__(self, problem: SpecProblem, asset: AssetName | None = None) -> None:
        """Build the error with a message that names the problem and the asset.

        Args:
            problem: Why the spec is refused.
            asset: The asset that the problem is about, if any.
        """
        about = "" if asset is None else f", asset {asset}"
        super().__init__(f"The release spec is refused: {problem}{about}.")
        self.problem = problem
        self.asset = asset


def is_release_path(path: str) -> bool:
    """Return whether `ai-service` accepts a path of a file of the release.

    Args:
        path: The path, relative to the release folder.

    Returns:
        True when the path fits the pattern, the length, and has no `.` or `..` segment.
    """
    return (
        len(path) <= _RELEASE_PATH_MAX_LENGTH
        and _RELEASE_PATH_PATTERN.fullmatch(path) is not None
        and not _DOT_SEGMENTS.intersection(path.split("/"))
    )


def check_spec(spec: ReleaseSpec) -> None:
    """Refuse a spec whose identifiers, versions, or paths `ai-service` would refuse.

    Args:
        spec: The spec, with its six assets in the order of `ASSET_NAMES`.

    Raises:
        SpecInvalidError: The release ID or a version breaks its pattern, a path is not a
            release path, two paths overlap or one is the manifest, or the routing
            configuration names another model version (DATA-58).
    """
    if RELEASE_ID_PATTERN.fullmatch(spec.release_id) is None:
        raise SpecInvalidError(SpecProblem.RELEASE_ID_INVALID)
    for asset in spec.assets:
        versions = (
            (asset.version,)
            if asset.model_version is None
            else (asset.version, asset.model_version)
        )
        if any(ASSET_VERSION_PATTERN.fullmatch(version) is None for version in versions):
            raise SpecInvalidError(SpecProblem.ASSET_VERSION_INVALID, asset.name)
        if not is_release_path(asset.path):
            raise SpecInvalidError(SpecProblem.PATH_INVALID, asset.name)
    _refuse_overlaps(spec.assets)
    by_name = {asset.name: asset for asset in spec.assets}
    if by_name[AssetName.ROUTING].model_version != by_name[AssetName.MODEL].version:
        raise SpecInvalidError(SpecProblem.ROUTING_MODEL_MISMATCH, AssetName.ROUTING)


def _refuse_overlaps(assets: tuple[AssetSpec, ...]) -> None:
    # No asset goes inside another, and none takes the place of the manifest. The paths are
    # compared without case, because the file system of macOS does not tell `kb` from `KB`.
    taken = [
        (MANIFEST_FILE_NAME, None),
        *((asset.path.casefold(), asset.name) for asset in assets),
    ]
    for index, (path, name) in enumerate(taken):
        for other, _ in taken[:index]:
            if path == other or path.startswith(f"{other}/") or other.startswith(f"{path}/"):
                raise SpecInvalidError(SpecProblem.PATHS_OVERLAP, name)

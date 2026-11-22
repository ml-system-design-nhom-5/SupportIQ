"""The rules of a candidate release, with no file access (ARCH-11)."""

from supportiq_release.candidate.domain.spec import (
    ASSET_NAMES,
    MANIFEST_FILE_NAME,
    RELEASE_ID_PATTERN,
    AssetName,
    AssetSpec,
    ReleaseSpec,
    SpecInvalidError,
    SpecProblem,
    check_spec,
    is_release_path,
)

__all__ = [
    "ASSET_NAMES",
    "MANIFEST_FILE_NAME",
    "RELEASE_ID_PATTERN",
    "AssetName",
    "AssetSpec",
    "ReleaseSpec",
    "SpecInvalidError",
    "SpecProblem",
    "check_spec",
    "is_release_path",
]

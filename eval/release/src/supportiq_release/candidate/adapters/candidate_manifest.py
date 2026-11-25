"""Write the manifest of a candidate release, and check it as `ai-service` checks a release.

The manifest follows `supportiq-release-manifest/interim-1`, the interim format that
`app.release.manifest` defines and checks (`ai-service/README.md`, Release
manifest). This module imports that module and no other module of `ai-service` (ADR-0021,
Where the code of `main` goes, statement 1). The candidate has `"gate_run": null`: only the
offline evaluation gate links a passing run (DATA-57).
"""

from pathlib import Path

from app.release.manifest import MANIFEST_FORMAT, verify_candidate

from supportiq_release.candidate.adapters.asset_sources import CopiedFile
from supportiq_release.candidate.domain import MANIFEST_FILE_NAME, AssetSpec, ReleaseSpec
from supportiq_release.files import write_json_file


def write_candidate_manifest(
    folder: Path, spec: ReleaseSpec, files: tuple[CopiedFile, ...]
) -> Path:
    """Write the manifest of the copied files, then check the whole candidate.

    Args:
        folder: The release folder, which holds every copied file and nothing else.
        spec: The spec of the candidate.
        files: The copied files.

    Returns:
        The manifest file.

    Raises:
        ReleaseInvalidError: `ai-service` refuses the candidate, for a reason other than its
            missing gate run. The check covers the manifest, the links, the sizes, and the
            checksums, not the formats of the assets.
        OSError: The manifest cannot be written.
    """
    manifest = folder / MANIFEST_FILE_NAME
    write_json_file(
        manifest,
        {
            "format": MANIFEST_FORMAT,
            "release_id": spec.release_id,
            "assets": {asset.name.value: _asset_entry(asset, files) for asset in spec.assets},
            "gate_run": None,
        },
    )
    verify_candidate(manifest)
    return manifest


def _asset_entry(asset: AssetSpec, files: tuple[CopiedFile, ...]) -> dict[str, object]:
    routing = {} if asset.model_version is None else {"model_version": asset.model_version}
    return {
        "version": asset.version,
        **routing,
        "files": [
            {"path": copied.path, "sha256": copied.sha256, "size_bytes": copied.size_bytes}
            for copied in files
            if copied.asset == asset.name
        ],
    }

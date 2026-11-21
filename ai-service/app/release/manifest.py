"""The second public entry point of release: the interim format of the release manifest.

The composition root checks the release here before a replica serves it. `eval/` uses the
same names, and no internal module of `ai-service`, to write a candidate manifest, to check
it, and to run the offline evaluation gate on exactly that candidate (ADR-0021, Where the
code of `main` goes, statement 1). Domain and application code never import this module,
because it reads files and uses pydantic. A data contract in `contracts/` replaces the
format (ADR-0021, Follow-ups).
"""

from app.release.adapters.manifest_file import (
    MANIFEST_FORMAT,
    GateRun,
    ManifestAsset,
    ManifestAssets,
    ManifestFile,
    ReleaseManifest,
    RoutingAsset,
    VerifiedReleaseSource,
    read_release_manifest,
    verify_candidate,
    verify_release,
)
from app.release.domain import ReleaseInvalidError, ReleaseInvalidReason

__all__ = [
    "MANIFEST_FORMAT",
    "GateRun",
    "ManifestAsset",
    "ManifestAssets",
    "ManifestFile",
    "ReleaseInvalidError",
    "ReleaseInvalidReason",
    "ReleaseManifest",
    "RoutingAsset",
    "VerifiedReleaseSource",
    "read_release_manifest",
    "verify_candidate",
    "verify_release",
]

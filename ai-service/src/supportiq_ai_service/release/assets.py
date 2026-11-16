"""The third public entry point of release: the files of each asset of a verified release.

The adapter that reads an asset takes its files from `VerifiedReleaseSource.asset_files` and
reads its interim format with these names. Only adapters and the composition root import this
module, because it reads files and uses pydantic. A data contract in `contracts/` replaces the
interim formats (ADR-0021, Follow-ups).
"""

from supportiq_ai_service.release.adapters.asset_document import (
    AssetFile,
    AssetFiles,
    AssetName,
    AssetVersionText,
    RelativePath,
    Sha256,
    StrictDocument,
    UtcTimestamp,
    read_json_asset,
    read_text_asset,
)

__all__ = [
    "AssetFile",
    "AssetFiles",
    "AssetName",
    "AssetVersionText",
    "RelativePath",
    "Sha256",
    "StrictDocument",
    "UtcTimestamp",
    "read_json_asset",
    "read_text_asset",
]

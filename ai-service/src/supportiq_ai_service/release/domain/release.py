"""The loaded release, the port that tells whether one is loaded, and why one is refused.

ai-service serves exactly one release manifest at a time, loaded at startup (DATA-56). It
does not start with a manifest that is incomplete or whose files do not match it (ERR-17).
While no verified release is loaded, it serves no request that needs the release.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol

from supportiq_ai_service.platform import AiServiceError, ErrorCode


@dataclass(frozen=True, slots=True)
class AssetVersions:
    """The `release_id` of the loaded release manifest and the version of each asset it names.

    Attributes:
        release_id: The unique, immutable identifier of the release manifest.
        model_version: The version of the intent classification model artifact.
        kb_version: The version of the KB.
        mapping_version: The version of the document-to-intent mapping.
        prompt_version: The version of the set of prompts.
        routing_version: The version of the routing configuration.
        index_version: The version of the retrieval index.
    """

    release_id: str
    model_version: str
    kb_version: str
    mapping_version: str
    prompt_version: str
    routing_version: str
    index_version: str


@dataclass(frozen=True, slots=True)
class LoadedRelease:
    """A release manifest that was loaded and whose every checksum matched.

    Attributes:
        versions: The release and asset versions that every result names (DATA-56).
    """

    versions: AssetVersions


class ReleaseSource(Protocol):
    """Tell which release is loaded, if any."""

    def current(self) -> LoadedRelease | None:
        """Return the loaded release.

        Returns:
            The release, or None while no verified release manifest is loaded.
        """
        ...


class ReleaseNotLoadedError(AiServiceError):
    """No verified release manifest is loaded, so ai-service cannot serve the request."""

    code: ClassVar[ErrorCode] = ErrorCode.NOT_READY

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The release manifest is not loaded.")


class ReleaseInvalidReason(StrEnum):
    """Why a release manifest, or an entry of its folder, is refused (DATA-56)."""

    MANIFEST_UNREADABLE = "manifest_unreadable"
    MANIFEST_INVALID = "manifest_invalid"
    GATE_RUN_MISSING = "gate_run_missing"
    ROUTING_MODEL_MISMATCH = "routing_model_mismatch"
    FILE_OUTSIDE_RELEASE = "file_outside_release"
    FILE_UNREADABLE = "file_unreadable"
    LINK_IN_RELEASE = "link_in_release"
    FILE_UNLISTED = "file_unlisted"
    SIZE_MISMATCH = "size_mismatch"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    ASSET_INVALID = "asset_invalid"


class ReleaseInvalidError(AiServiceError):
    """A release manifest or one of its files is invalid, so ai-service does not start.

    It keeps the reason, the asset, and the path of the file inside the release, never the
    content of a file.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        reason: ReleaseInvalidReason,
        asset: str | None = None,
        file_path: str | None = None,
    ) -> None:
        """Build the error with a detail that names only the reason.

        Args:
            reason: Why the release is refused.
            asset: The asset of the manifest that is refused, when one is.
            file_path: The path of the refused file inside the release, when one is.
        """
        super().__init__(f"The release manifest is refused: {reason}.")
        self.reason = reason
        self.asset = asset
        self.file_path = file_path

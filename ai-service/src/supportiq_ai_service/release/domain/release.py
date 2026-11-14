"""The loaded release: its asset versions, and the port that tells whether one is loaded.

ai-service serves exactly one release manifest at a time, loaded at startup (DATA-56). Until
a manifest is loaded and every checksum matches, ai-service is not ready and serves no
request that needs the release.
"""

from dataclasses import dataclass
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

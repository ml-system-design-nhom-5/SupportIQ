"""In-memory fakes of the release ports (ARCH-27)."""

from dataclasses import dataclass

from app.release import AssetVersions, LoadedRelease

# The versions of `contracts/examples/getAssetVersions/loaded.json`.
EXAMPLE_VERSIONS = AssetVersions(
    release_id="release-2026-11-12-sample",
    model_version="intent-model-sample-1",
    kb_version="kb-sample-1",
    mapping_version="mapping-sample-1",
    prompt_version="prompts-sample-1",
    routing_version="routing-sample-1",
    index_version="index-sample-1",
)
EXAMPLE_RELEASE = LoadedRelease(versions=EXAMPLE_VERSIONS)


@dataclass(frozen=True, slots=True)
class StaticReleaseSource:
    """A release source whose loaded release a test chooses; None means not loaded."""

    release: LoadedRelease | None = EXAMPLE_RELEASE

    def current(self) -> LoadedRelease | None:
        """Return the chosen release."""
        return self.release


class FailingReleaseSource:
    """A release source that fails unexpectedly, as a defect would."""

    def current(self) -> LoadedRelease | None:
        """Raise the failure.

        Raises:
            RuntimeError: Always.
        """
        message = "release source failed"
        raise RuntimeError(message)

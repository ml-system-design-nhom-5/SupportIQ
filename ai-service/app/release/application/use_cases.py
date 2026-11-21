"""Use cases of release: the asset versions in use, and readiness (DATA-56, ERR-18)."""

from app.release.domain import (
    AssetVersions,
    LoadedRelease,
    ReleaseNotLoadedError,
    ReleaseSource,
)


def require_release(source: ReleaseSource) -> LoadedRelease:
    """Return the loaded release, or refuse the request.

    Args:
        source: Where the loaded release comes from.

    Returns:
        The loaded release.

    Raises:
        ReleaseNotLoadedError: No verified release manifest is loaded.
    """
    release = source.current()
    if release is None:
        raise ReleaseNotLoadedError
    return release


class GetAssetVersions:
    """Tell the release and asset versions in use (`getAssetVersions`)."""

    def __init__(self, source: ReleaseSource) -> None:
        """Keep the source of the loaded release.

        Args:
            source: Where the loaded release comes from.
        """
        self._source = source

    def execute(self) -> AssetVersions:
        """Return the versions of the loaded release.

        Returns:
            The `release_id` and the version of each asset.

        Raises:
            ReleaseNotLoadedError: No verified release manifest is loaded.
        """
        return require_release(self._source).versions


class ReleaseReadinessProbe:
    """Implement the `ReadinessProbe` port: ready only with a verified release loaded."""

    def __init__(self, source: ReleaseSource) -> None:
        """Keep the source of the loaded release.

        Args:
            source: Where the loaded release comes from.
        """
        self._source = source

    def check(self) -> None:
        """Check that a release is loaded.

        Raises:
            ReleaseNotLoadedError: No verified release manifest is loaded.
        """
        require_release(self._source)

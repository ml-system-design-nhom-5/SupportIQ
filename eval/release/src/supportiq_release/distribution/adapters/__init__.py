"""The files and requests of the release download: archive, cache, pinned file, and GitHub."""

from supportiq_release.distribution.adapters.github_releases import (
    GITHUB_API_ORIGIN,
    REPOSITORY,
    GitHubAccess,
    GitHubUnreachableError,
    NetworkProblem,
    TokenRefusedError,
    download_asset,
    look_up_assets,
)
from supportiq_release.distribution.adapters.pinned_release_file import (
    read_pinned_release,
    write_pinned_release,
)
from supportiq_release.distribution.adapters.published_manifest import (
    PublishedManifest,
    PublishedProblem,
    ReleaseNotPublishedError,
    read_published_manifest,
)
from supportiq_release.distribution.adapters.release_archive import (
    FILE_MODE,
    FOLDER_MODE,
    PackProblem,
    PackRefusedError,
    unpack_archive,
    write_archive,
)
from supportiq_release.distribution.adapters.release_cache import (
    CachedReleaseInvalidError,
    CachedReleaseProblem,
    ReleaseFilesRefusedError,
    check_cached_release,
    free_bytes,
    install_release,
    is_cached,
    new_partial_archive,
    release_folder,
)
from supportiq_release.distribution.adapters.terminal import can_answer, confirms

__all__ = [
    "FILE_MODE",
    "FOLDER_MODE",
    "GITHUB_API_ORIGIN",
    "REPOSITORY",
    "CachedReleaseInvalidError",
    "CachedReleaseProblem",
    "GitHubAccess",
    "GitHubUnreachableError",
    "NetworkProblem",
    "PackProblem",
    "PackRefusedError",
    "PublishedManifest",
    "PublishedProblem",
    "ReleaseFilesRefusedError",
    "ReleaseNotPublishedError",
    "TokenRefusedError",
    "can_answer",
    "check_cached_release",
    "confirms",
    "download_asset",
    "free_bytes",
    "install_release",
    "is_cached",
    "look_up_assets",
    "new_partial_archive",
    "read_pinned_release",
    "read_published_manifest",
    "release_folder",
    "unpack_archive",
    "write_archive",
    "write_pinned_release",
]

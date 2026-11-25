"""The commands of the release download: `pack-release`, `download-release`, `check-pinned-release`.

- `pack-release` writes the archive of a published release folder, and with `--pin` the pinned
  file (ADR-0030, Release archives).
- `download-release` puts a published release into the cache, from its GitHub Release, and
  prints only the path of its folder on standard output (ADR-0030, Download).
- `check-pinned-release` checks the pinned file in the repository, and with `--remote` against
  the GitHub Release of its tag (ADR-0030, Release archives, statement 5).

The exit statuses are those of `exit_statuses.py`: 4 declined, 5 network, 6 check failed, and 2
for an input that cannot be used. The command line maps each root error to its status.
`github_transport` and `free_bytes` are the seams of the tests, next to the standard streams and
the environment: the transport of every request, and the free space of the cache.
"""

import argparse
import asyncio
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
from app.release.manifest import verify_release

from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.composition_root.download_settings import load_download_settings
from supportiq_release.composition_root.exit_statuses import EXIT_CHECK_FAILED, EXIT_SUCCESS
from supportiq_release.distribution.adapters import (
    GitHubAccess,
    PackProblem,
    PackRefusedError,
    PublishedManifest,
    ReleaseNotPublishedError,
    can_answer,
    check_cached_release,
    confirms,
    download_asset,
    free_bytes,
    install_release,
    is_cached,
    look_up_assets,
    new_partial_archive,
    read_pinned_release,
    read_published_manifest,
    release_folder,
    write_archive,
    write_pinned_release,
)
from supportiq_release.distribution.domain import (
    PinnedRelease,
    PinnedReleaseInvalidError,
    ReleaseAsset,
    archive_asset,
    archive_name,
    check_pinned_size,
    checked_release_id,
    mebibytes,
)
from supportiq_release.errors import DownloadDeclinedError
from supportiq_release.files import new_output_folder

type AddParser = Callable[..., argparse.ArgumentParser]

_RELEASE_RECORDS = "eval/releases"


def github_transport() -> httpx.AsyncBaseTransport | None:
    """Return the transport of the requests to GitHub: None for the network.

    Returns:
        None, so httpx opens its own connections. Tests replace this function.
    """
    return None


def pack_release(arguments: argparse.Namespace) -> int:
    """Write the archive of a published release folder, and the pinned file with `--pin`.

    Args:
        arguments: The arguments of `pack-release`.

    Returns:
        0 when the archive is written, and the pinned file too with `--pin`.
    """
    folder, records = Path(arguments.release_folder), Path(arguments.release_records)
    source = verify_release(folder / MANIFEST_FILE_NAME)
    published = read_published_manifest(records, source.manifest.release_id)
    if (folder / MANIFEST_FILE_NAME).read_bytes() != published.content:
        raise PackRefusedError(PackProblem.MANIFEST_DIFFERS_FROM_GIT)
    output = Path(arguments.output)
    name = archive_name(published.release_id)
    paths = (MANIFEST_FILE_NAME, *published.size_bytes_by_path)
    with new_output_folder(output, (folder, records)) as staging:
        size = write_archive(folder, paths, staging / name)
    if arguments.pin:
        write_pinned_release(records, PinnedRelease(published.release_id, size))
    sys.stdout.write(
        f"release_id={published.release_id} archive={output / name} archive_size_bytes={size}\n"
    )
    return EXIT_SUCCESS


def download_release(arguments: argparse.Namespace) -> int:
    """Put a published release into the cache, and print only the path of its folder.

    Args:
        arguments: The arguments of `download-release`.

    Returns:
        0 when the release is in the cache and checked, downloaded now or before.
    """
    settings = load_download_settings()
    records = Path(arguments.release_records)
    release_id, pinned_size = _chosen_release(arguments.release, records)
    published = read_published_manifest(records, release_id)
    cache = settings.cache_folder()
    folder = release_folder(cache, release_id)
    if is_cached(folder):
        check_cached_release(folder, published)
        sys.stderr.write(f"Release {release_id} is in the cache and checked.\n")
    else:
        if not arguments.yes and not can_answer():
            raise DownloadDeclinedError
        access = GitHubAccess(token=settings.release_token, transport=github_transport())
        asset = archive_asset(release_id, asyncio.run(look_up_assets(access, release_id)))
        if pinned_size is not None:
            check_pinned_size(asset, pinned_size)
        # Nothing is created before the answer, so a declined run, or one that fails before it,
        # writes nothing.
        published.contents().check_free_space(asset.size_bytes, free_bytes(cache))
        sys.stderr.write(_plan(published, asset, folder))
        if not arguments.yes and not confirms("Proceed? [y/N] "):
            raise DownloadDeclinedError
        cache.mkdir(parents=True, exist_ok=True)
        _fetch(access, asset, published, folder)
    sys.stdout.write(f"{folder}\n")
    return EXIT_SUCCESS


def check_pinned_release(arguments: argparse.Namespace) -> int:
    """Check the pinned file, and with `--remote` the GitHub Release of its tag.

    Args:
        arguments: The arguments of `check-pinned-release`.

    Returns:
        0 when every check passed, 6 when the pinned file or its manifest fails.
    """
    records = Path(arguments.release_records)
    try:
        pinned = read_pinned_release(records)
        read_published_manifest(records, pinned.release_id)
    except (PinnedReleaseInvalidError, ReleaseNotPublishedError) as error:
        sys.stderr.write(f"{error}\n")
        return EXIT_CHECK_FAILED
    if arguments.remote:
        settings = load_download_settings()
        access = GitHubAccess(token=settings.release_token, transport=github_transport())
        assets = asyncio.run(look_up_assets(access, pinned.release_id))
        check_pinned_size(archive_asset(pinned.release_id, assets), pinned.archive_size_bytes)
    sys.stdout.write(
        f"pinned release_id={pinned.release_id} archive_size_bytes={pinned.archive_size_bytes}"
        f" github={'checked' if arguments.remote else 'not checked'}\n"
    )
    return EXIT_SUCCESS


def add_distribution_commands(add_parser: AddParser) -> None:
    """Add `pack-release`, `download-release`, and `check-pinned-release` to the command line.

    Args:
        add_parser: `add_parser` of the subcommands of `supportiq-release`.
    """
    pack = add_parser("pack-release", help="Write the archive of a published release folder.")
    pack.add_argument("--release-folder", required=True, help="A published release folder.")
    pack.add_argument("--release-records", required=True, help=_RELEASE_RECORDS)
    pack.add_argument("--output", required=True, help="A new or empty folder for the archive.")
    pack.add_argument("--pin", action="store_true", help="Also write the pinned file.")
    download = add_parser(
        "download-release", help="Put a published release into the cache; print its folder."
    )
    download.add_argument("--release", help="A published release ID; the pinned one otherwise.")
    download.add_argument("--release-records", default=_RELEASE_RECORDS, help=_RELEASE_RECORDS)
    download.add_argument("--yes", action="store_true", help="Answer the question with y.")
    check = add_parser("check-pinned-release", help="Check the pinned file of the releases.")
    check.add_argument("--release-records", default=_RELEASE_RECORDS, help=_RELEASE_RECORDS)
    check.add_argument("--remote", action="store_true", help="Also check its GitHub Release.")


def _chosen_release(requested: str | None, records: Path) -> tuple[str, int | None]:
    # The release that `--release` names, or the pinned one with the size of its archive.
    if requested is not None:
        return checked_release_id(requested), None
    pinned = read_pinned_release(records)
    return pinned.release_id, pinned.archive_size_bytes


def _plan(published: PublishedManifest, asset: ReleaseAsset, folder: Path) -> str:
    # Written to standard error, so standard output holds only the path of the folder.
    unpacked = mebibytes(sum(published.size_bytes_by_path.values()))
    return (
        f"Release {published.release_id}: archive of {asset.size_bytes} bytes"
        f" ({mebibytes(asset.size_bytes)} MiB, {unpacked} MiB unpacked), into {folder}.\n"
    )


def _fetch(
    access: GitHubAccess, asset: ReleaseAsset, published: PublishedManifest, folder: Path
) -> None:
    archive = new_partial_archive(folder.parent, published.release_id)
    try:
        asyncio.run(download_asset(access, asset, archive))
        install_release(archive, published, folder)
    finally:
        archive.unlink(missing_ok=True)
    sys.stderr.write(f"Release {published.release_id} is downloaded and checked.\n")

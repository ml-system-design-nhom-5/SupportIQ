"""The interim format of the release manifest, and the check of a release at startup (DATA-56).

A release is one folder: the manifest file and every asset file that it names, by a path
relative to that folder. The release command of `eval/` writes the manifest with this format,
and `ai-service` checks it, and every file it names, before it serves. A data contract in
`contracts/` replaces this format (ADR-0021, Follow-ups).

The check refuses a release, in this order, when:

1. the manifest is unreadable, is not JSON in UTF-8, or breaks the format of `ReleaseManifest`;
2. it links no passing gate run, except for a candidate (DATA-57);
3. the routing configuration was tuned for another model version (DATA-58);
4. a file resolves outside the folder, or is not a readable regular file;
5. the folder holds a symbolic link, even one that the manifest names, another entry that is
   not a folder and that the manifest does not name, or a folder that cannot be listed. A
   release holds only regular files and folders, because a model library reads a whole
   folder, so a link or an extra file would change what is served without a checksum
   (ADR-0018, decision driver 2);
6. a file has another size, or another SHA-256, than the manifest states.
"""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, ValidationError, model_validator

from app.release.adapters.asset_document import (
    AssetFile,
    AssetFiles,
    AssetName,
    AssetVersionText,
    RelativePath,
    Sha256,
    StrictDocument,
)
from app.release.domain import (
    AssetVersions,
    LoadedRelease,
    ReleaseInvalidError,
    ReleaseInvalidReason,
)

MANIFEST_FORMAT = "supportiq-release-manifest/interim-1"
_HASH_NAME = "sha256"
# The pattern of `release_id` in the contract, so it can be served as it is
# (contracts/schemas/AssetVersions.yaml).
_RELEASE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

ReleaseId = Annotated[str, StringConstraints(pattern=_RELEASE_ID_PATTERN)]


class ManifestFile(StrictDocument):
    """One file of an asset.

    Attributes:
        path: The path of the file, relative to the folder of the manifest.
        sha256: The SHA-256 of every byte of the file, in lowercase hexadecimal.
        size_bytes: The size of the file.
    """

    path: RelativePath
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]


class ManifestAsset(StrictDocument):
    """One versioned asset and its files (ARCH-38).

    Attributes:
        version: The version of the asset, which results report as it is.
        files: Every file of the asset.
    """

    version: AssetVersionText
    files: Annotated[tuple[ManifestFile, ...], Field(min_length=1)]


class RoutingAsset(ManifestAsset):
    """The routing configuration, with the model version it was tuned for (DATA-58).

    Attributes:
        model_version: The version of the model artifact that the routing configuration was
            tuned for. It must be the version of the model of the same manifest.
    """

    model_version: AssetVersionText


class ManifestAssets(StrictDocument):
    """The six assets of a release, each one required (DATA-56).

    Attributes:
        model: The intent classification model artifact.
        kb: The KB version: the KB document versions that retrieval searches, possibly none.
        mapping: The document-to-intent mapping.
        prompts: The set of prompts that drafting uses.
        routing: The routing configuration.
        index: The retrieval index, with the files of the encoder that builds it and embeds
            each query.
    """

    model: ManifestAsset
    kb: ManifestAsset
    mapping: ManifestAsset
    prompts: ManifestAsset
    routing: RoutingAsset
    index: ManifestAsset

    def named_assets(self) -> tuple[tuple[AssetName, ManifestAsset], ...]:
        """Return every asset with its name.

        Returns:
            The name of each asset, as in the manifest, and the asset, in the manifest's order.
        """
        return (
            ("model", self.model),
            ("kb", self.kb),
            ("mapping", self.mapping),
            ("prompts", self.prompts),
            ("routing", self.routing),
            ("index", self.index),
        )

    def named_files(self) -> Iterator[tuple[AssetName, ManifestFile]]:
        """Yield every file of every asset, with the name of its asset.

        Yields:
            The name of the asset, as in the manifest, and one of its files.
        """
        for name, asset in self.named_assets():
            for manifest_file in asset.files:
                yield name, manifest_file


class GateRun(StrictDocument):
    """The run of the offline evaluation gate that this manifest passed (DATA-57).

    Attributes:
        run_id: The identifier of the run.
        outcome: Always `passed`: a manifest never links a failed run.
        record: The path of the record of the run in the repository.
        record_sha256: The SHA-256 of that record, which CI checks.
    """

    run_id: ReleaseId
    outcome: Literal["passed"]
    record: RelativePath
    record_sha256: Sha256


class ReleaseManifest(StrictDocument):
    """The interim format of the release manifest (DATA-56).

    Attributes:
        format: The name and version of this format.
        release_id: The unique, immutable identifier of the release. It is never reused, not
            even after a candidate fails the gate (ARCH-40).
        assets: The six assets.
        gate_run: The passing gate run, or None in a candidate that has not passed it yet.
    """

    format: Literal["supportiq-release-manifest/interim-1"]
    release_id: ReleaseId
    assets: ManifestAssets
    gate_run: GateRun | None

    @model_validator(mode="after")
    def _each_file_belongs_to_one_asset(self) -> Self:
        paths = [manifest_file.path for _name, manifest_file in self.assets.named_files()]
        if len(set(paths)) != len(paths):
            message = "every file belongs to one asset, once"
            raise ValueError(message)
        return self

    def asset_versions(self) -> AssetVersions:
        """Return the versions that every result reports (ARCH-39).

        Returns:
            The `release_id` and the version of each asset. The contract has one
            `prompt_version` for the set of prompts.
        """
        assets = self.assets
        return AssetVersions(
            release_id=self.release_id,
            model_version=assets.model.version,
            kb_version=assets.kb.version,
            mapping_version=assets.mapping.version,
            prompt_version=assets.prompts.version,
            routing_version=assets.routing.version,
            index_version=assets.index.version,
        )


@dataclass(frozen=True, slots=True)
class VerifiedReleaseSource:
    """Implement the `ReleaseSource` port for a release whose every file was checked.

    Only `verify_release` and `verify_candidate` create one.

    Attributes:
        manifest: The checked manifest.
        folder: The release folder, which holds the manifest and every file it names.
    """

    manifest: ReleaseManifest
    folder: Path

    def current(self) -> LoadedRelease:
        """Return the checked release.

        Returns:
            The release with the versions of its manifest.
        """
        return LoadedRelease(versions=self.manifest.asset_versions())

    def asset_files(self, asset: AssetName) -> AssetFiles:
        """Return the checked files of one asset, for the adapter that reads them.

        Args:
            asset: The asset.

        Returns:
            Its version and its files, and the paths of the files of every other asset.
        """
        named_assets = dict(self.manifest.assets.named_assets())
        named_files = tuple(self.manifest.assets.named_files())
        return AssetFiles(
            asset=asset,
            version=named_assets[asset].version,
            folder=self.folder,
            files=tuple(
                AssetFile(
                    asset=asset,
                    file_path=manifest_file.path,
                    location=self.folder / manifest_file.path,
                )
                for name, manifest_file in named_files
                if name == asset
            ),
            other_file_paths=frozenset(
                manifest_file.path for name, manifest_file in named_files if name != asset
            ),
        )


def verify_release(manifest_path: Path) -> VerifiedReleaseSource:
    """Check a published release before ai-service serves it.

    Args:
        manifest_path: The manifest file; the assets are in its folder.

    Returns:
        The source of the checked release.

    Raises:
        ReleaseInvalidError: The release fails one of the checks of this module, or its
            manifest links no passing gate run.
    """
    manifest = read_release_manifest(manifest_path)
    if manifest.gate_run is None:
        raise ReleaseInvalidError(ReleaseInvalidReason.GATE_RUN_MISSING)
    return _verify_files(manifest, manifest_path)


def verify_candidate(manifest_path: Path) -> VerifiedReleaseSource:
    """Check a candidate release, which may not have passed the gate yet.

    Only the release command calls it, to run the gate on exactly that candidate (ADR-0021,
    Release and the offline evaluation gate). `ai-service serve` always calls
    `verify_release`.

    Args:
        manifest_path: The manifest file; the assets are in its folder.

    Returns:
        The source of the checked candidate.

    Raises:
        ReleaseInvalidError: The candidate fails one of the checks of this module, other than
            the gate run.
    """
    return _verify_files(read_release_manifest(manifest_path), manifest_path)


def read_release_manifest(manifest_path: Path) -> ReleaseManifest:
    """Read a manifest file and check its format, without reading the files it names.

    Args:
        manifest_path: The manifest file.

    Returns:
        The manifest.

    Raises:
        ReleaseInvalidError: The file is unreadable, is not JSON in UTF-8, or breaks the
            format of `ReleaseManifest`.
    """
    try:
        content = manifest_path.read_bytes()
    except OSError as error:
        raise ReleaseInvalidError(ReleaseInvalidReason.MANIFEST_UNREADABLE) from error
    try:
        return ReleaseManifest.model_validate_json(content)
    except ValidationError as error:
        raise ReleaseInvalidError(ReleaseInvalidReason.MANIFEST_INVALID) from error


def _verify_files(manifest: ReleaseManifest, manifest_path: Path) -> VerifiedReleaseSource:
    assets = manifest.assets
    if assets.routing.model_version != assets.model.version:
        raise ReleaseInvalidError(ReleaseInvalidReason.ROUTING_MODEL_MISMATCH, asset="routing")
    manifest_location = manifest_path.resolve()
    folder = manifest_location.parent
    located = [
        (name, manifest_file, _locate(folder, manifest_location, name, manifest_file))
        for name, manifest_file in assets.named_files()
    ]
    _refuse_links_and_unlisted_entries(
        folder, {manifest_location} | {path for _, _, path in located}
    )
    for name, manifest_file, path in located:
        _check_content(path, name, manifest_file)
    return VerifiedReleaseSource(manifest, folder)


def _locate(folder: Path, manifest_location: Path, asset: str, manifest_file: ManifestFile) -> Path:
    # Resolving follows every symbolic link, so a link out of the folder is refused too.
    path = (folder / manifest_file.path).resolve()
    if not path.is_relative_to(folder):
        raise ReleaseInvalidError(
            ReleaseInvalidReason.FILE_OUTSIDE_RELEASE, asset=asset, file_path=manifest_file.path
        )
    if path == manifest_location:
        # A manifest cannot hold its own checksum, so it never names itself.
        raise ReleaseInvalidError(
            ReleaseInvalidReason.MANIFEST_INVALID, asset=asset, file_path=manifest_file.path
        )
    if not path.is_file():
        raise ReleaseInvalidError(
            ReleaseInvalidReason.FILE_UNREADABLE, asset=asset, file_path=manifest_file.path
        )
    return path


def _refuse_links_and_unlisted_entries(folder: Path, listed: set[Path]) -> None:
    for path in _entries(folder):
        file_path = path.relative_to(folder).as_posix()
        if path.is_symlink():
            raise ReleaseInvalidError(ReleaseInvalidReason.LINK_IN_RELEASE, file_path=file_path)
        # `Path.walk` follows no link, so a path that is not a link is already resolved.
        if path not in listed:
            raise ReleaseInvalidError(ReleaseInvalidReason.FILE_UNLISTED, file_path=file_path)


def _entries(folder: Path) -> list[Path]:
    # Every entry of the folder and of its subfolders, except the subfolders, in a stable
    # order. `Path.walk` lists a link as an entry, even a link to a folder, and never follows it.
    def refuse_unreadable_folder(error: OSError) -> None:
        # Otherwise the walk would skip that folder, and every entry in it, without a word.
        raise ReleaseInvalidError(
            ReleaseInvalidReason.FILE_UNREADABLE,
            file_path=Path(error.filename).relative_to(folder).as_posix(),
        ) from error

    return sorted(
        directory / name
        for directory, _folder_names, names in folder.walk(on_error=refuse_unreadable_folder)
        for name in names
    )


def _check_content(path: Path, asset: str, manifest_file: ManifestFile) -> None:
    try:
        size = path.stat().st_size
        if size != manifest_file.size_bytes:
            raise ReleaseInvalidError(
                ReleaseInvalidReason.SIZE_MISMATCH, asset=asset, file_path=manifest_file.path
            )
        with path.open("rb") as content:
            digest = hashlib.file_digest(content, _HASH_NAME).hexdigest()
    except OSError as error:
        raise ReleaseInvalidError(
            ReleaseInvalidReason.FILE_UNREADABLE, asset=asset, file_path=manifest_file.path
        ) from error
    if digest != manifest_file.sha256:
        raise ReleaseInvalidError(
            ReleaseInvalidReason.CHECKSUM_MISMATCH, asset=asset, file_path=manifest_file.path
        )

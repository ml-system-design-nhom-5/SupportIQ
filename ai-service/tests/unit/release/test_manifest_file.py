"""A release is served only when its manifest is complete and every file matches it (DATA-56)."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.release.manifest import (
    ReleaseInvalidError,
    ReleaseInvalidReason,
    read_release_manifest,
    verify_candidate,
    verify_release,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    ASSET_FILES,
    MANIFEST_FILE_NAME,
    ManifestDocument,
    write_release,
)

type ManifestChange = Callable[[ManifestDocument], None]

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root reads every file and lists every folder, whatever its permissions",
)


def first_file(document: ManifestDocument, asset: str) -> ManifestDocument:
    return document["assets"][asset]["files"][0]


def flip_first_byte(path: Path) -> None:
    content = bytearray(path.read_bytes())
    content[0] ^= 1
    path.write_bytes(bytes(content))


def refusal(verify: Callable[[Path], object], manifest_path: Path) -> ReleaseInvalidError:
    with pytest.raises(ReleaseInvalidError) as raised:
        verify(manifest_path)
    return raised.value


def test_a_complete_release_serves_the_versions_of_its_manifest(tmp_path: Path) -> None:
    source = verify_release(write_release(tmp_path))

    assert source.current() == LoadedRelease(versions=EXAMPLE_VERSIONS)


def test_the_files_of_the_encoder_belong_to_the_index(tmp_path: Path) -> None:
    source = verify_release(write_release(tmp_path))

    index_paths = [manifest_file.path for manifest_file in source.manifest.assets.index.files]
    assert index_paths == list(ASSET_FILES["index"])
    assert "index/encoder/1_Pooling/config.json" in index_paths


def test_a_candidate_without_a_gate_run_is_checked_but_never_served(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path, gate_run=False)

    assert verify_candidate(manifest_path).current() == LoadedRelease(versions=EXAMPLE_VERSIONS)
    assert refusal(verify_release, manifest_path).reason is ReleaseInvalidReason.GATE_RUN_MISSING


@pytest.mark.parametrize("name", ["missing.json", "."])
def test_an_unreadable_manifest_is_refused(tmp_path: Path, name: str) -> None:
    error = refusal(verify_release, tmp_path / name)

    assert error.reason is ReleaseInvalidReason.MANIFEST_UNREADABLE


@pytest.mark.parametrize("content", [b"{", b"\xff\xfe", b"[]", b""])
def test_a_manifest_that_is_not_a_json_object_in_utf8_is_refused(
    tmp_path: Path, content: bytes
) -> None:
    manifest_path = tmp_path / MANIFEST_FILE_NAME
    manifest_path.write_bytes(content)

    assert refusal(verify_release, manifest_path).reason is ReleaseInvalidReason.MANIFEST_INVALID


def _set(key: str, value: object) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        document[key] = value

    return change


def _delete(key: str) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        del document[key]

    return change


def _set_asset(asset: str, key: str, value: object) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        document["assets"][asset][key] = value

    return change


def _set_file(key: str, value: object) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        first_file(document, "model")[key] = value

    return change


def _delete_asset_key(asset: str, key: str) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        del document["assets"][asset][key]

    return change


def _delete_asset(asset: str) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        del document["assets"][asset]

    return change


def _add_an_asset(document: ManifestDocument) -> None:
    extra_file = {"path": "extra.bin", "sha256": "0" * 64, "size_bytes": 0}
    document["assets"]["extra"] = {"version": "1", "files": [extra_file]}


def _repeat_a_path(document: ManifestDocument) -> None:
    document["assets"]["kb"]["files"].append(first_file(document, "model"))


def _set_gate_run(key: str, value: object) -> ManifestChange:
    def change(document: ManifestDocument) -> None:
        document["gate_run"] = {**document["gate_run"], key: value}

    return change


@pytest.mark.parametrize(
    "change",
    [
        _set("extra", 1),
        _set("format", "supportiq-release-manifest/interim-2"),
        _delete("format"),
        _delete("gate_run"),
        _set("release_id", "-starts-with-a-dash"),
        _set("release_id", "r" * 65),
        _set("release_id", "release/1"),
        _add_an_asset,
        _delete_asset("index"),
        _set_asset("kb", "files", []),
        _set_asset("kb", "extra", 1),
        _set_asset("model", "version", ""),
        _set_asset("model", "version", "v 1"),
        _set_asset("model", "version", 1),
        _set_asset("routing", "model_version", None),
        _delete_asset_key("routing", "model_version"),
        _set_file("sha256", "A" * 64),
        _set_file("sha256", "a" * 63),
        _set_file("size_bytes", -1),
        _set_file("size_bytes", "33"),
        _set_file("extra", 1),
        _set_file("path", "/etc/passwd"),
        _set_file("path", "../outside.bin"),
        _set_file("path", "model/../model.bin"),
        _set_file("path", "./model.bin"),
        _set_file("path", "model/./model.bin"),
        _set_file("path", "model//model.bin"),
        _set_file("path", "model\\model.bin"),
        _set_file("path", "model/"),
        _set_file("path", ""),
        _set_file("path", "a" * 256),
        _repeat_a_path,
        _set_gate_run("outcome", "failed"),
        _set_gate_run("record", "../report.json"),
        _set_gate_run("extra", 1),
    ],
)
def test_a_manifest_that_breaks_the_format_is_refused(
    tmp_path: Path, change: ManifestChange
) -> None:
    manifest_path = write_release(tmp_path, change=change)

    assert refusal(verify_release, manifest_path).reason is ReleaseInvalidReason.MANIFEST_INVALID
    with pytest.raises(ReleaseInvalidError):
        read_release_manifest(manifest_path)


def test_a_routing_configuration_tuned_for_another_model_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(
        tmp_path, change=_set_asset("routing", "model_version", "intent-model-sample-2")
    )

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.asset) == (ReleaseInvalidReason.ROUTING_MODEL_MISMATCH, "routing")


def test_a_file_that_links_out_of_the_release_folder_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    manifest_path = write_release(folder)
    weights = folder / "model" / "model.safetensors"
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(weights.read_bytes())
    weights.unlink()
    weights.symlink_to(outside)

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.asset, error.file_path) == (
        ReleaseInvalidReason.FILE_OUTSIDE_RELEASE,
        "model",
        "model/model.safetensors",
    )


@pytest.mark.parametrize(
    ("link_path", "target"),
    [
        ("model/tokenizer_config.json", "../kb/kb.json"),
        ("index/encoder/2_Normalize", "../../../outside"),
        ("index/encoder/extra", "../../model"),
        ("model/special_tokens_map.json", "missing.json"),
        ("model/config.json", "tokenizer.json"),
    ],
    ids=[
        "an unlisted name for a listed file",
        "a folder out of the release",
        "a folder of the release",
        "a broken link",
        "a listed name for another listed file",
    ],
)
def test_a_symbolic_link_in_the_release_folder_is_refused(
    tmp_path: Path, link_path: str, target: str
) -> None:
    folder = tmp_path / "release"
    folder.mkdir()
    manifest_path = write_release(folder)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "vocab.txt").write_bytes(b"not in the release\n")
    link = folder / link_path
    link.unlink(missing_ok=True)
    link.symlink_to(target)

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.file_path) == (ReleaseInvalidReason.LINK_IN_RELEASE, link_path)


def test_a_manifest_that_names_itself_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path, change=_set_file("path", MANIFEST_FILE_NAME))

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.file_path) == (
        ReleaseInvalidReason.MANIFEST_INVALID,
        MANIFEST_FILE_NAME,
    )


@pytest.mark.parametrize("folder_in_its_place", [False, True])
def test_a_missing_file_or_a_folder_in_its_place_is_refused(
    tmp_path: Path, *, folder_in_its_place: bool
) -> None:
    manifest_path = write_release(tmp_path)
    tokenizer = tmp_path / "model" / "tokenizer.json"
    tokenizer.unlink()
    if folder_in_its_place:
        tokenizer.mkdir()

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.asset, error.file_path) == (
        ReleaseInvalidReason.FILE_UNREADABLE,
        "model",
        "model/tokenizer.json",
    )


@needs_file_permissions
def test_a_file_that_cannot_be_read_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    routing = tmp_path / "routing" / "routing.json"
    routing.chmod(0)

    try:
        error = refusal(verify_release, manifest_path)
    finally:
        routing.chmod(0o600)

    assert (error.reason, error.asset, error.file_path) == (
        ReleaseInvalidReason.FILE_UNREADABLE,
        "routing",
        "routing/routing.json",
    )


@pytest.mark.parametrize(
    "extra_path", ["model/tokenizer_config.json", "index/encoder/vocab.txt", ".DS_Store"]
)
def test_a_file_that_the_manifest_does_not_name_is_refused(tmp_path: Path, extra_path: str) -> None:
    manifest_path = write_release(tmp_path)
    (tmp_path / extra_path).write_bytes(b"not in the manifest\n")

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.file_path) == (ReleaseInvalidReason.FILE_UNLISTED, extra_path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="the platform has no named pipe")
def test_an_unlisted_entry_that_is_not_a_regular_file_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    os.mkfifo(tmp_path / "model" / "special_tokens_map.json")

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.file_path) == (
        ReleaseInvalidReason.FILE_UNLISTED,
        "model/special_tokens_map.json",
    )


@needs_file_permissions
def test_a_folder_that_cannot_be_listed_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    unlisted_folder = tmp_path / "index" / "encoder" / "2_Normalize"
    unlisted_folder.mkdir()
    (unlisted_folder / "config.json").write_bytes(b"not in the manifest\n")
    unlisted_folder.chmod(0o100)

    try:
        error = refusal(verify_release, manifest_path)
    finally:
        unlisted_folder.chmod(0o700)

    assert (error.reason, error.file_path) == (
        ReleaseInvalidReason.FILE_UNREADABLE,
        "index/encoder/2_Normalize",
    )


def test_a_file_of_another_size_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    with (tmp_path / "kb" / "kb.json").open("ab") as kb:
        kb.write(b" ")

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.asset, error.file_path) == (
        ReleaseInvalidReason.SIZE_MISMATCH,
        "kb",
        "kb/kb.json",
    )


def test_a_file_with_one_changed_byte_is_refused(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    flip_first_byte(tmp_path / "index" / "encoder" / "model.safetensors")

    error = refusal(verify_release, manifest_path)

    assert (error.reason, error.asset, error.file_path) == (
        ReleaseInvalidReason.CHECKSUM_MISMATCH,
        "index",
        "index/encoder/model.safetensors",
    )


def test_the_gate_run_is_checked_before_any_file(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path, gate_run=False)
    (tmp_path / "model" / "model.safetensors").unlink()

    assert refusal(verify_release, manifest_path).reason is ReleaseInvalidReason.GATE_RUN_MISSING


def test_an_unlisted_file_is_found_before_any_file_is_hashed(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    flip_first_byte(tmp_path / "model" / "model.safetensors")
    (tmp_path / "extra.bin").write_bytes(b"extra\n")

    assert refusal(verify_release, manifest_path).reason is ReleaseInvalidReason.FILE_UNLISTED


def test_the_detail_of_a_refusal_names_only_its_reason(tmp_path: Path) -> None:
    manifest_path = write_release(tmp_path)
    (tmp_path / "kb" / "kb.json").write_bytes(b'{"documents": [1, 2]}\n')

    error = refusal(verify_release, manifest_path)

    assert str(error) == "The release manifest is refused: size_mismatch."

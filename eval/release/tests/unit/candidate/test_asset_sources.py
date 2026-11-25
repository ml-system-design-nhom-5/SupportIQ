"""Sources are copied as real files only, byte for byte, and never over another file."""

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_release.candidate.adapters import (
    CopiedFile,
    SourceInvalidError,
    SourceProblem,
    copy_files,
    plan_copies,
    read_release_spec,
)
from tests.unit.candidate.fakes import RELEASE_FILES, SOURCE_FILES, write_sources, write_spec

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root reads every file and lists every folder, whatever its permissions",
)


def _refusal(base: Path) -> SourceInvalidError:
    with pytest.raises(SourceInvalidError) as refused:
        plan_copies(read_release_spec(write_spec(base)), base)
    return refused.value


@pytest.fixture
def copied(tmp_path: Path) -> tuple[Path, dict[str, CopiedFile]]:
    base = write_sources(tmp_path / "sources")
    output = tmp_path / "release"
    output.mkdir()
    files = copy_files(plan_copies(read_release_spec(write_spec(base)), base), output)
    return output, {item.path: item for item in files}


def test_every_file_of_every_source_is_planned_with_its_path_in_the_release(
    tmp_path: Path,
) -> None:
    base = write_sources(tmp_path)

    planned = plan_copies(read_release_spec(write_spec(base)), base)

    assert [(copy.asset, copy.source, copy.path) for copy in planned] == [
        ("index", base / "index/encoder/model.safetensors", "index/encoder/model.safetensors"),
        ("index", base / "index/index.json", "index/index.json"),
        ("kb", base / "kb.json", "kb/kb.json"),
        ("mapping", base / "document-intents.json", "mapping/document-intents.json"),
        ("model", base / "model/artifact.json", "model/artifact.json"),
        ("model", base / "model/model.safetensors", "model/model.safetensors"),
        ("model", base / "model/tokenizer.json", "model/tokenizer.json"),
        (
            "prompts",
            base / "prompts/drafting-requires-authority.txt",
            "prompts/drafting-requires-authority.txt",
        ),
        ("prompts", base / "prompts/drafting-system.txt", "prompts/drafting-system.txt"),
        ("routing", base / "routing.json", "routing/routing.json"),
    ]


@pytest.mark.parametrize(("name", "path"), list(RELEASE_FILES.items()))
def test_each_file_is_copied_byte_for_byte_with_its_checksum_and_size(
    copied: tuple[Path, dict[str, CopiedFile]], name: str, path: str
) -> None:
    output, by_path = copied
    data = SOURCE_FILES[name]

    assert (output / path).read_bytes() == data
    assert (by_path[path].sha256, by_path[path].size_bytes) == (
        hashlib.sha256(data).hexdigest(),
        len(data),
    )


def test_a_file_is_never_copied_over_another(tmp_path: Path) -> None:
    base = write_sources(tmp_path / "sources")
    output = tmp_path / "release"
    (output / "kb").mkdir(parents=True)
    (output / "kb" / "kb.json").write_bytes(b"kept")

    with pytest.raises(FileExistsError):
        copy_files(plan_copies(read_release_spec(write_spec(base)), base), output)

    assert (output / "kb" / "kb.json").read_bytes() == b"kept"


def _link_the_kb_file(base: Path) -> None:
    (base / "kb.json").rename(base / "real-kb.json")
    (base / "kb.json").symlink_to(base / "real-kb.json")


def _link_the_model_folder(base: Path) -> None:
    (base / "model").rename(base / "real-model")
    (base / "model").symlink_to(base / "real-model")


def _link_a_file_inside(base: Path) -> None:
    (base / "index" / "encoder" / "model.safetensors").unlink()
    (base / "index" / "encoder" / "model.safetensors").symlink_to(base / "kb.json")


def _link_a_folder_inside(base: Path) -> None:
    (base / "index" / "more").symlink_to(base / "prompts")


def _make_a_hugging_face_snapshot(base: Path) -> None:
    # A snapshot of the Hugging Face cache: each file is a link to a blob.
    blobs = base / "blobs"
    blobs.mkdir()
    for name in ("artifact.json", "model.safetensors", "tokenizer.json"):
        (blobs / name).write_bytes((base / "model" / name).read_bytes())
        (base / "model" / name).unlink()
        (base / "model" / name).symlink_to(Path("../blobs") / name)


@pytest.mark.parametrize(
    "make_link",
    [
        _link_the_kb_file,
        _link_the_model_folder,
        _link_a_file_inside,
        _link_a_folder_inside,
        _make_a_hugging_face_snapshot,
    ],
)
def test_a_link_anywhere_in_a_source_stops_the_build(
    tmp_path: Path, make_link: Callable[[Path], None]
) -> None:
    base = write_sources(tmp_path)
    make_link(base)

    refused = _refusal(base)

    assert refused.problem is SourceProblem.LINK
    assert "Hugging Face cache" in str(refused)


def test_a_missing_source_stops_the_build(tmp_path: Path) -> None:
    base = write_sources(tmp_path)
    (base / "routing.json").unlink()

    refused = _refusal(base)

    assert (refused.problem, refused.asset) == (SourceProblem.MISSING, "routing")


def _replace_a_file_source_by_a_pipe(base: Path) -> None:
    (base / "routing.json").unlink()
    os.mkfifo(base / "routing.json")


def _add_a_pipe_to_a_folder_source(base: Path) -> None:
    os.mkfifo(base / "model" / "pipe")


@pytest.mark.parametrize(
    "make_pipe", [_replace_a_file_source_by_a_pipe, _add_a_pipe_to_a_folder_source]
)
def test_a_source_that_is_not_a_regular_file_or_folder_stops_the_build(
    tmp_path: Path, make_pipe: Callable[[Path], None]
) -> None:
    base = write_sources(tmp_path)
    make_pipe(base)

    assert _refusal(base).problem is SourceProblem.NOT_REGULAR


def test_a_source_folder_without_a_file_stops_the_build(tmp_path: Path) -> None:
    base = write_sources(tmp_path)
    for name in ("drafting-system.txt", "drafting-requires-authority.txt"):
        (base / "prompts" / name).unlink()
    (base / "prompts" / "empty").mkdir()

    refused = _refusal(base)

    assert (refused.problem, refused.asset) == (SourceProblem.EMPTY_FOLDER, "prompts")


def test_a_file_name_that_a_release_cannot_hold_stops_the_build(tmp_path: Path) -> None:
    base = write_sources(tmp_path)
    (base / "model" / "a copy.json").write_bytes(b"x")

    refused = _refusal(base)

    assert (refused.problem, refused.asset) == (SourceProblem.NAME_INVALID, "model")


def _add_a_finder_file(base: Path) -> None:
    (base / "prompts" / ".DS_Store").write_bytes(b"written by Finder")


def _add_a_hidden_folder(base: Path) -> None:
    (base / "prompts" / ".cache").mkdir()
    (base / "prompts" / ".cache" / "note.txt").write_bytes(b"x")


@pytest.mark.parametrize("hide", [_add_a_finder_file, _add_a_hidden_folder])
def test_a_hidden_entry_in_a_folder_source_stops_the_build(
    tmp_path: Path, hide: Callable[[Path], None]
) -> None:
    # The prompts asset holds exactly two files, so an extra file changes what is served.
    base = write_sources(tmp_path)
    hide(base)

    refused = _refusal(base)

    assert (refused.problem, refused.asset) == (SourceProblem.HIDDEN, "prompts")


@needs_file_permissions
def test_a_folder_of_a_source_that_cannot_be_listed_stops_the_build(tmp_path: Path) -> None:
    # `Path.walk` would skip the folder, and the candidate would lack its files.
    base = write_sources(tmp_path)
    locked = base / "index" / "encoder"
    locked.chmod(0)

    try:
        refused = _refusal(base)
    finally:
        locked.chmod(0o700)

    assert (refused.problem, refused.asset) == (SourceProblem.UNREADABLE, "index")


@needs_file_permissions
def test_a_source_file_that_cannot_be_read_stops_the_copy_with_a_typed_error(
    tmp_path: Path,
) -> None:
    base = write_sources(tmp_path / "sources")
    planned = plan_copies(read_release_spec(write_spec(base)), base)
    output = tmp_path / "release"
    output.mkdir()
    (base / "routing.json").chmod(0)

    try:
        with pytest.raises(SourceInvalidError) as refused:
            copy_files(planned, output)
    finally:
        (base / "routing.json").chmod(0o600)

    assert (refused.value.problem, refused.value.asset) == (SourceProblem.UNREADABLE, "routing")

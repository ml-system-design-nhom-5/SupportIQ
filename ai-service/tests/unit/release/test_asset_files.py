"""An adapter reads only the checked files of its asset, and a broken file stops startup."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.release.assets import (
    AssetFile,
    StrictDocument,
    UtcTimestamp,
    read_json_asset,
    read_text_asset,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import ASSET_FILES, asset_refusal, verified_release


class _Moment(StrictDocument):
    at: UtcTimestamp


def test_an_asset_holds_its_own_files_and_knows_the_paths_of_the_others(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("routing")

    assert (files.asset, files.version) == ("routing", EXAMPLE_VERSIONS.routing_version)
    (routing_file,) = files.files
    assert routing_file == AssetFile(
        asset="routing",
        file_path="routing/routing.json",
        location=tmp_path.resolve() / "routing" / "routing.json",
    )
    other_paths = {
        path for name, paths in ASSET_FILES.items() if name != "routing" for path in paths
    }
    assert files.other_file_paths == other_paths


def test_a_file_is_found_by_its_path_or_its_name(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("model")

    assert files.file("model/config.json").file_path == "model/config.json"
    assert files.named("tokenizer.json").file_path == "model/tokenizer.json"


def test_a_missing_file_is_refused_with_its_path(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("model")

    error = asset_refusal(lambda: files.file("model/vocab.txt"))

    assert (error.asset, error.file_path) == ("model", "model/vocab.txt")


def test_a_name_that_no_file_or_several_files_hold_is_refused(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("index")

    assert asset_refusal(lambda: files.named("vocab.txt")).asset == "index"
    assert asset_refusal(lambda: files.named("config.json")).asset == "index"


def test_only_an_asset_of_one_file_has_a_sole_file(tmp_path: Path) -> None:
    source = verified_release(tmp_path)

    assert source.asset_files("kb").sole().file_path == "kb/kb.json"
    assert asset_refusal(source.asset_files("prompts").sole).asset == "prompts"


def test_a_folder_of_an_asset_is_found_when_it_holds_files_of_that_asset_only(
    tmp_path: Path,
) -> None:
    files = verified_release(tmp_path).asset_files("index")

    assert files.directory("index/encoder") == tmp_path.resolve() / "index" / "encoder"
    assert asset_refusal(lambda: files.directory("model")).file_path == "model"


def test_a_folder_that_holds_a_file_of_another_asset_is_refused(tmp_path: Path) -> None:
    source = verified_release(
        tmp_path, {"prompts": {"index/encoder/prompt.txt": b"A fake prompt.\n"}}
    )

    error = asset_refusal(lambda: source.asset_files("index").directory("index/encoder"))

    assert (error.asset, error.file_path) == ("index", "index/encoder")


def test_a_json_file_is_read_strictly_with_its_model(tmp_path: Path) -> None:
    source = verified_release(
        tmp_path, {"routing": {"routing/routing.json": b'{"at": "2026-11-05T09:30:00Z"}\n'}}
    )
    routing_file = source.asset_files("routing").sole()

    moment = read_json_asset(routing_file, _Moment)

    assert moment.at == datetime(2026, 11, 5, 9, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "content",
    [
        b'{"at": "2026-11-05T09:30:00+07:00"}',
        b'{"at": "2026-11-05T09:30:00"}',
        b'{"at": "2026-13-05T09:30:00Z"}',
        b'{"at": 1}',
        b'{"at": "2026-11-05T09:30:00Z", "extra": 1}',
        b"{",
        b"\xff\xfe",
    ],
)
def test_a_json_file_that_breaks_its_model_is_refused(tmp_path: Path, content: bytes) -> None:
    source = verified_release(tmp_path, {"routing": {"routing/routing.json": content}})
    routing_file = source.asset_files("routing").sole()

    error = asset_refusal(lambda: read_json_asset(routing_file, _Moment))

    assert (error.asset, error.file_path) == ("routing", "routing/routing.json")


def test_a_file_that_disappears_after_the_check_is_refused(tmp_path: Path) -> None:
    routing_file = verified_release(tmp_path).asset_files("routing").sole()
    routing_file.location.unlink()

    assert (
        asset_refusal(lambda: read_json_asset(routing_file, _Moment)).file_path
        == routing_file.file_path
    )
    assert asset_refusal(lambda: read_text_asset(routing_file)).file_path == routing_file.file_path


def test_a_text_file_is_read_as_it_is(tmp_path: Path) -> None:
    prompt = verified_release(tmp_path).asset_files("prompts").named("drafting-system.txt")

    assert read_text_asset(prompt) == "A fake system prompt for tests.\n"


@pytest.mark.parametrize("content", [b"\xff\xfe not UTF-8\n", b" \n\t\n"])
def test_a_text_file_that_is_not_utf8_or_holds_only_spaces_is_refused(
    tmp_path: Path, content: bytes
) -> None:
    source = verified_release(tmp_path, {"prompts": {"prompts/drafting-system.txt": content}})
    prompt = source.asset_files("prompts").named("drafting-system.txt")

    assert asset_refusal(lambda: read_text_asset(prompt)).file_path == "prompts/drafting-system.txt"

"""An output folder is complete or absent, never overwrites, and never touches an input."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_release.files import OutputFolderError, OutputFolderProblem, new_output_folder

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root writes into every folder, whatever its permissions",
)


class _StopError(Exception):
    """An error that a test raises inside the block."""


def _write_one_file_and_fail(staging: Path) -> None:
    (staging / "kb.json").write_text("half")
    raise _StopError


def _write_one_file_and_fail_to_write(staging: Path) -> None:
    (staging / "kb.json").write_text("half")
    (staging / "missing" / "report.json").write_text("never")


def test_the_files_of_the_block_land_in_a_new_folder_with_its_parents(tmp_path: Path) -> None:
    output = tmp_path / "a" / "b"

    with new_output_folder(output, ()) as staging:
        (staging / "kb.json").write_text("done")

    assert [path.name for path in output.iterdir()] == ["kb.json"]
    assert [path.name for path in output.parent.iterdir()] == ["b"]


def test_an_empty_folder_is_used(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()

    with new_output_folder(output, ()) as staging:
        (staging / "kb.json").write_text("done")

    assert (output / "kb.json").read_text() == "done"


def test_an_error_in_the_block_leaves_no_output_and_no_staging_folder(tmp_path: Path) -> None:
    output = tmp_path / "out"

    with pytest.raises(_StopError), new_output_folder(output, ()) as staging:
        _write_one_file_and_fail(staging)

    assert list(tmp_path.iterdir()) == []


def test_an_error_in_the_block_leaves_an_empty_output_empty(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(_StopError), new_output_folder(output, ()) as staging:
        _write_one_file_and_fail(staging)

    assert [path.name for path in tmp_path.iterdir()] == ["out"]
    assert list(output.iterdir()) == []


def test_a_file_that_cannot_be_written_refuses_the_output_and_leaves_nothing(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"

    with pytest.raises(OutputFolderError) as refused, new_output_folder(output, ()) as staging:
        _write_one_file_and_fail_to_write(staging)

    assert refused.value.problem is OutputFolderProblem.NOT_WRITABLE
    assert list(tmp_path.iterdir()) == []


def _hold_a_file(output: Path) -> None:
    output.mkdir()
    (output / "kept").write_text("kept")


def _hold_a_folder(output: Path) -> None:
    (output / "kept").mkdir(parents=True)


def _be_a_file(output: Path) -> None:
    output.write_text("kept")


def _link_to_an_empty_folder(output: Path) -> None:
    # A link would write the files somewhere that the path does not name.
    target = output.parent / "target"
    target.mkdir()
    output.symlink_to(target)


@pytest.mark.parametrize(
    "make_output", [_hold_a_file, _hold_a_folder, _be_a_file, _link_to_an_empty_folder]
)
def test_an_output_that_is_not_a_new_or_empty_folder_is_refused(
    tmp_path: Path, make_output: Callable[[Path], None]
) -> None:
    output = tmp_path / "out"
    make_output(output)

    with pytest.raises(OutputFolderError) as refused, new_output_folder(output, ()):
        pass

    assert refused.value.problem is OutputFolderProblem.NOT_EMPTY


@pytest.mark.parametrize("place", ["data/raw/kb/v9/out", "data/raw/out", "eval/data/raw"])
def test_an_output_in_the_raw_data_is_refused(tmp_path: Path, place: str) -> None:
    with pytest.raises(OutputFolderError) as refused, new_output_folder(tmp_path / place, ()):
        pass

    assert refused.value.problem is OutputFolderProblem.IN_RAW_DATA
    assert not (tmp_path / place).exists()


@pytest.mark.parametrize(
    ("output", "source", "problem"),
    [
        pytest.param(
            "prompts/out", "prompts", OutputFolderProblem.IN_AN_INPUT, id="inside-a-source"
        ),
        pytest.param("prompts", "prompts", OutputFolderProblem.IN_AN_INPUT, id="the-source"),
        # A folder around an input holds that input, so it is not empty.
        pytest.param("all", "all/prompts", OutputFolderProblem.NOT_EMPTY, id="around-a-source"),
    ],
)
def test_an_output_inside_or_around_an_input_is_refused(
    tmp_path: Path, output: str, source: str, problem: OutputFolderProblem
) -> None:
    (tmp_path / source).mkdir(parents=True)

    with (
        pytest.raises(OutputFolderError) as refused,
        new_output_folder(tmp_path / output, (tmp_path / source,)),
    ):
        pass

    assert refused.value.problem is problem
    assert not (tmp_path / "prompts" / "out").exists()


def test_an_output_next_to_an_input_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()

    with new_output_folder(tmp_path / "prompts-copy", (tmp_path / "prompts",)) as staging:
        (staging / "kb.json").write_text("done")

    assert (tmp_path / "prompts-copy" / "kb.json").is_file()


@needs_file_permissions
def test_an_output_folder_that_cannot_be_listed_is_refused(tmp_path: Path) -> None:
    output = tmp_path / "out"
    output.mkdir()
    output.chmod(0)

    try:
        with pytest.raises(OutputFolderError) as refused, new_output_folder(output, ()):
            pass
    finally:
        output.chmod(0o700)

    assert refused.value.problem is OutputFolderProblem.NOT_WRITABLE


@needs_file_permissions
def test_a_parent_that_cannot_be_written_refuses_the_output(tmp_path: Path) -> None:
    parent = tmp_path / "locked"
    parent.mkdir()
    parent.chmod(0o500)

    try:
        with pytest.raises(OutputFolderError) as refused, new_output_folder(parent / "out", ()):
            pass
    finally:
        parent.chmod(0o700)

    assert refused.value.problem is OutputFolderProblem.NOT_WRITABLE

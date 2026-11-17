"""`supportiq-release build-candidate`: everything is checked before the first copy."""

from collections.abc import Callable
from pathlib import Path

import pytest
from supportiq_ai_service.release.manifest import (
    ReleaseInvalidError,
    ReleaseInvalidReason,
    verify_candidate,
)

from supportiq_release.candidate.adapters import candidate_manifest
from supportiq_release.composition_root import cli
from tests.unit.candidate.fakes import (
    RELEASE_ID,
    asset_entries,
    spec_document,
    write_sources,
    write_spec,
)


@pytest.fixture
def records(tmp_path: Path) -> Path:
    folder = tmp_path / "releases"
    folder.mkdir()
    return folder


def _build(spec: Path, records: Path, output: Path) -> int:
    return cli.main(
        [
            "build-candidate",
            "--spec",
            str(spec),
            "--release-records",
            str(records),
            "--output",
            str(output),
        ]
    )


def test_a_candidate_is_built_and_checked(
    tmp_path: Path, records: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = write_spec(write_sources(tmp_path / "sources"))
    output = tmp_path / "candidate"

    status = _build(spec, records, output)

    manifest = output / "release-manifest.json"
    assert status == cli.EXIT_SUCCESS
    assert capsys.readouterr().out == f"release_id={RELEASE_ID} files=10 manifest={manifest}\n"
    assert verify_candidate(manifest).current().versions.release_id == RELEASE_ID
    assert not any(records.iterdir())


def _use_the_release_id(sources: Path, records: Path) -> None:
    del sources
    (records / RELEASE_ID).mkdir()


def _link_a_source(sources: Path, records: Path) -> None:
    del records
    (sources / "kb.json").unlink()
    (sources / "kb.json").symlink_to(sources / "routing.json")


def _break_the_spec(sources: Path, records: Path) -> None:
    del records
    write_spec(sources, {**spec_document(), "release_id": "a release"})


def _remove_the_records(sources: Path, records: Path) -> None:
    del sources
    records.rmdir()


@pytest.mark.parametrize(
    "break_input", [_use_the_release_id, _link_a_source, _break_the_spec, _remove_the_records]
)
def test_an_input_that_cannot_be_used_stops_before_any_copy(
    tmp_path: Path,
    records: Path,
    capsys: pytest.CaptureFixture[str],
    break_input: Callable[[Path, Path], None],
) -> None:
    sources = write_sources(tmp_path / "sources")
    spec = write_spec(sources)
    break_input(sources, records)
    output = tmp_path / "candidate"

    status = _build(spec, records, output)

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err.startswith("The ")
    assert not output.exists()


def test_an_output_folder_that_is_not_empty_is_never_written(tmp_path: Path, records: Path) -> None:
    spec = write_spec(write_sources(tmp_path / "sources"))
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "kept").write_text("kept")

    assert _build(spec, records, output) == cli.EXIT_INPUT_INVALID
    assert [path.name for path in output.iterdir()] == ["kept"]


def test_a_candidate_that_ai_service_refuses_names_the_reason_the_asset_and_the_file(
    tmp_path: Path,
    records: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(manifest: Path) -> None:
        del manifest
        raise ReleaseInvalidError(
            ReleaseInvalidReason.CHECKSUM_MISMATCH, asset="model", file_path="model/x"
        )

    monkeypatch.setattr(candidate_manifest, "verify_candidate", refuse)
    spec = write_spec(write_sources(tmp_path / "sources"))

    status = _build(spec, records, tmp_path / "candidate")

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The release manifest is refused: checksum_mismatch. asset=model file=model/x\n"
    )
    # Nothing that was copied is left: the output is complete or absent.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["releases", "sources"]


def _hide_a_file_in_the_prompts(sources: Path) -> Path:
    (sources / "prompts" / ".DS_Store").write_bytes(b"written by Finder")
    return sources / "candidate"


def _give_the_kb_another_version(sources: Path) -> Path:
    write_spec(sources, spec_document(kb={**asset_entries()["kb"], "version": "v8"}))
    return sources / "candidate"


def _put_the_output_inside_a_source(sources: Path) -> Path:
    return sources / "prompts" / "candidate"


def _put_the_output_in_the_raw_data(sources: Path) -> Path:
    return sources.parent / "data" / "raw" / "candidate"


@pytest.mark.parametrize(
    ("break_input", "message"),
    [
        (
            _hide_a_file_in_the_prompts,
            "The source of asset prompts is refused: hidden_entry.\n",
        ),
        (
            _give_the_kb_another_version,
            "The source of asset kb is refused: version_not_that_of_the_spec.\n",
        ),
        (_put_the_output_inside_a_source, "The output folder is refused: inside_an_input.\n"),
        (_put_the_output_in_the_raw_data, "The output folder is refused: inside_data_raw.\n"),
    ],
)
def test_a_build_that_would_serve_other_files_or_touch_an_input_is_refused(
    tmp_path: Path,
    records: Path,
    capsys: pytest.CaptureFixture[str],
    break_input: Callable[[Path], Path],
    message: str,
) -> None:
    sources = write_sources(tmp_path / "sources")
    spec = write_spec(sources)
    output = break_input(sources)

    status = _build(spec, records, output)

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err == message
    assert not output.exists()

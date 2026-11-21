"""`supportiq-release ingest-kb`: exit statuses, and output without KB text (DATA-13)."""

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_release.composition_root import cli
from tests.unit.kb_ingestion.fakes import BODY, TITLE, record, write_raw_folder

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
INTENT_LABEL_SCHEMA = REPOSITORY_ROOT / "contracts" / "schemas" / "IntentLabel.yaml"
ISSUE = "https://github.com/fake-owner/fake-repository/issues/7"
KEY = ("FAKE-REFUND-001", "1.0")

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root reads every file, whatever its permissions",
)


def _arguments(kb_folder: Path, output: Path, *more: str) -> list[str]:
    return [
        "ingest-kb",
        "--kb-folder",
        str(kb_folder),
        "--intent-labels",
        str(INTENT_LABEL_SCHEMA),
        "--output",
        str(output),
        *more,
    ]


def test_a_run_without_quarantine_succeeds_and_prints_only_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record()])

    status = cli.main(_arguments(folder, tmp_path / "out"))

    assert status == cli.EXIT_SUCCESS
    assert capsys.readouterr().out == (
        "kb_version=v9 admitted=1 quarantined=0 conflicts=0 released_but_absent=0"
        " quarantine=accepted\n"
    )
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "document-intents.json",
        "ingestion-report.json",
        "kb.json",
    ]


def test_a_run_with_quarantine_writes_its_files_and_fails_until_an_issue_accepts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record(policy_key=None)])

    failed = cli.main(_arguments(folder, tmp_path / "first"))
    accepted = cli.main(_arguments(folder, tmp_path / "second", "--accepted-quarantine", ISSUE))

    assert (failed, accepted) == (cli.EXIT_QUARANTINE_NOT_ACCEPTED, cli.EXIT_SUCCESS)
    assert (tmp_path / "first" / "ingestion-report.json").is_file()
    assert capsys.readouterr().out.splitlines() == [
        "kb_version=v9 admitted=0 quarantined=1 conflicts=0 released_but_absent=0"
        " quarantine=not accepted",
        "kb_version=v9 admitted=0 quarantined=1 conflicts=0 released_but_absent=0"
        " quarantine=accepted",
    ]


def test_an_accepted_quarantine_must_name_a_github_issue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record()])

    with pytest.raises(SystemExit) as refused:
        cli.main(_arguments(folder, tmp_path / "out", "--accepted-quarantine", "accepted"))

    assert refused.value.code == cli.EXIT_INPUT_INVALID
    assert "expected the URL of a GitHub issue" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def _remove_the_release_file(folder: Path, labels: Path, output: Path) -> None:
    del labels, output
    (folder / "kb-release.json").unlink()


def _break_the_labels(folder: Path, labels: Path, output: Path) -> None:
    del folder, output
    labels.write_text("type: string\n")


def _fill_the_output(folder: Path, labels: Path, output: Path) -> None:
    del folder, labels
    output.mkdir()
    (output / "kept").write_text("kept")


@pytest.mark.parametrize(
    "break_input", [_remove_the_release_file, _break_the_labels, _fill_the_output]
)
def test_an_input_that_cannot_be_used_stops_with_status_2_and_writes_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    break_input: Callable[[Path, Path, Path], None],
) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    labels = tmp_path / "IntentLabel.yaml"
    labels.write_bytes(INTENT_LABEL_SCHEMA.read_bytes())
    output = tmp_path / "out"
    break_input(folder, labels, output)

    status = cli.main(
        [
            "ingest-kb",
            "--kb-folder",
            str(folder),
            "--intent-labels",
            str(labels),
            "--output",
            str(output),
        ]
    )

    assert status == cli.EXIT_INPUT_INVALID
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.endswith(".\n")
    assert not (output / "kb.json").exists()


def test_a_released_version_that_the_kb_file_lacks_fails_until_an_issue_accepts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record()], released=[KEY, ("FAKE-GONE", "3")])

    status = cli.main(_arguments(folder, tmp_path / "out"))

    assert status == cli.EXIT_QUARANTINE_NOT_ACCEPTED
    assert capsys.readouterr().out == (
        "kb_version=v9 admitted=1 quarantined=0 conflicts=0 released_but_absent=1"
        " quarantine=not accepted\n"
    )


def test_a_text_with_a_lone_surrogate_is_quarantined_and_the_run_still_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record(), record(document_id="FAKE-2", title="a\ud800")])

    status = cli.main(_arguments(folder, tmp_path / "out"))

    assert status == cli.EXIT_QUARANTINE_NOT_ACCEPTED
    assert "quarantined=1" in capsys.readouterr().out
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "document-intents.json",
        "ingestion-report.json",
        "kb.json",
    ]


def test_an_output_in_the_raw_kb_folder_is_refused_and_the_folder_is_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "data" / "raw" / "kb"
    raw.mkdir(parents=True)
    folder = write_raw_folder(raw, [record()])

    status = cli.main(_arguments(folder, folder / "out"))

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The output folder is refused: inside_data_raw.\n"
    assert sorted(path.name for path in folder.iterdir()) == ["fake_kb.json", "kb-release.json"]


def test_a_failure_while_writing_leaves_no_output_and_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def write_one_file_then_fail(output: Path, *arguments: object) -> None:
        del arguments
        (output / "kb.json").write_text("half")
        raise PermissionError

    monkeypatch.setattr(cli, "write_ingestion", write_one_file_then_fail)
    (tmp_path / "raw").mkdir()
    folder = write_raw_folder(tmp_path / "raw", [record()])

    status = cli.main(_arguments(folder, tmp_path / "out" / "v9"))

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The output folder is refused: not_writable.\n"
    assert list((tmp_path / "out").iterdir()) == []


@needs_file_permissions
def test_a_kb_file_that_cannot_be_read_stops_with_status_2_and_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    (folder / "fake_kb.json").chmod(0)

    try:
        status = cli.main(_arguments(folder, tmp_path / "out"))
    finally:
        (folder / "fake_kb.json").chmod(0o600)

    assert status == cli.EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The file fake_kb.json is refused: unreadable.\n"
    assert not (tmp_path / "out").exists()


def test_nothing_that_the_command_prints_holds_kb_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = write_raw_folder(tmp_path, [record(), record(document_id="FAKE-2", content=None)])

    cli.main(_arguments(folder, tmp_path / "out"))

    captured = capsys.readouterr()
    assert TITLE not in captured.out + captured.err
    assert BODY not in captured.out + captured.err


def test_the_command_reads_the_arguments_of_the_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    monkeypatch.setattr(sys, "argv", ["supportiq-release", *_arguments(folder, tmp_path / "out")])

    assert cli.main() == cli.EXIT_SUCCESS

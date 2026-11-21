"""A raw KB folder is read strictly, with the checksum of each file (DATA-06, DATA-12)."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from supportiq_release.files import JsonFileInvalidError, JsonFileProblem, read_json_file
from supportiq_release.kb_ingestion.adapters import (
    KbFolderInvalidError,
    KbFolderProblem,
    content_sha256,
    read_raw_kb_folder,
)
from tests.unit.kb_ingestion.fakes import (
    KB_FILE_NAME,
    KB_VERSION,
    RELEASE_NAME,
    record,
    write_raw_folder,
)

RELEASE_FILE = "kb-release.json"

needs_file_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="root reads every file, whatever its permissions",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_release(folder: Path, release: object) -> None:
    (folder / RELEASE_FILE).write_text(json.dumps(release), encoding="utf-8")


def test_a_folder_gives_its_kb_version_its_released_versions_and_its_records(
    tmp_path: Path,
) -> None:
    folder = write_raw_folder(tmp_path, [record(), record(document_id="FAKE-2")])

    read = read_raw_kb_folder(folder)

    assert (read.kb.kb_version, read.kb.kb_file_name, read.kb_release) == (
        KB_VERSION,
        KB_FILE_NAME,
        RELEASE_NAME,
    )
    assert read.kb.released == {("FAKE-REFUND-001", "1.0"), ("FAKE-2", "1.0")}
    assert [entry["document_id"] for entry in read.kb.records] == ["FAKE-REFUND-001", "FAKE-2"]
    assert [(item.name, item.sha256) for item in read.inputs] == [
        (RELEASE_FILE, _sha256(folder / RELEASE_FILE)),
        (KB_FILE_NAME, _sha256(folder / KB_FILE_NAME)),
    ]


def test_a_folder_whose_name_is_not_a_kb_identifier_is_refused(tmp_path: Path) -> None:
    folder = write_raw_folder(tmp_path, [record()])

    with pytest.raises(KbFolderInvalidError) as refused:
        read_raw_kb_folder(folder.rename(tmp_path / "kb v9"))

    assert refused.value.problem is KbFolderProblem.FOLDER_NAME_INVALID


GOOD_ENTRY = {"document_id": "FAKE-REFUND-001", "version": "1.0"}
GOOD_RELEASE: dict[str, object] = {
    "release": RELEASE_NAME,
    "source": f"data/knowledge/{KB_FILE_NAME}",
    "documents": [GOOD_ENTRY],
}


@pytest.mark.parametrize(
    "release",
    [
        pytest.param([GOOD_RELEASE], id="not-an-object"),
        pytest.param({"release": RELEASE_NAME, "documents": []}, id="no-source"),
        pytest.param({**GOOD_RELEASE, "owner": "fake"}, id="unknown-field"),
        pytest.param({**GOOD_RELEASE, "source": 3}, id="source-not-text"),
        pytest.param({**GOOD_RELEASE, "source": "data/knowledge/"}, id="source-without-file"),
        pytest.param({**GOOD_RELEASE, "source": "kb-release.json"}, id="source-is-itself"),
        pytest.param({**GOOD_RELEASE, "release": "a release name"}, id="release-not-identifier"),
        pytest.param({**GOOD_RELEASE, "documents": {}}, id="documents-not-a-list"),
        pytest.param({**GOOD_RELEASE, "documents": ["FAKE-REFUND-001"]}, id="entry-not-object"),
        pytest.param(
            {**GOOD_RELEASE, "documents": [{**GOOD_ENTRY, "title": "x"}]}, id="entry-unknown-field"
        ),
        pytest.param(
            {**GOOD_RELEASE, "documents": [{**GOOD_ENTRY, "version": 1}]}, id="version-not-text"
        ),
        pytest.param({**GOOD_RELEASE, "documents": [GOOD_ENTRY] * 2}, id="entry-twice"),
    ],
)
def test_a_release_file_of_another_shape_stops_the_run(tmp_path: Path, release: object) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    _write_release(folder, release)

    with pytest.raises(KbFolderInvalidError) as refused:
        read_raw_kb_folder(folder)

    assert refused.value.problem is KbFolderProblem.RELEASE_FILE_INVALID


@pytest.mark.parametrize("content", [{}, [1], [record(), "text"]])
def test_a_kb_file_that_is_not_a_list_of_objects_stops_the_run(
    tmp_path: Path, content: object
) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    (folder / KB_FILE_NAME).write_text(json.dumps(content), encoding="utf-8")

    with pytest.raises(KbFolderInvalidError) as refused:
        read_raw_kb_folder(folder)

    assert refused.value.problem is KbFolderProblem.KB_FILE_INVALID


@pytest.mark.parametrize("missing", [RELEASE_FILE, KB_FILE_NAME])
def test_a_missing_file_stops_the_run_and_names_the_file(tmp_path: Path, missing: str) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    (folder / missing).unlink()

    with pytest.raises(JsonFileInvalidError) as refused:
        read_raw_kb_folder(folder)

    assert (refused.value.file_name, refused.value.problem) == (
        missing,
        JsonFileProblem.NOT_A_REGULAR_FILE,
    )


def test_a_kb_file_that_is_a_link_is_refused(tmp_path: Path) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    target = tmp_path / "elsewhere.json"
    (folder / KB_FILE_NAME).rename(target)
    (folder / KB_FILE_NAME).symlink_to(target)

    with pytest.raises(JsonFileInvalidError) as refused:
        read_raw_kb_folder(folder)

    assert refused.value.problem is JsonFileProblem.NOT_A_REGULAR_FILE


@needs_file_permissions
def test_a_kb_file_that_cannot_be_read_stops_the_run_with_a_typed_error(tmp_path: Path) -> None:
    folder = write_raw_folder(tmp_path, [record()])
    (folder / KB_FILE_NAME).chmod(0)

    try:
        with pytest.raises(JsonFileInvalidError) as refused:
            read_raw_kb_folder(folder)
    finally:
        (folder / KB_FILE_NAME).chmod(0o600)

    assert (refused.value.file_name, refused.value.problem) == (
        KB_FILE_NAME,
        JsonFileProblem.UNREADABLE,
    )


def test_the_checksum_of_a_content_is_its_sha_256_in_utf_8() -> None:
    assert content_sha256("Chính sách hoàn tiền trong 30 ngày") == (
        "37ab0a2c17e416ba34c6d0e8685afe38107a061d3b226d22eac325f53a281e67"
    )


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b'{"a": 1, "a": 2}', id="duplicate-key"),
        pytest.param(b'{"a": NaN}', id="nan"),
        pytest.param(b'{"a": Infinity}', id="infinity"),
        pytest.param(b'{"a": "\xff"}', id="not-utf-8"),
        pytest.param(b'{"a": ', id="not-json"),
    ],
)
def test_a_file_that_is_not_strict_json_in_utf_8_is_refused(tmp_path: Path, data: bytes) -> None:
    path = tmp_path / "file.json"
    path.write_bytes(data)

    with pytest.raises(JsonFileInvalidError) as refused:
        read_json_file(path)

    assert (refused.value.file_name, refused.value.problem) == (
        "file.json",
        JsonFileProblem.NOT_STRICT_JSON,
    )
    assert "\\xff" not in str(refused.value)

"""The three files of a run: KB text only in the KB file, and the same bytes every time."""

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from supportiq_release.kb_ingestion.adapters import (
    content_sha256,
    read_raw_kb_folder,
    write_ingestion,
)
from supportiq_release.kb_ingestion.domain import admit
from tests.unit.kb_ingestion.fakes import (
    BODY,
    KB_FILE_NAME,
    LABELS,
    TITLE,
    record,
    without,
    write_raw_folder,
)

ISSUE = "https://github.com/fake-owner/fake-repository/issues/7"
FILES = ("kb.json", "document-intents.json", "ingestion-report.json")
VIETNAMESE_TITLE = "Chính sách hoàn tiền trong 30 ngày"


def _run(tmp_path: Path, accepted_in: str | None = None) -> Path:
    # Two versions admitted, one open-ended and in conflict with the other; two quarantined,
    # one of them with a document ID that is KB text; and one released version that is absent.
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    folder = write_raw_folder(
        raw,
        [
            record(),
            without(record(document_id="FAKE-OPEN", supported_intents=["track_order"]), "valid_to"),
            record(document_id="FAKE-2", title=""),
            record(document_id="A refund rule text", version=1),
        ],
        released=[
            ("FAKE-REFUND-001", "1.0"),
            ("FAKE-OPEN", "1.0"),
            ("FAKE-2", "1.0"),
            ("GONE", "3"),
        ],
    )
    read = read_raw_kb_folder(folder)
    output = tmp_path / "out"
    output.mkdir()
    write_ingestion(output, read, admit(read.kb, LABELS, content_sha256), accepted_in)
    return output


def _json(path: Path) -> dict[str, object]:
    document: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return cast("dict[str, object]", document)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(document_id: str) -> dict[str, str]:
    return {"document_id": document_id, "version": "1.0"}


def test_the_kb_file_holds_the_admitted_versions_in_the_format_of_ai_service(
    tmp_path: Path,
) -> None:
    output = _run(tmp_path)

    entry = {
        "title": TITLE,
        "body": BODY,
        "policy_key": "fake_refund_window",
        "effective_start_at": "2026-01-01T00:00:00Z",
    }
    origin = {"owner": "fake_policy_owner", "source": f"{KB_FILE_NAME}, KB v9"}
    assert _json(output / "kb.json") == {
        "format": "supportiq-kb/interim-1",
        "kb_version": "v9",
        "documents": [
            # An open-ended version has no `effective_end_at`, never a null one.
            {**_key("FAKE-OPEN"), **entry, **origin},
            {
                **_key("FAKE-REFUND-001"),
                **entry,
                "effective_end_at": "2026-12-31T23:59:59Z",
                **origin,
            },
        ],
    }
    assert _json(output / "document-intents.json") == {
        "format": "supportiq-document-intents/interim-1",
        "version": "v9",
        "kb_version": "v9",
        "documents": [
            {**_key("FAKE-OPEN"), "intents": ["track_order"]},
            {**_key("FAKE-REFUND-001"), "intents": ["request_refund"]},
        ],
    }


def test_the_report_names_versions_reasons_and_checksums_and_no_kb_text(tmp_path: Path) -> None:
    output = _run(tmp_path)
    raw = tmp_path / "raw" / "v9"

    assert _json(output / "ingestion-report.json") == {
        "format": "supportiq-kb-ingestion-report/interim-1",
        "kb_version": "v9",
        "kb_release": "fake-release-1",
        "inputs": [
            {"file": "kb-release.json", "sha256": _sha256(raw / "kb-release.json")},
            {"file": KB_FILE_NAME, "sha256": _sha256(raw / KB_FILE_NAME)},
        ],
        "admitted": [_key("FAKE-OPEN"), _key("FAKE-REFUND-001")],
        "quarantined": [
            {
                "position": 2,
                **_key("FAKE-2"),
                "reasons": [{"code": "invalid_field", "field": "title"}],
            },
            {
                # The document ID and the version are left out: they are not identifiers.
                "position": 3,
                "reasons": [
                    {"code": "invalid_field", "field": "document_id"},
                    {"code": "invalid_field", "field": "version"},
                    {"code": "not_in_release"},
                ],
            },
        ],
        "conflicts": [{"versions": [_key("FAKE-OPEN"), _key("FAKE-REFUND-001")]}],
        "released_but_absent": [{"document_id": "GONE", "version": "3"}],
    }


@pytest.mark.parametrize("name", ["ingestion-report.json", "document-intents.json"])
def test_only_the_kb_file_holds_kb_text(tmp_path: Path, name: str) -> None:
    text = (_run(tmp_path) / name).read_text(encoding="utf-8")

    assert TITLE not in text
    assert BODY not in text
    assert "A refund rule text" not in text


def test_the_report_records_the_issue_that_accepted_the_quarantine(tmp_path: Path) -> None:
    report = _json(_run(tmp_path, accepted_in=ISSUE) / "ingestion-report.json")

    assert report.get("quarantine_accepted_in") == ISSUE


@pytest.mark.parametrize("name", FILES)
def test_each_file_is_indented_json_with_lf_and_a_final_newline(tmp_path: Path, name: str) -> None:
    data = (_run(tmp_path) / name).read_bytes()

    assert data.startswith(b'{\n  "format": ')
    assert data.endswith(b"}\n")
    assert b"\r" not in data


def test_the_same_input_gives_the_same_bytes(tmp_path: Path) -> None:
    first, second = _run(tmp_path / "first"), _run(tmp_path / "second")

    assert [(first / name).read_bytes() for name in FILES] == [
        (second / name).read_bytes() for name in FILES
    ]


def test_a_text_outside_ascii_is_written_as_is_in_utf_8(tmp_path: Path) -> None:
    read = read_raw_kb_folder(write_raw_folder(tmp_path, [record(title=VIETNAMESE_TITLE)]))
    output = tmp_path / "out"
    output.mkdir()

    write_ingestion(output, read, admit(read.kb, LABELS, content_sha256), None)

    assert f'"title": "{VIETNAMESE_TITLE}"'.encode() in (output / "kb.json").read_bytes()


def test_a_file_is_never_written_over_another(tmp_path: Path) -> None:
    read = read_raw_kb_folder(write_raw_folder(tmp_path, [record()]))
    output = tmp_path / "out"
    output.mkdir()
    (output / "kb.json").write_text("kept")

    with pytest.raises(FileExistsError):
        write_ingestion(output, read, admit(read.kb, LABELS, content_sha256), None)

    assert (output / "kb.json").read_text() == "kept"

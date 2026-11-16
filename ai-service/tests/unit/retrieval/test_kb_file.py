"""The KB of a release holds only versions with every field of `KbDocumentVersion` (DATA-16)."""

import copy
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from supportiq_ai_service.retrieval import KbDocument
from supportiq_ai_service.retrieval.adapters.kb_file import read_kb_documents
from tests.unit.release.release_folder import (
    KB_DOCUMENT,
    KB_ENTRY,
    AssetFileChanges,
    JsonDocument,
    asset_refusal,
    json_file,
    verified_release,
)

KB_PATH = "kb/kb.json"


def _kb_with(*entries: JsonDocument) -> AssetFileChanges:
    return {"kb": {KB_PATH: json_file({**KB_DOCUMENT, "documents": list(entries)})}}


def _entry(change: Callable[[JsonDocument], None]) -> AssetFileChanges:
    entry = copy.deepcopy(KB_ENTRY)
    change(entry)
    return _kb_with(entry)


def test_the_first_release_holds_no_kb_document(tmp_path: Path) -> None:
    assert read_kb_documents(verified_release(tmp_path).asset_files("kb")) == ()


def test_a_kb_document_version_is_read_with_its_metadata(tmp_path: Path) -> None:
    reviewed = {**KB_ENTRY, "last_reviewed_at": "2026-10-01T08:00:00.5Z"}

    (document,) = read_kb_documents(
        verified_release(tmp_path, _kb_with(reviewed)).asset_files("kb")
    )

    assert document == KbDocument(
        document_id="SAMPLE-REFUND-001",
        version="1.0",
        title=KB_ENTRY["title"],
        body=KB_ENTRY["body"],
        policy_key="refund_window",
        effective_start_at=datetime(2026, 1, 1, tzinfo=UTC),
        effective_end_at=datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
        owner="policy_owner",
        source=KB_ENTRY["source"],
        last_reviewed_at=datetime(2026, 10, 1, 8, 0, 0, 500_000, tzinfo=UTC),
    )


def test_a_version_without_an_end_is_open_ended(tmp_path: Path) -> None:
    open_ended = {key: value for key, value in KB_ENTRY.items() if key != "effective_end_at"}

    (document,) = read_kb_documents(
        verified_release(tmp_path, _kb_with(open_ended)).asset_files("kb")
    )

    assert document.effective_end_at is None
    assert document.last_reviewed_at is None


# Each way to break the KB file; every refusal names the KB file but the last.
KB_BREAKS: dict[str, AssetFileChanges] = {
    "another KB version": {
        "kb": {KB_PATH: json_file({**KB_DOCUMENT, "kb_version": "kb-sample-2"})}
    },
    "another format": {
        "kb": {KB_PATH: json_file({**KB_DOCUMENT, "format": "supportiq-kb/interim-2"})}
    },
    "no owner": _entry(lambda entry: entry.pop("owner")),
    "no source": _entry(lambda entry: entry.pop("source")),
    "no policy key": _entry(lambda entry: entry.pop("policy_key")),
    "an empty title": _entry(lambda entry: entry.update(title="")),
    "a title too long": _entry(lambda entry: entry.update(title="t" * 201)),
    "an identifier with a space": _entry(lambda entry: entry.update(document_id="SAMPLE 1")),
    "a time with an offset": _entry(
        lambda entry: entry.update(effective_start_at="2026-01-01T00:00:00+07:00")
    ),
    "a time without a zone": _entry(
        lambda entry: entry.update(effective_start_at="2026-01-01T00:00:00")
    ),
    "an end before the start": _entry(
        lambda entry: entry.update(effective_end_at="2025-12-31T00:00:00Z")
    ),
    "an end at the start": _entry(
        lambda entry: entry.update(effective_end_at=KB_ENTRY["effective_start_at"])
    ),
    "an unknown field": _entry(lambda entry: entry.update(supported_intents=[])),
    "a version twice": _kb_with(KB_ENTRY, KB_ENTRY),
    "a second file": {"kb": {"kb/kb-extra.json": json_file(KB_DOCUMENT)}},
}


@pytest.mark.parametrize("name", sorted(KB_BREAKS))
def test_a_kb_that_breaks_its_format_is_refused(tmp_path: Path, name: str) -> None:
    files = verified_release(tmp_path, KB_BREAKS[name]).asset_files("kb")

    error = asset_refusal(lambda: read_kb_documents(files))

    assert (error.asset, error.file_path) == ("kb", None if name == "a second file" else KB_PATH)

"""Builders of raw KB records and folders, with synthetic text only (TEST-18).

`record()` is a valid record of a KB file in the shape of KB v2, with a field that ingestion
does not read. Its `content_hash` is the SHA-256 of its `content`, unless a test sets it. A raw
KB lists every record that a test gives it, unless the test names the released versions
itself.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TypeIs

from supportiq_release.kb_ingestion.domain import DocumentVersionKey, RawKb

LABELS = frozenset({"track_order", "request_refund", "refund_policy"})
KB_VERSION = "v9"
KB_FILE_NAME = "fake_kb.json"
RELEASE_NAME = "fake-release-1"
TITLE = "A fake refund rule"
BODY = "A fake rule about refunds, written for tests only."


def sha256_text(text: str) -> str:
    """Return the SHA-256 of a text in UTF-8, as `admit` expects of its digest.

    Args:
        text: A text that UTF-8 can hold.

    Returns:
        The checksum, in lowercase hexadecimal.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record(**changes: object) -> dict[str, object]:
    """Return a valid record of a KB file, with some fields changed.

    Args:
        **changes: The fields to change or add.

    Returns:
        The record, with the checksum of its content unless `changes` sets one.
    """
    entry: dict[str, object] = {
        "document_id": "FAKE-REFUND-001",
        "version": "1.0",
        "title": TITLE,
        "content": BODY,
        "policy_key": "fake_refund_window",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2026-12-31T23:59:59Z",
        "approved_by": "fake_policy_owner",
        "supported_intents": ["request_refund"],
        "status": "draft",
        **changes,
    }
    content = entry.get("content")
    entry.setdefault("content_hash", sha256_text(content if _encodes(content) else BODY))
    return entry


def _encodes(value: object) -> TypeIs[str]:
    # A content that UTF-8 cannot hold, such as a lone surrogate, has no checksum of its own.
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def without(entry: Mapping[str, object], name: str) -> dict[str, object]:
    """Return a copy of a record without one field.

    Args:
        entry: The record.
        name: The field to leave out.

    Returns:
        The copy.
    """
    return {key: value for key, value in entry.items() if key != name}


def released_keys(records: Iterable[Mapping[str, object]]) -> frozenset[DocumentVersionKey]:
    """Return the pairs of the records whose document ID and version are texts.

    Args:
        records: The records.

    Returns:
        The pairs.
    """
    keys: set[DocumentVersionKey] = set()
    for entry in records:
        document_id, version = entry.get("document_id"), entry.get("version")
        if isinstance(document_id, str) and isinstance(version, str):
            keys.add((document_id, version))
    return frozenset(keys)


def raw_kb(
    *records: Mapping[str, object], released: Iterable[DocumentVersionKey] | None = None
) -> RawKb:
    """Return a raw KB of the records.

    Args:
        *records: The records of the KB file.
        released: The released versions; the pairs of the records when None.

    Returns:
        The raw KB.
    """
    return RawKb(
        kb_version=KB_VERSION,
        kb_file_name=KB_FILE_NAME,
        released=released_keys(records) if released is None else frozenset(released),
        records=records,
    )


def write_raw_folder(
    parent: Path,
    records: Iterable[Mapping[str, object]],
    released: Iterable[DocumentVersionKey] | None = None,
) -> Path:
    """Write a raw KB folder, `<parent>/v9/`, with its release file and its KB file.

    Args:
        parent: An empty folder.
        records: The records of the KB file.
        released: The released versions; the pairs of the records when None.

    Returns:
        The raw KB folder.
    """
    entries = list(records)
    keys = released_keys(entries) if released is None else frozenset(released)
    folder = parent / KB_VERSION
    folder.mkdir()
    release = {
        "release": RELEASE_NAME,
        "source": f"data/knowledge/{KB_FILE_NAME}",
        "documents": [{"document_id": key[0], "version": key[1]} for key in sorted(keys)],
    }
    (folder / "kb-release.json").write_text(json.dumps(release), encoding="utf-8")
    (folder / KB_FILE_NAME).write_text(json.dumps(entries), encoding="utf-8")
    return folder

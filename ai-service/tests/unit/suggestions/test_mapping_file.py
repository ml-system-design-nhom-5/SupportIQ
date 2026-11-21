"""The document-to-intent mapping names intents of the KB document versions of its release."""

from pathlib import Path

import pytest

from app.retrieval.adapters.kb_file import read_kb_documents
from app.suggestions.adapters.mapping_file import read_document_intents
from app.suggestions.domain import IntentName
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    KB_DOCUMENT,
    KB_ENTRY,
    MAPPING_DOCUMENT,
    AssetFileChanges,
    JsonDocument,
    asset_refusal,
    json_file,
    verified_release,
)

MAPPING_PATH = "mapping/document-intents.json"
KB_VERSION = EXAMPLE_VERSIONS.kb_version
REFUND_ENTRY: JsonDocument = {
    "document_id": KB_ENTRY["document_id"],
    "version": KB_ENTRY["version"],
    "intents": ["request_refund", "refund_policy"],
}


def _release_with(*entries: JsonDocument, **fields: object) -> AssetFileChanges:
    return {
        "kb": {"kb/kb.json": json_file({**KB_DOCUMENT, "documents": [KB_ENTRY]})},
        "mapping": {
            MAPPING_PATH: json_file({**MAPPING_DOCUMENT, "documents": list(entries), **fields})
        },
    }


def test_the_mapping_names_the_intents_of_each_document_version(tmp_path: Path) -> None:
    source = verified_release(tmp_path, _release_with(REFUND_ENTRY))
    kb_documents = read_kb_documents(source.asset_files("kb"))

    mapping = read_document_intents(source.asset_files("mapping"), KB_VERSION, kb_documents)

    assert mapping.intents_of("SAMPLE-REFUND-001", "1.0") == {
        IntentName("request_refund"),
        IntentName("refund_policy"),
    }
    assert mapping.intents_of("SAMPLE-REFUND-001", "2.0") == frozenset()


def test_the_mapping_of_the_first_release_names_no_document(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("mapping")

    assert read_document_intents(files, KB_VERSION, ()).intents_by_document == {}


def test_a_mapping_built_from_another_kb_version_is_refused(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("mapping")

    error = asset_refusal(lambda: read_document_intents(files, "kb-sample-2", ()))

    assert (error.asset, error.file_path) == ("mapping", MAPPING_PATH)


# Each way to break the mapping; every refusal names the mapping file.
MAPPING_BREAKS: dict[str, AssetFileChanges] = {
    "another mapping version": _release_with(version="mapping-sample-2"),
    "a document version outside the KB": _release_with({**REFUND_ENTRY, "version": "2.0"}),
    "an unknown intent": _release_with({**REFUND_ENTRY, "intents": ["refund_now"]}),
    "no intent": _release_with({**REFUND_ENTRY, "intents": []}),
    "an intent twice": _release_with(
        {**REFUND_ENTRY, "intents": ["request_refund", "request_refund"]}
    ),
    "a version twice": _release_with(REFUND_ENTRY, REFUND_ENTRY),
    "an unknown field": _release_with({**REFUND_ENTRY, "weight": 1}),
}


@pytest.mark.parametrize("name", sorted(MAPPING_BREAKS))
def test_a_mapping_that_breaks_its_format_is_refused(tmp_path: Path, name: str) -> None:
    source = verified_release(tmp_path, MAPPING_BREAKS[name])
    kb_documents = read_kb_documents(source.asset_files("kb"))
    files = source.asset_files("mapping")

    error = asset_refusal(lambda: read_document_intents(files, KB_VERSION, kb_documents))

    assert (error.asset, error.file_path) == ("mapping", MAPPING_PATH)

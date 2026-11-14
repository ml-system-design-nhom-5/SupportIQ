"""Only the document versions of the loaded KB are served (UI-20, DATA-56)."""

import json
from pathlib import Path

import pytest

from supportiq_ai_service.platform import ResourceNotFoundError
from supportiq_ai_service.platform.web import render_json
from supportiq_ai_service.release import ReleaseNotLoadedError
from supportiq_ai_service.retrieval import GetKbDocumentVersion
from supportiq_ai_service.retrieval.api import kb_document_body
from tests.unit.release.fakes import StaticReleaseSource
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT, StaticKbDocuments

EXAMPLE = Path(__file__).parents[4] / "contracts/examples/getKbDocumentVersion/found.json"


def test_a_version_of_the_loaded_kb_is_found() -> None:
    use_case = GetKbDocumentVersion(StaticReleaseSource(), StaticKbDocuments())

    assert use_case.execute("SAMPLE-REFUND-001", "1.0") == EXAMPLE_DOCUMENT


@pytest.mark.parametrize(
    ("document_id", "version"), [("SAMPLE-REFUND-001", "0.9"), ("UNKNOWN-001", "1.0")]
)
def test_a_version_outside_the_loaded_kb_is_not_found(document_id: str, version: str) -> None:
    use_case = GetKbDocumentVersion(StaticReleaseSource(), StaticKbDocuments())

    with pytest.raises(ResourceNotFoundError):
        use_case.execute(document_id, version)


def test_without_a_loaded_release_no_document_is_served() -> None:
    use_case = GetKbDocumentVersion(StaticReleaseSource(release=None), StaticKbDocuments())

    with pytest.raises(ReleaseNotLoadedError):
        use_case.execute("SAMPLE-REFUND-001", "1.0")


def test_the_document_version_is_the_contract_example() -> None:
    body = json.loads(render_json(kb_document_body(EXAMPLE_DOCUMENT)))

    assert body == json.loads(EXAMPLE.read_text(encoding="utf-8"))["value"]

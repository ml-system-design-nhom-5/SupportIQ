"""`getKbDocumentVersion` finds the document versions of the KB of the loaded release."""

import dataclasses

from supportiq_ai_service.retrieval.adapters.release_kb import ReleaseKbDocuments
from tests.unit.release.fakes import EXAMPLE_RELEASE
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT

EARLIER = dataclasses.replace(EXAMPLE_DOCUMENT, version="0.9")


def test_a_version_of_the_kb_is_found() -> None:
    documents = ReleaseKbDocuments([EXAMPLE_DOCUMENT, EARLIER])

    assert documents.find("SAMPLE-REFUND-001", "0.9", EXAMPLE_RELEASE) == EARLIER
    assert documents.find("SAMPLE-REFUND-001", "1.0", EXAMPLE_RELEASE) == EXAMPLE_DOCUMENT


def test_a_version_outside_the_kb_is_not_found() -> None:
    documents = ReleaseKbDocuments([EXAMPLE_DOCUMENT])

    assert documents.find("SAMPLE-REFUND-001", "2.0", EXAMPLE_RELEASE) is None
    assert ReleaseKbDocuments([]).find("SAMPLE-REFUND-001", "1.0", EXAMPLE_RELEASE) is None

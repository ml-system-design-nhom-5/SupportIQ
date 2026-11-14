"""In-memory fakes of the retrieval ports (ARCH-27).

`EXAMPLE_DOCUMENT` is `contracts/examples/getKbDocumentVersion/found.json`.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.retrieval import KbDocument

EXAMPLE_DOCUMENT = KbDocument(
    document_id="SAMPLE-REFUND-001",
    version="1.0",
    title="Sample refund document",
    body=(
        "This is sample text. It is not KB content and not a policy. The document version "
        "opens here in full, so staff can check a citation against its source."
    ),
    policy_key="sample_refund_review",
    effective_start_at=datetime(2026, 1, 1, tzinfo=UTC),
    effective_end_at=None,
    owner="Policy owner",
    source="Sample source document",
    last_reviewed_at=None,
)


def _example_documents() -> Mapping[tuple[str, str], KbDocument]:
    key = (EXAMPLE_DOCUMENT.document_id, EXAMPLE_DOCUMENT.version)
    return MappingProxyType({key: EXAMPLE_DOCUMENT})


@dataclass(frozen=True, slots=True)
class StaticKbDocuments:
    """A KB whose document versions a test chooses, by document ID and version."""

    documents: Mapping[tuple[str, str], KbDocument] = field(default_factory=_example_documents)

    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        """Return the chosen document version, or None.

        Args:
            document_id: The document.
            version: The version of the document.
            release: The loaded release.
        """
        del release
        return self.documents.get((document_id, version))

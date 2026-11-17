"""Read what the gate compares with `written_for`: the versions and the KB size of a candidate.

The candidate is checked with `verify_candidate` of `ai-service` first, so its manifest and every
file it names are those that the run loads (DATA-56). The KB file is read in its interim format,
`supportiq-kb/interim-1`, which KB ingestion writes, only to count its document versions.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from supportiq_ai_service.release.manifest import verify_candidate

from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import read_json_file
from supportiq_release.gate.domain import CONTRACT_VERSION, WrittenFor


class CandidateKbInvalidError(ReleaseCommandError):
    """The KB asset of a candidate is not one file that holds a list of documents."""

    def __init__(self) -> None:
        """Build the error with its fixed message."""
        super().__init__("The KB of the candidate is refused: not_one_file_with_documents.")


@dataclass(frozen=True, slots=True)
class CandidateFacts:
    """What the gate knows of a checked candidate before it runs it.

    Attributes:
        manifest_path: The manifest file of the candidate.
        manifest_sha256: The SHA-256 of the manifest file.
        release_id: The ID of the candidate.
        release: The versions, the KB size, and the contract that the gate reads it with.
    """

    manifest_path: Path
    manifest_sha256: str
    release_id: str
    release: WrittenFor


def read_candidate_facts(candidate: Path) -> CandidateFacts:
    """Check a candidate, and read its versions and the number of its KB document versions.

    Args:
        candidate: The folder of the candidate.

    Returns:
        The facts of the candidate.

    Raises:
        ReleaseInvalidError: `ai-service` refuses the candidate.
        JsonFileInvalidError: The manifest or the KB file is not strict JSON.
        CandidateKbInvalidError: The KB file holds no list of documents.
    """
    manifest_path = candidate / MANIFEST_FILE_NAME
    manifest_file = read_json_file(manifest_path)
    source = verify_candidate(manifest_path)
    versions = source.manifest.asset_versions()
    kb_files = source.asset_files("kb").files
    if len(kb_files) != 1:
        raise CandidateKbInvalidError
    content = read_json_file(kb_files[0].location).content
    # The casts only name the types that `isinstance` found in a JSON value (PY-12).
    fields = cast("dict[str, object]", content) if isinstance(content, dict) else {}
    documents = fields.get("documents")
    if not isinstance(documents, list):
        raise CandidateKbInvalidError
    return CandidateFacts(
        manifest_path=manifest_path,
        manifest_sha256=manifest_file.sha256,
        release_id=versions.release_id,
        release=WrittenFor(
            ai_service_contract=CONTRACT_VERSION,
            model_version=versions.model_version,
            routing_version=versions.routing_version,
            kb_version=versions.kb_version,
            kb_document_count=len(cast("list[object]", documents)),
        ),
    )

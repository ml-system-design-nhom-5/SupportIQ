"""Write the KB, the document-to-intent mapping, and the report of one ingestion run.

The KB file and the mapping file use the interim formats that `ai-service` reads
(`ai-service/README.md`, Asset formats): `supportiq-kb/interim-1` and
`supportiq-document-intents/interim-1`. A data contract in `contracts/` replaces them
(ADR-0021, Follow-ups). The mapping takes the version of the KB, because ingestion derives it
from that KB alone.

Only the KB file holds text of the KB. The mapping holds identifiers and intents, and the
report holds identifiers, versions, checksums, and reasons (DATA-13).
"""

from pathlib import Path

from supportiq_release.files import write_json_file
from supportiq_release.kb_ingestion.adapters.raw_kb_folder import RawKbFolder
from supportiq_release.kb_ingestion.domain import (
    AdmittedVersion,
    DocumentVersionKey,
    IngestionResult,
    QuarantinedRecord,
)

KB_FORMAT = "supportiq-kb/interim-1"
MAPPING_FORMAT = "supportiq-document-intents/interim-1"
REPORT_FORMAT = "supportiq-kb-ingestion-report/interim-1"
KB_FILE_NAME = "kb.json"
MAPPING_FILE_NAME = "document-intents.json"
REPORT_FILE_NAME = "ingestion-report.json"


def write_ingestion(
    output: Path, folder: RawKbFolder, result: IngestionResult, accepted_in: str | None
) -> None:
    """Write the three files of one ingestion run into an empty folder.

    Args:
        output: The staging folder of `new_output_folder`.
        folder: The raw KB folder that was ingested.
        result: What ingestion made of it.
        accepted_in: The issue that accepted the quarantine, or None (DATA-13).

    Raises:
        OSError: A file cannot be written; `new_output_folder` then removes the folder.
    """
    write_json_file(output / KB_FILE_NAME, _kb_document(result))
    write_json_file(output / MAPPING_FILE_NAME, _mapping_document(result))
    write_json_file(output / REPORT_FILE_NAME, _report_document(folder, result, accepted_in))


def _kb_document(result: IngestionResult) -> dict[str, object]:
    return {
        "format": KB_FORMAT,
        "kb_version": result.kb_version,
        "documents": [_kb_entry(version) for version in result.admitted],
    }


def _kb_entry(version: AdmittedVersion) -> dict[str, object]:
    # `effective_end_at` is left out for an open-ended version, never written as null.
    end = {} if version.effective_end_at is None else {"effective_end_at": version.effective_end_at}
    return {
        "document_id": version.document_id,
        "version": version.version,
        "title": version.title,
        "body": version.body,
        "policy_key": version.policy_key,
        "effective_start_at": version.effective_start_at,
        **end,
        "owner": version.owner,
        "source": version.source,
    }


def _mapping_document(result: IngestionResult) -> dict[str, object]:
    return {
        "format": MAPPING_FORMAT,
        "version": result.kb_version,
        "kb_version": result.kb_version,
        "documents": [
            {**_key_entry(version.key), "intents": list(version.intents)}
            for version in result.admitted
        ],
    }


def _report_document(
    folder: RawKbFolder, result: IngestionResult, accepted_in: str | None
) -> dict[str, object]:
    accepted = {} if accepted_in is None else {"quarantine_accepted_in": accepted_in}
    return {
        "format": REPORT_FORMAT,
        "kb_version": result.kb_version,
        "kb_release": folder.kb_release,
        "inputs": [{"file": item.name, "sha256": item.sha256} for item in folder.inputs],
        "admitted": [_key_entry(version.key) for version in result.admitted],
        "quarantined": [_quarantine_entry(record) for record in result.quarantined],
        "conflicts": [
            {"versions": [_key_entry(conflict.first), _key_entry(conflict.second)]}
            for conflict in result.conflicts
        ],
        "released_but_absent": [_key_entry(key) for key in result.released_but_absent],
        **accepted,
    }


def _key_entry(key: DocumentVersionKey) -> dict[str, object]:
    return {"document_id": key[0], "version": key[1]}


def _quarantine_entry(record: QuarantinedRecord) -> dict[str, object]:
    # An identifier that is not valid is left out, because its value could hold KB text.
    identifiers = {
        name: value
        for name, value in (("document_id", record.document_id), ("version", record.version))
        if value is not None
    }
    return {
        "position": record.position,
        **identifiers,
        "reasons": [
            {
                "code": reason.code.value,
                **({} if reason.field is None else {"field": reason.field.value}),
            }
            for reason in record.reasons
        ],
    }

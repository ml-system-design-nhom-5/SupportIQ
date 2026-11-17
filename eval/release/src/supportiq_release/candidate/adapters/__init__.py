"""The files of a candidate release: its spec, its copied assets, and its manifest."""

from supportiq_release.candidate.adapters.asset_sources import (
    CopiedFile,
    PlannedCopy,
    SourceInvalidError,
    SourceProblem,
    copy_files,
    plan_copies,
)
from supportiq_release.candidate.adapters.candidate_manifest import write_candidate_manifest
from supportiq_release.candidate.adapters.kb_sources import check_kb_versions
from supportiq_release.candidate.adapters.release_records import (
    ReleaseIdNotFreeError,
    ReleaseIdProblem,
    check_release_id_free,
)
from supportiq_release.candidate.adapters.spec_file import SPEC_FORMAT, read_release_spec

__all__ = [
    "SPEC_FORMAT",
    "CopiedFile",
    "PlannedCopy",
    "ReleaseIdNotFreeError",
    "ReleaseIdProblem",
    "SourceInvalidError",
    "SourceProblem",
    "check_kb_versions",
    "check_release_id_free",
    "copy_files",
    "plan_copies",
    "read_release_spec",
    "write_candidate_manifest",
]

"""Check that the KB and the mapping of a spec are files of the versions that the spec names.

`verify_candidate` checks the bytes of a candidate, not the formats of its assets. `ai-service`
refuses a KB file whose `kb_version` is not the version of its asset, and a mapping whose
`version` or `kb_version` is not the version of its asset or of the KB
(`retrieval/adapters/kb_file.py`, `suggestions/adapters/mapping_file.py`). So the command reads
these fields of the two interim formats before any copy, and a spec that names other versions
stops the build. The gate checks the rest of each format when it loads the candidate.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from supportiq_release.candidate.adapters.asset_sources import SourceInvalidError, SourceProblem
from supportiq_release.candidate.domain import AssetName, AssetSpec, ReleaseSpec
from supportiq_release.files import read_json_file


def check_kb_versions(spec: ReleaseSpec, base: Path) -> None:
    """Refuse a KB or a mapping whose versions are not those of the spec.

    Args:
        spec: The checked spec.
        base: The folder that the sources are relative to.

    Raises:
        SourceInvalidError: The source of the KB or of the mapping is not one file, or names
            another version.
        JsonFileInvalidError: That file is unreadable or not strict JSON in UTF-8.
    """
    by_name = {asset.name: asset for asset in spec.assets}
    kb, mapping = by_name[AssetName.KB], by_name[AssetName.MAPPING]
    _require_versions(kb, base, {"kb_version": kb.version})
    _require_versions(mapping, base, {"version": mapping.version, "kb_version": kb.version})


def _require_versions(asset: AssetSpec, base: Path, expected: Mapping[str, str]) -> None:
    source = base / asset.source
    if not source.is_file():
        raise SourceInvalidError(SourceProblem.FILE_EXPECTED, asset.name)
    content = read_json_file(source).content
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    fields = cast("dict[str, object]", content) if isinstance(content, dict) else {}
    if any(fields.get(name) != version for name, version in expected.items()):
        raise SourceInvalidError(SourceProblem.VERSION_MISMATCH, asset.name)

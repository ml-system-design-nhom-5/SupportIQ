"""The KB and the mapping of a spec are files of the versions that it names (S4)."""

from pathlib import Path

import pytest

from supportiq_release.candidate.adapters import (
    SourceInvalidError,
    SourceProblem,
    check_kb_versions,
    read_release_spec,
)
from supportiq_release.candidate.domain import AssetName
from tests.unit.candidate.fakes import asset_entries, spec_document, write_sources, write_spec

ENTRIES = asset_entries()


def _check(base: Path, document: dict[str, object] | None = None) -> None:
    check_kb_versions(read_release_spec(write_spec(base, document)), base)


def test_a_kb_and_a_mapping_of_the_versions_of_the_spec_pass(tmp_path: Path) -> None:
    _check(write_sources(tmp_path))


@pytest.mark.parametrize(
    ("document", "asset"),
    [
        pytest.param(
            spec_document(kb={**ENTRIES["kb"], "version": "v8"}), AssetName.KB, id="kb-version"
        ),
        pytest.param(
            spec_document(mapping={**ENTRIES["mapping"], "version": "map-1"}),
            AssetName.MAPPING,
            id="mapping-version",
        ),
    ],
)
def test_a_spec_that_names_other_versions_than_its_files_stops_the_build(
    tmp_path: Path, document: dict[str, object], asset: AssetName
) -> None:
    base = write_sources(tmp_path)

    with pytest.raises(SourceInvalidError) as refused:
        _check(base, document)

    assert (refused.value.problem, refused.value.asset) == (SourceProblem.VERSION_MISMATCH, asset)


@pytest.mark.parametrize(
    ("data", "asset"),
    [
        pytest.param(
            b'{"version": "v9", "kb_version": "v8"}', AssetName.MAPPING, id="mapping-of-another-kb"
        ),
        pytest.param(b'{"version": "v9"}', AssetName.MAPPING, id="mapping-without-kb-version"),
        pytest.param(b'["v9"]', AssetName.MAPPING, id="mapping-not-an-object"),
    ],
)
def test_a_mapping_of_another_kb_version_stops_the_build(
    tmp_path: Path, data: bytes, asset: AssetName
) -> None:
    base = write_sources(tmp_path)
    (base / "document-intents.json").write_bytes(data)

    with pytest.raises(SourceInvalidError) as refused:
        _check(base)

    assert (refused.value.problem, refused.value.asset) == (SourceProblem.VERSION_MISMATCH, asset)


def test_a_kb_source_that_is_a_folder_stops_the_build(tmp_path: Path) -> None:
    base = write_sources(tmp_path)
    (base / "kb").mkdir()
    (base / "kb" / "kb.json").write_bytes((base / "kb.json").read_bytes())

    with pytest.raises(SourceInvalidError) as refused:
        _check(base, spec_document(kb={**ENTRIES["kb"], "source": "kb", "path": "kb"}))

    assert (refused.value.problem, refused.value.asset) == (
        SourceProblem.FILE_EXPECTED,
        AssetName.KB,
    )

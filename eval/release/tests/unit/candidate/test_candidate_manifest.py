"""The manifest of a candidate passes the check of ai-service, and serve refuses it (DATA-57)."""

import json
from pathlib import Path

import pytest
from supportiq_ai_service.release.manifest import (
    ReleaseInvalidError,
    ReleaseInvalidReason,
    verify_candidate,
    verify_release,
)

from supportiq_release.candidate.adapters import (
    copy_files,
    plan_copies,
    read_release_spec,
    write_candidate_manifest,
)
from tests.unit.candidate.fakes import (
    MODEL_VERSION,
    RELEASE_FILES,
    RELEASE_ID,
    write_sources,
    write_spec,
)


def _build(tmp_path: Path) -> Path:
    base = write_sources(tmp_path / "sources")
    spec = read_release_spec(write_spec(base))
    output = tmp_path / "release"
    output.mkdir()
    return write_candidate_manifest(output, spec, copy_files(plan_copies(spec, base), output))


def test_the_candidate_passes_the_check_of_ai_service_with_the_versions_of_the_spec(
    tmp_path: Path,
) -> None:
    manifest = _build(tmp_path)

    versions = verify_candidate(manifest).current().versions

    assert (versions.release_id, versions.model_version, versions.kb_version) == (
        RELEASE_ID,
        MODEL_VERSION,
        "v9",
    )
    assert (versions.prompt_version, versions.routing_version, versions.index_version) == (
        "fake-prompts-1",
        "fake-routing-1",
        "fake-index-1",
    )


def test_the_manifest_lists_every_file_and_links_no_gate_run(tmp_path: Path) -> None:
    manifest = _build(tmp_path)

    document = json.loads(manifest.read_text(encoding="utf-8"))

    assert document["gate_run"] is None
    assert list(document["assets"]) == ["model", "kb", "mapping", "prompts", "routing", "index"]
    assert document["assets"]["routing"]["model_version"] == MODEL_VERSION
    listed = sorted(
        entry["path"] for asset in document["assets"].values() for entry in asset["files"]
    )
    assert listed == sorted(RELEASE_FILES.values())
    # Every entry of the folder: the listed files, their folders, and the manifest.
    assert sorted(
        path.relative_to(manifest.parent).as_posix() for path in manifest.parent.rglob("*")
    ) == sorted(
        [
            *RELEASE_FILES.values(),
            "index",
            "index/encoder",
            "kb",
            "mapping",
            "model",
            "prompts",
            "release-manifest.json",
            "routing",
        ]
    )


def test_a_candidate_is_never_served(tmp_path: Path) -> None:
    manifest = _build(tmp_path)

    with pytest.raises(ReleaseInvalidError) as refused:
        verify_release(manifest)

    assert refused.value.reason is ReleaseInvalidReason.GATE_RUN_MISSING


def test_one_changed_byte_refuses_the_candidate(tmp_path: Path) -> None:
    manifest = _build(tmp_path)
    weights = manifest.parent / "model" / "model.safetensors"
    data = bytearray(weights.read_bytes())
    data[0] ^= 1
    weights.write_bytes(bytes(data))

    with pytest.raises(ReleaseInvalidError) as refused:
        verify_candidate(manifest)

    assert (refused.value.reason, refused.value.asset, refused.value.file_path) == (
        ReleaseInvalidReason.CHECKSUM_MISMATCH,
        "model",
        "model/model.safetensors",
    )

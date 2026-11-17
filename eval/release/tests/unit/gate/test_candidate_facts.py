"""The facts of a candidate come from `verify_candidate` and the count of its KB versions."""

import hashlib
import json
from pathlib import Path

import pytest
from supportiq_ai_service.release.manifest import ReleaseInvalidError

from supportiq_release.candidate.adapters import (
    copy_files,
    plan_copies,
    read_release_spec,
    write_candidate_manifest,
)
from supportiq_release.files import JsonFileInvalidError
from supportiq_release.gate.adapters import CandidateKbInvalidError, read_candidate_facts
from supportiq_release.gate.domain import WrittenFor
from tests.unit.candidate.fakes import RELEASE_ID, asset_entries, spec_document, write_sources
from tests.unit.gate.fakes import build_fake_candidate

KB = {"format": "supportiq-kb/interim-1", "kb_version": "v9"}


def test_the_facts_are_the_versions_and_the_kb_size_of_the_candidate(tmp_path: Path) -> None:
    candidate = build_fake_candidate(tmp_path)

    facts = read_candidate_facts(candidate)

    manifest = candidate / "release-manifest.json"
    assert facts.manifest_path == manifest
    assert facts.manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert facts.release_id == RELEASE_ID
    assert facts.release == WrittenFor(
        ai_service_contract="1.0.0",
        model_version="fake-model-1",
        routing_version="fake-routing-1",
        kb_version="v9",
        kb_document_count=0,
    )


def test_the_kb_size_counts_every_document_version(tmp_path: Path) -> None:
    documents = [{"id": "d1"}, {"id": "d2"}]
    kb = json.dumps({**KB, "documents": documents}).encode()

    facts = read_candidate_facts(build_fake_candidate(tmp_path, kb))

    assert facts.release.kb_document_count == len(documents)


@pytest.mark.parametrize("kb", [KB, {**KB, "documents": {}}], ids=["missing", "not a list"])
def test_a_kb_without_a_list_of_documents_is_refused(tmp_path: Path, kb: dict[str, object]) -> None:
    candidate = build_fake_candidate(tmp_path, json.dumps(kb).encode())

    with pytest.raises(CandidateKbInvalidError):
        read_candidate_facts(candidate)


def test_a_kb_of_two_files_is_refused(tmp_path: Path) -> None:
    # `build-candidate` copies a KB file only, so this candidate is written without it.
    sources = write_sources(tmp_path / "sources")
    (sources / "kb").mkdir()
    for name in ("a.json", "b.json"):
        (sources / "kb" / name).write_text(json.dumps({**KB, "documents": []}))
    kb_entry = {**asset_entries()["kb"], "source": "kb", "path": "kb"}
    spec_path = sources / "release-spec.json"
    spec_path.write_text(json.dumps(spec_document(kb=kb_entry)))
    spec = read_release_spec(spec_path)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    write_candidate_manifest(candidate, spec, copy_files(plan_copies(spec, sources), candidate))

    with pytest.raises(CandidateKbInvalidError):
        read_candidate_facts(candidate)


def test_a_candidate_that_ai_service_refuses_gives_no_facts(tmp_path: Path) -> None:
    candidate = build_fake_candidate(tmp_path)
    weights = candidate / "model" / "model.safetensors"
    data = bytearray(weights.read_bytes())
    data[0] ^= 1
    weights.write_bytes(bytes(data))

    with pytest.raises(ReleaseInvalidError):
        read_candidate_facts(candidate)


def test_a_folder_without_a_manifest_gives_no_facts(tmp_path: Path) -> None:
    with pytest.raises(JsonFileInvalidError):
        read_candidate_facts(tmp_path)

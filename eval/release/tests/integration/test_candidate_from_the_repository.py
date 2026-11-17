"""A candidate from the files of the repository: the KB of KB v2 and the prompts grounded-v4.

The model, the routing configuration, and the index are fakes, because their real files are
not in the repository (ADR-0018, Artifact store). The sources are read only.
"""

import hashlib
import json
from pathlib import Path

import pytest
from supportiq_ai_service.release.manifest import verify_candidate

from supportiq_release.composition_root import cli
from tests.unit.candidate.fakes import spec_document, write_sources

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
KB_V2 = REPOSITORY_ROOT / "eval" / "kb-ingestion" / "v2"
PROMPTS = REPOSITORY_ROOT / "ai-service" / "prompts" / "grounded-v4"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_candidate_with_the_kb_of_kb_v2_and_the_prompts_grounded_v4_passes_the_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repository_sources = (KB_V2 / "kb.json", KB_V2 / "document-intents.json", *PROMPTS.iterdir())
    before = {path: _sha256(path) for path in repository_sources}
    sources = write_sources(tmp_path / "sources")
    spec = sources / "release-spec.json"
    spec.write_text(
        json.dumps(
            spec_document(
                kb={"version": "v2", "source": str(KB_V2 / "kb.json"), "path": "kb/kb.json"},
                mapping={
                    "version": "v2",
                    "source": str(KB_V2 / "document-intents.json"),
                    "path": "mapping/document-intents.json",
                },
                prompts={"version": "grounded-v4", "source": str(PROMPTS), "path": "prompts"},
            )
        )
    )
    (tmp_path / "releases").mkdir()
    output = tmp_path / "candidate"

    status = cli.main(
        [
            "build-candidate",
            "--spec",
            str(spec),
            "--release-records",
            str(tmp_path / "releases"),
            "--output",
            str(output),
        ]
    )

    assert status == cli.EXIT_SUCCESS, capsys.readouterr().err
    versions = verify_candidate(output / "release-manifest.json").current().versions
    assert (versions.kb_version, versions.mapping_version, versions.prompt_version) == (
        "v2",
        "v2",
        "grounded-v4",
    )
    assert (output / "prompts" / "drafting-system.txt").read_bytes() == (
        PROMPTS / "drafting-system.txt"
    ).read_bytes()
    assert {path: _sha256(path) for path in repository_sources} == before

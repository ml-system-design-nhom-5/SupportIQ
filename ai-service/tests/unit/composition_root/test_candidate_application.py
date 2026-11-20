"""The application of a candidate, for the offline evaluation gate only (ADR-0021).

`build_candidate_application` checks a candidate with `verify_candidate` and wires it with the
ports of the gate, in the same process and without a server. `serve` keeps refusing every
candidate, and `ai-service` holds no fake: the ports here are those of a test, as the ports of
the gate are those of `eval/release/`.
"""

import io
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.composition_root import (
    CandidatePorts,
    SettingsInvalidError,
    build_candidate_application,
    cli,
)
from app.drafting import DraftReply, DraftRequest, LlmCallError, LlmFailure
from app.intent import IntentClassifier, IntentDistribution
from app.release.manifest import ReleaseInvalidError, ReleaseInvalidReason
from app.retrieval import DocumentMatch, DocumentSearch, RetrievalError
from tests.unit.composition_root.fakes import (
    KB_RELEASE_CHANGES,
    FakeClassifier,
    load_fake_models,
)
from tests.unit.intent.fakes import distribution
from tests.unit.platform.fakes import LLM_ENVIRONMENT
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import with_changes, write_release

BASE_URL = "http://ai-service.test"
SERVICE_TOKEN = "service-token-for-the-gate-tests"
SERVICE_TOKEN_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
REQUEST = {"message": "Where is my refund", "as_of": "2026-11-05T09:30:00Z"}


@dataclass(slots=True)
class RecordingPorts:
    """Ports of a test that record what the application gives them."""

    wrapped: list[object] = field(default_factory=list[object])
    llm_requests: list[DraftRequest] = field(default_factory=list[DraftRequest])

    def classifier(self, real: IntentClassifier) -> IntentClassifier:
        """Keep the intent model of the candidate, and return one sure of `human_agent`.

        Args:
            real: The intent model of the candidate.

        Returns:
            The intent model to use.
        """
        self.wrapped.append(real)
        return _SureClassifier()

    def search(self, real: DocumentSearch) -> DocumentSearch:
        """Keep the search of the candidate, and return it unchanged.

        Args:
            real: The search of the candidate.

        Returns:
            The same search.
        """
        self.wrapped.append(real)
        return real

    def write(self, request: DraftRequest) -> DraftReply:
        """Record the request and fail, as the writer of the gate does.

        Args:
            request: What the LLM would receive.

        Raises:
            LlmCallError: Always, as `llm_unavailable`.
        """
        self.llm_requests.append(request)
        raise LlmCallError(LlmFailure.UNAVAILABLE)

    def candidate_ports(self) -> CandidatePorts:
        """Return the ports for `build_candidate_application`.

        Returns:
            The ports that record.
        """
        return CandidatePorts(classifier=self.classifier, search=self.search, writer=self)


class _SureClassifier:
    def classify(self, message: str) -> IntentDistribution:
        del message
        return distribution(("human_agent", 1.0))


class _FailingSearch:
    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        del message
        raise RetrievalError


@pytest.fixture(autouse=True)
def restored_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = tuple(root.handlers), root.level
    yield
    for handler in tuple(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


@pytest.fixture(autouse=True)
def fake_models(monkeypatch: pytest.MonkeyPatch) -> None:
    # The application loads the two models through this function; torch is not needed here.
    monkeypatch.setattr(cli, "load_release_models", load_fake_models)


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # No RELEASE_MANIFEST_PATH: the candidate named by the gate is the only manifest.
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.delenv("RELEASE_MANIFEST_PATH", raising=False)
    for name, value in LLM_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


async def _post(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        return await client.post(path, json=REQUEST, headers=SERVICE_TOKEN_HEADERS)


def _events(log: io.StringIO) -> list[str]:
    return [json.loads(line)["event"] for line in log.getvalue().splitlines()]


@pytest.mark.anyio
async def test_a_candidate_is_served_in_process_with_the_ports_of_the_gate(
    tmp_path: Path,
) -> None:
    ports = RecordingPorts()
    log = io.StringIO()

    app = build_candidate_application(
        write_release(tmp_path, gate_run=False), ports.candidate_ports(), log
    )
    response = await _post(app, "/v1/analyses")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["intent"]["label"] == "human_agent"
    assert response.json()["routing"]["recommendation"] == "escalate"
    # The ports of the gate got the intent model and the search of the candidate itself.
    assert [type(port).__name__ for port in ports.wrapped] == [
        FakeClassifier.__name__,
        "SemanticRetriever",
    ]
    assert "release.loaded" in _events(log)
    assert f'"release_id":"{EXAMPLE_VERSIONS.release_id}"' in log.getvalue()


@pytest.mark.anyio
async def test_the_writer_of_the_gate_replaces_the_llm_step(tmp_path: Path) -> None:
    # With KB documents mapped to `track_order`, a draft reaches the LLM step.
    ports = RecordingPorts()
    manifest = write_release(tmp_path, gate_run=False, assets=with_changes(KB_RELEASE_CHANGES))
    keep_the_model = CandidatePorts(classifier=_unchanged, search=ports.search, writer=ports)

    app = build_candidate_application(manifest, keep_the_model, io.StringIO())
    response = await _post(app, "/v1/drafts")

    assert response.status_code == HTTPStatus.OK
    assert (response.json()["status"], response.json()["reason_codes"]) == (
        "llm_unavailable",
        ["llm_unavailable"],
    )
    assert len(ports.llm_requests) == 1


def _unchanged(real: IntentClassifier) -> IntentClassifier:
    return real


def _failing(real: DocumentSearch) -> DocumentSearch:
    del real
    return _FailingSearch()


@pytest.mark.anyio
async def test_a_port_of_the_gate_that_fails_is_a_failure_of_the_candidate(
    tmp_path: Path,
) -> None:
    ports = RecordingPorts()
    failing_search = CandidatePorts(classifier=_unchanged, search=_failing, writer=ports)

    app = build_candidate_application(
        write_release(tmp_path, gate_run=False), failing_search, io.StringIO()
    )
    response = await _post(app, "/v1/analyses")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["type"] == "urn:supportiq:problem:internal-error"


def test_a_candidate_whose_files_do_not_match_is_refused(tmp_path: Path) -> None:
    manifest = write_release(tmp_path, gate_run=False)
    weights = tmp_path / "model" / "model.safetensors"
    data = bytearray(weights.read_bytes())
    data[0] ^= 1
    weights.write_bytes(bytes(data))

    with pytest.raises(ReleaseInvalidError) as refused:
        build_candidate_application(manifest, RecordingPorts().candidate_ports(), io.StringIO())

    assert refused.value.reason is ReleaseInvalidReason.CHECKSUM_MISMATCH


@pytest.mark.anyio
async def test_the_candidate_is_the_only_manifest_and_needs_no_manifest_setting(
    tmp_path: Path,
) -> None:
    # The environment of the gate holds no RELEASE_MANIFEST_PATH, and the replica reports the
    # versions of the candidate that the gate named.
    app = build_candidate_application(
        write_release(tmp_path, gate_run=False), RecordingPorts().candidate_ports(), io.StringIO()
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        versions = await client.get("/v1/asset-versions", headers=SERVICE_TOKEN_HEADERS)

    assert versions.status_code == HTTPStatus.OK
    assert versions.json()["release_id"] == EXAMPLE_VERSIONS.release_id


def test_missing_settings_stop_the_gate_before_the_candidate_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SERVICE_TOKEN")
    log = io.StringIO()

    with pytest.raises(SettingsInvalidError):
        build_candidate_application(
            write_release(tmp_path, gate_run=False), RecordingPorts().candidate_ports(), log
        )

    assert _events(log) == ["settings.invalid"]

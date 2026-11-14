"""`ai-service serve` stops on bad settings or a bad release, or runs a replica (ARCH-34)."""

import logging
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from supportiq_ai_service.composition_root import cli
from supportiq_ai_service.platform.adapters.egress import (
    ALLOW_LIST_FILE_NAME,
    EgressAllowList,
    EgressAllowListInvalidError,
    packaged_egress_allow_list,
)
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.release import ReleaseNotLoadedError
from supportiq_ai_service.retrieval.adapters.no_kb_documents import NoKbDocuments
from supportiq_ai_service.suggestions import SuggestionInput
from supportiq_ai_service.suggestions.adapters import UnavailablePipeline
from tests.unit.platform.fakes import RecordingEgressClientFactory
from tests.unit.release.fakes import EXAMPLE_RELEASE, EXAMPLE_VERSIONS
from tests.unit.release.release_folder import ASSET_FILES, write_release

SERVE_ARGUMENTS = ["serve", "--host", "127.0.0.1", "--port", "8000"]
SERVICE_TOKEN = "service-token-for-unit-tests"
REQUEST = SuggestionInput(message="Hello", as_of=datetime(2026, 11, 5, 9, 30, tzinfo=UTC))
BASE_URL = "http://ai-service.test"
SERVICE_TOKEN_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


@dataclass(slots=True)
class RecordingServer:
    """Keep the application and the options that `uvicorn.run` would get."""

    runs: list[tuple[FastAPI, dict[str, object]]] = field(
        default_factory=list[tuple[FastAPI, dict[str, object]]]
    )

    def run(self, app: FastAPI, **options: object) -> None:
        """Keep the application and the options instead of serving.

        Args:
            app: The application.
            **options: The options of `uvicorn.run`.
        """
        self.runs.append((app, options))


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


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> RecordingServer:
    recording = RecordingServer()
    monkeypatch.setattr(cli.uvicorn, "run", recording.run)
    return recording


@pytest.fixture
def release_manifest(tmp_path: Path) -> Path:
    return write_release(tmp_path)


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, release_manifest: Path) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("RELEASE_MANIFEST_PATH", str(release_manifest))


@pytest.fixture
def client_factory(monkeypatch: pytest.MonkeyPatch) -> RecordingEgressClientFactory:
    factory = RecordingEgressClientFactory()
    monkeypatch.setattr(cli, "create_egress_client", factory)
    return factory


@pytest.mark.usefixtures("environment")
def test_serve_runs_one_replica_without_access_log_or_server_header(
    server: RecordingServer,
) -> None:
    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_SUCCESS
    ((_app, options),) = server.runs
    assert options == {
        "host": "127.0.0.1",
        "port": 8000,
        "log_config": None,
        "access_log": False,
        "server_header": False,
    }


@pytest.mark.usefixtures("environment")
def test_invalid_settings_stop_with_status_2_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SERVICE_TOKEN")

    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    assert '"event":"settings.invalid"' in capsys.readouterr().out


@pytest.mark.usefixtures("environment")
def test_an_invalid_egress_allow_list_stops_with_status_2_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    def invalid_allow_list() -> EgressAllowList:
        raise EgressAllowListInvalidError(ALLOW_LIST_FILE_NAME)

    monkeypatch.setattr(cli, "packaged_egress_allow_list", invalid_allow_list)

    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    output = capsys.readouterr().out
    assert '"event":"egress_allow_list.invalid"' in output
    assert f'"file_name":"{ALLOW_LIST_FILE_NAME}"' in output


def _flip_a_byte_of_the_weights(manifest_path: Path) -> str:
    weights = manifest_path.parent / "model" / "model.safetensors"
    content = bytearray(weights.read_bytes())
    content[0] ^= 1
    weights.write_bytes(bytes(content))
    return str(manifest_path)


def _name_a_missing_manifest(manifest_path: Path) -> str:
    return str(manifest_path.with_name("missing.json"))


def _leave_the_value_empty(manifest_path: Path) -> str:
    del manifest_path
    return ""


def _write_a_candidate(manifest_path: Path) -> str:
    return str(write_release(manifest_path.parent, gate_run=False))


# Each way to break the release, with the attributes that `release.invalid` must carry.
RELEASE_BREAKS: dict[str, tuple[Callable[[Path], str], tuple[str, ...]]] = {
    "checksum": (
        _flip_a_byte_of_the_weights,
        (
            '"reason":"checksum_mismatch"',
            '"asset":"model"',
            '"file_path":"model/model.safetensors"',
        ),
    ),
    "missing": (_name_a_missing_manifest, ('"reason":"manifest_unreadable"',)),
    "empty": (_leave_the_value_empty, ('"reason":"manifest_unreadable"',)),
    "candidate": (_write_a_candidate, ('"reason":"gate_run_missing"',)),
}


@pytest.fixture(params=sorted(RELEASE_BREAKS))
def broken_release(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, release_manifest: Path
) -> tuple[str, ...]:
    break_release, expected_attributes = RELEASE_BREAKS[request.param]
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.setenv("RELEASE_MANIFEST_PATH", break_release(release_manifest))
    return expected_attributes


def test_a_release_that_fails_its_check_stops_with_status_2_before_anything_is_created(
    server: RecordingServer,
    client_factory: RecordingEgressClientFactory,
    capsys: pytest.CaptureFixture[str],
    broken_release: tuple[str, ...],
) -> None:
    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_CONFIGURATION_INVALID
    assert not server.runs
    assert not client_factory.created
    output = capsys.readouterr().out
    assert '"event":"release.invalid"' in output
    for attribute in broken_release:
        assert attribute in output
    assert '"event":"release.loaded"' not in output
    for files in ASSET_FILES.values():
        for content in files.values():
            assert content.decode().strip() not in output


@pytest.mark.usefixtures("environment")
def test_serve_creates_one_client_of_the_packaged_allow_list_before_the_server_starts(
    server: RecordingServer, client_factory: RecordingEgressClientFactory
) -> None:
    cli.main(SERVE_ARGUMENTS)

    ((allow_list, client),) = client_factory.created
    assert allow_list == packaged_egress_allow_list()
    assert not client.is_closed
    assert len(server.runs) == 1


def test_serve_needs_a_host_and_a_port() -> None:
    with pytest.raises(SystemExit):
        cli.parse_arguments(["serve"])


def test_the_system_clock_tells_the_time_in_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


async def _request(app: FastAPI, method: str, path: str, body: object = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        return await client.request(method, path, json=body, headers=SERVICE_TOKEN_HEADERS)


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_a_replica_serves_the_versions_of_its_verified_release(
    server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    ready = await _request(app, "GET", "/health/ready")
    versions = await _request(app, "GET", "/v1/asset-versions")

    assert ready.status_code == HTTPStatus.NO_CONTENT
    assert versions.status_code == HTTPStatus.OK
    assert versions.json() == asdict(EXAMPLE_VERSIONS)
    output = capsys.readouterr().out
    assert '"event":"release.loaded"' in output
    assert f'"release_id":"{EXAMPLE_VERSIONS.release_id}"' in output


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
@pytest.mark.parametrize("path", ["/v1/analyses", "/v1/drafts"])
async def test_until_the_pipeline_is_wired_a_replica_answers_not_ready(
    server: RecordingServer, path: str
) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    response = await _request(
        app, "POST", path, {"message": "Hello", "as_of": "2026-11-05T09:30:00Z"}
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"


@pytest.mark.anyio
@pytest.mark.usefixtures("environment")
async def test_until_a_kb_is_wired_a_replica_finds_no_kb_document(server: RecordingServer) -> None:
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    response = await _request(app, "GET", "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"


@pytest.mark.anyio
async def test_until_the_pipeline_is_wired_it_refuses_every_suggestion() -> None:
    pipeline = UnavailablePipeline()

    with pytest.raises(ReleaseNotLoadedError):
        await pipeline.analyze(REQUEST, EXAMPLE_RELEASE)
    with pytest.raises(ReleaseNotLoadedError):
        await pipeline.draft(REQUEST, EXAMPLE_RELEASE)


def test_until_a_kb_is_wired_no_kb_document_is_found() -> None:
    assert NoKbDocuments().find("SAMPLE-REFUND-001", "1.0", EXAMPLE_RELEASE) is None

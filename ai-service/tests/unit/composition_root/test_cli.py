"""`ai-service serve` stops on invalid settings and otherwise runs one replica (ARCH-34)."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus

import httpx
import pytest
from fastapi import FastAPI

from supportiq_ai_service.composition_root import cli
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.release import ReleaseNotLoadedError
from supportiq_ai_service.release.adapters import NoReleaseSource
from supportiq_ai_service.retrieval.adapters.no_kb_documents import NoKbDocuments
from supportiq_ai_service.suggestions import SuggestionInput
from supportiq_ai_service.suggestions.adapters import UnavailablePipeline
from tests.unit.release.fakes import EXAMPLE_RELEASE

SERVE_ARGUMENTS = ["serve", "--host", "127.0.0.1", "--port", "8000"]
SERVICE_TOKEN = "service-token-for-unit-tests"
REQUEST = SuggestionInput(message="Hello", as_of=datetime(2026, 11, 5, 9, 30, tzinfo=UTC))


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


def test_serve_runs_one_replica_without_access_log_or_server_header(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer
) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", "service-token-for-unit-tests")

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


def test_invalid_settings_stop_with_status_2_before_the_server_starts(
    monkeypatch: pytest.MonkeyPatch, server: RecordingServer, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)

    status = cli.main(SERVE_ARGUMENTS)

    assert status == cli.EXIT_SETTINGS_INVALID
    assert not server.runs
    assert '"event":"settings.invalid"' in capsys.readouterr().out


def test_serve_needs_a_host_and_a_port() -> None:
    with pytest.raises(SystemExit):
        cli.parse_arguments(["serve"])


def test_the_system_clock_tells_the_time_in_utc() -> None:
    assert SystemClock().now().tzinfo is UTC


def test_without_a_release_manifest_no_release_is_loaded() -> None:
    assert NoReleaseSource().current() is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/v1/analyses", {"message": "Hello", "as_of": "2026-11-05T09:30:00Z"}),
        ("POST", "/v1/drafts", {"message": "Hello", "as_of": "2026-11-05T09:30:00Z"}),
        ("GET", "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0", None),
        ("GET", "/v1/asset-versions", None),
        ("GET", "/health/ready", None),
    ],
)
async def test_a_replica_without_a_release_manifest_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    server: RecordingServer,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    monkeypatch.setenv("SERVICE_TOKEN", SERVICE_TOKEN)
    cli.main(SERVE_ARGUMENTS)
    ((app, _options),) = server.runs

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ai-service.test") as client:
        response = await client.request(
            method, path, json=body, headers={"Authorization": f"Bearer {SERVICE_TOKEN}"}
        )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"


@pytest.mark.anyio
async def test_without_a_release_manifest_the_pipeline_computes_nothing() -> None:
    pipeline = UnavailablePipeline()

    with pytest.raises(ReleaseNotLoadedError):
        await pipeline.analyze(REQUEST, EXAMPLE_RELEASE)
    with pytest.raises(ReleaseNotLoadedError):
        await pipeline.draft(REQUEST, EXAMPLE_RELEASE)


def test_without_a_release_manifest_no_kb_document_is_found() -> None:
    assert NoKbDocuments().find("SAMPLE-REFUND-001", "1.0", EXAMPLE_RELEASE) is None

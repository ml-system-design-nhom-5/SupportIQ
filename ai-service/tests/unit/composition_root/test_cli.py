"""`ai-service serve` stops on invalid settings and otherwise runs one replica (ARCH-34)."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC

import pytest
from fastapi import FastAPI

from supportiq_ai_service.composition_root import cli
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.release.adapters import NoReleaseSource

SERVE_ARGUMENTS = ["serve", "--host", "127.0.0.1", "--port", "8000"]


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

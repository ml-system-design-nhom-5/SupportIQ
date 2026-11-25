"""A failed export of spans fails no request and does not hold up shutdown (LOG-02, ERR-09)."""

import socket
import time
from http import HTTPStatus

import pytest

from tests.integration.application import build_settings, running_client
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

LOOPBACK = "127.0.0.1"
EXPORT_TIMEOUT_MS = 200
# Far above one export bounded by EXPORT_TIMEOUT_MS, and far below the 10 seconds that the
# exporter takes when the setting does not reach it.
SHUTDOWN_LIMIT_SECONDS = 5


@pytest.fixture
def unreachable_collector() -> str:
    with socket.socket() as probe:
        probe.bind((LOOPBACK, 0))
        port = int(probe.getsockname()[1])
    return f"http://{LOOPBACK}:{port}/v1/traces"


async def test_unreachable_collector_fails_no_request_and_does_not_hold_up_shutdown(
    worker_database: WorkerDatabase, unreachable_collector: str
) -> None:
    settings = build_settings(
        worker_database,
        trace_exporter="otlp",
        otlp_traces_endpoint=unreachable_collector,
        otlp_export_timeout_ms=EXPORT_TIMEOUT_MS,
    )

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        response = await client.get("/health/ready")
        shutdown_started = time.monotonic()
    shutdown_seconds = time.monotonic() - shutdown_started

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert shutdown_seconds < SHUTDOWN_LIMIT_SECONDS

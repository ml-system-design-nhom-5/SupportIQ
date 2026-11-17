"""Guardrail: backend connects only to the destinations that its settings name (TEST-26).

The deployment has no network-level filter for outbound connections, so the list of ADR-0010 is
enforced in code: the settings name the database, ai-service, and the telemetry destination,
and no other module of backend imports a network client ([ADR-0016, Outbound connections](
../../../../docs/decisions/0016-hosting-on-free-tiers.md#outbound-connections), item 1; SEC-40).
"""

import ast
from pathlib import Path
from typing import get_args

import pytest
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import HttpUrl

from supportiq_backend.composition_root.runtime import build_runtime
from supportiq_backend.platform.settings import Settings, TraceExporter
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder
from tests.unit.platform.settings_builders import build_test_settings

SOURCE_ROOT = Path(__file__).parents[3] / "src" / "supportiq_backend"
DESTINATION_SETTINGS = {
    "database_url_app",
    "database_url_owner",
    "ai_service_base_url",
    "otlp_traces_endpoint",
}
DESTINATION_WORDS = ("url", "endpoint", "host")
NETWORK_MODULES = (
    "httpx",
    "requests",
    "urllib3",
    "aiohttp",
    "urllib.request",
    "http.client",
    "socket",
    "ssl",
    "asyncpg",
    "psycopg",
    "psycopg2",
    "smtplib",
    "ftplib",
    "websockets",
    "grpc",
    "opentelemetry.exporter",
)
ENGINE_FACTORIES = ("create_async_engine", "create_engine")
# The client of ai-service and the modules that pass its transport or hold it as a type; the
# driver and the engine of the database; and the exporter of spans.
IMPORTERS = {
    "httpx": {
        "composition_root/runtime.py",
        "composition_root/suggestions_wiring.py",
        "composition_root/web_application.py",
        "suggestions/adapters/ai_service_client.py",
    },
    "asyncpg": {"platform/adapters/database.py"},
    "create_async_engine": {"platform/adapters/database.py"},
    "opentelemetry.exporter": {"platform/adapters/telemetry.py"},
}
DATABASE_URL = "postgresql+asyncpg://supportiq_app:not-a-password@db.destination.test:6543/demo"
AI_SERVICE_URL = "https://ai.destination.test/"
OTLP_ENDPOINT = "https://otlp.destination.test/v1/traces"


def network_imports(source: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
            imported.update(alias.name for alias in node.names if alias.name in ENGINE_FACTORIES)
    return {
        network
        for name in imported
        for network in (*NETWORK_MODULES, *ENGINE_FACTORIES)
        if name == network or name.startswith(f"{network}.")
    }


def test_the_settings_name_exactly_the_outbound_destinations() -> None:
    """The settings that name a destination are exactly the database, ai-service, and telemetry.

    A setting names a destination when its name holds `url`, `endpoint`, or `host`, or its type
    is `HttpUrl`. A destination with another kind of name still meets the import check.
    """
    named = {
        name
        for name, field in Settings.model_fields.items()
        if any(word in name for word in DESTINATION_WORDS)
        or field.annotation is HttpUrl
        or HttpUrl in get_args(field.annotation)
    }

    assert named == DESTINATION_SETTINGS


def test_only_the_clients_of_those_destinations_import_a_network_library() -> None:
    importers: dict[str, set[str]] = {}
    for source in sorted(SOURCE_ROOT.rglob("*.py")):
        for network in network_imports(source):
            importers.setdefault(network, set()).add(source.relative_to(SOURCE_ROOT).as_posix())

    assert importers == IMPORTERS


@pytest.mark.anyio
async def test_each_outbound_client_takes_its_destination_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoints: list[str] = []

    def record_exporter(endpoint: str, *, timeout_ms: int) -> SpanExporter:
        del timeout_ms
        endpoints.append(endpoint)
        return InMemorySpanExporter()

    monkeypatch.setattr(
        "supportiq_backend.composition_root.runtime.create_otlp_span_exporter", record_exporter
    )
    settings = build_test_settings(
        database_url_app=DATABASE_URL,
        ai_service_base_url=AI_SERVICE_URL,
        trace_exporter=TraceExporter.OTLP,
        otlp_traces_endpoint=OTLP_ENDPOINT,
    )

    runtime = build_runtime(settings, RecordingEventRecorder(), FakeClock(), None)

    url = runtime.app_engine.url
    assert (url.host, url.port, url.database) == ("db.destination.test", 6543, "demo")
    assert str(runtime.ai_client.base_url) == AI_SERVICE_URL
    assert endpoints == [OTLP_ENDPOINT]
    await runtime.ai_client.aclose()
    await runtime.app_engine.dispose()
    runtime.tracer_provider.shutdown()

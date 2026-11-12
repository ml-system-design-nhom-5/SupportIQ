"""What the guardrail tests of telemetry share: the captured logs and the exported spans."""

import logging
from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from supportiq_backend.platform.adapters.telemetry import create_tracer_provider


@pytest.fixture
def restored_root_logger() -> Iterator[None]:
    """Give the root logger its handlers and level back after a test that configures it.

    Yields:
        Nothing.
    """
    root = logging.getLogger()
    handlers = tuple(root.handlers)
    level = root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.fixture
def exported_spans(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    """Keep every span that the application of the test exports, after its redaction.

    Args:
        monkeypatch: Replaces the tracer provider of the runtime for the test.

    Returns:
        The exporter, which holds the finished spans.
    """
    exporter = InMemorySpanExporter()

    def provider_with_exporter(_configured: SpanExporter | None) -> TracerProvider:
        return create_tracer_provider(exporter)

    monkeypatch.setattr(
        "supportiq_backend.composition_root.runtime.create_tracer_provider",
        provider_with_exporter,
    )
    return exporter

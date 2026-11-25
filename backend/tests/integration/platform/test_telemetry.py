"""Integration tests of tracing: every request has a trace with its database spans (ADR-0007)."""

from http import HTTPStatus

import httpx
import pytest
from fastapi import FastAPI, Response
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform import DatabaseOperationError
from app.platform.adapters.telemetry import (
    RedactingSpanProcessor,
    instrument_application,
    instrument_engine,
    uninstrument_engines,
)

pytestmark = pytest.mark.anyio

ORDER_ID = "ORD-20931"


@pytest.fixture
async def exported_spans(app_engine: AsyncEngine) -> tuple[ReadableSpan, ...]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    app = FastAPI()

    @app.get("/v1/orders/{order_id}")
    async def handle_get_order(order_id: str) -> Response:
        async with app_engine.connect() as connection:
            await connection.execute(text("SELECT :order_id"), {"order_id": order_id})
        return Response(status_code=HTTPStatus.NO_CONTENT)

    instrument_application(app, provider)
    instrument_engine(app_engine, provider)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend.test") as client:
        await client.get(f"/v1/orders/{ORDER_ID}?cursor=abc")
    uninstrument_engines()
    return tuple(exporter.get_finished_spans())


async def test_failed_statement_ends_its_span_without_the_value_it_was_given(
    app_engine: AsyncEngine,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))
    instrument_engine(app_engine, provider)

    with pytest.raises(DatabaseOperationError):
        async with app_engine.connect() as connection:
            await connection.execute(text("SELECT CAST(:value AS integer)"), {"value": ORDER_ID})

    uninstrument_engines()
    spans = exporter.get_finished_spans()
    (failed,) = (span for span in spans if span.status.status_code is StatusCode.ERROR)
    assert failed.status.description is None
    assert ORDER_ID not in repr([span.to_json() for span in spans])


def trace_id_of(span: ReadableSpan) -> int:
    context = span.context
    if context is None:
        raise AssertionError
    return context.trace_id


def trace_ids_of_database_spans(spans: tuple[ReadableSpan, ...]) -> set[int]:
    return {trace_id_of(span) for span in spans if (span.attributes or {}).get("db.system")}


def trace_id_of_server_span(spans: tuple[ReadableSpan, ...]) -> int:
    (server_span,) = (span for span in spans if span.name.startswith("GET "))
    return trace_id_of(server_span)


def text_of(spans: tuple[ReadableSpan, ...]) -> str:
    return repr([(span.name, dict(span.attributes or {})) for span in spans])


async def test_request_trace_holds_a_database_span(
    exported_spans: tuple[ReadableSpan, ...],
) -> None:
    database_trace_ids = trace_ids_of_database_spans(exported_spans)

    assert database_trace_ids == {trace_id_of_server_span(exported_spans)}


async def test_exported_spans_hold_neither_the_raw_path_nor_a_statement_parameter(
    exported_spans: tuple[ReadableSpan, ...],
) -> None:
    exported_text = text_of(exported_spans)

    assert ORDER_ID not in exported_text
    assert "cursor=abc" not in exported_text

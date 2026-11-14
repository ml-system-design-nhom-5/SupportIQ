"""The long-lived resources of a `backend` replica and the routers wired on them (ARCH-21)."""

from dataclasses import dataclass

import httpx
from fastapi import APIRouter
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root.accounts_wiring import wire_accounts
from supportiq_backend.composition_root.commerce_wiring import wire_commerce
from supportiq_backend.composition_root.shared_ports import build_shared_ports
from supportiq_backend.composition_root.suggestions_wiring import wire_suggestions
from supportiq_backend.composition_root.tickets_wiring import wire_tickets
from supportiq_backend.platform import CheckReadiness, Clock, EventRecorder
from supportiq_backend.platform.adapters.database import (
    DatabaseReadinessProbe,
    DatabaseTimeouts,
    create_database_engine,
    create_session_factory,
)
from supportiq_backend.platform.adapters.telemetry import (
    create_otlp_span_exporter,
    create_tracer_provider,
)
from supportiq_backend.platform.settings import Settings, TraceExporter
from supportiq_backend.suggestions import ClaimLoop


@dataclass(frozen=True, slots=True)
class Runtime:
    """What one replica creates at startup and closes at shutdown.

    Attributes:
        tracer_provider: The tracer provider of the process, never installed as a global.
        app_engine: The engine that connects as `supportiq_app`.
        check_readiness: The readiness use case.
        routers: The routers of every feature.
        ai_client: The HTTP client of ai-service, closed at shutdown.
        claim_loop: The claim loop of suggestion jobs, run by the lifespan.
    """

    tracer_provider: TracerProvider
    app_engine: AsyncEngine
    check_readiness: CheckReadiness
    routers: tuple[APIRouter, ...]
    ai_client: httpx.AsyncClient
    claim_loop: ClaimLoop


def database_timeouts(settings: Settings) -> DatabaseTimeouts:
    """Collect the timeout settings of every database call (ERR-09).

    Args:
        settings: The validated settings.

    Returns:
        The timeouts.
    """
    return DatabaseTimeouts(
        connect_ms=settings.database_connect_timeout_ms,
        statement_ms=settings.database_statement_timeout_ms,
        lock_ms=settings.database_lock_timeout_ms,
        pool_ms=settings.database_pool_timeout_ms,
    )


def build_tracer_provider(settings: Settings) -> TracerProvider:
    """Create the tracer provider with the exporter that the settings choose.

    Args:
        settings: The validated settings.

    Returns:
        The tracer provider.
    """
    if settings.trace_exporter is TraceExporter.OTLP and settings.otlp_traces_endpoint is not None:
        exporter = create_otlp_span_exporter(
            str(settings.otlp_traces_endpoint), timeout_ms=settings.otlp_export_timeout_ms
        )
        return create_tracer_provider(exporter)
    return create_tracer_provider(None)


def build_runtime(
    settings: Settings,
    events: EventRecorder,
    clock: Clock,
    ai_service_transport: httpx.AsyncBaseTransport | None,
) -> Runtime:
    """Create the resources of a replica and wire every feature on them.

    Args:
        settings: The validated settings.
        events: Where events are recorded.
        clock: The clock of the process.
        ai_service_transport: The transport of the ai-service client; None for the network.

    Returns:
        The runtime. Nothing here opens a connection.
    """
    engine = create_database_engine(
        settings.database_url_app.get_secret_value(), database_timeouts(settings)
    )
    session_factory = create_session_factory(engine)
    tracer_provider = build_tracer_provider(settings)
    shared = build_shared_ports(settings, events, clock, tracer_provider)
    accounts = wire_accounts(settings, session_factory, shared)
    suggestions = wire_suggestions(
        settings, session_factory, shared, accounts, ai_service_transport
    )
    return Runtime(
        tracer_provider=tracer_provider,
        app_engine=engine,
        check_readiness=CheckReadiness((DatabaseReadinessProbe(engine),)),
        routers=(
            *accounts.routers,
            wire_commerce(session_factory, accounts),
            *wire_tickets(settings, session_factory, shared, accounts, suggestions),
            *suggestions.routers,
        ),
        ai_client=suggestions.ai_client,
        claim_loop=suggestions.claim_loop,
    )

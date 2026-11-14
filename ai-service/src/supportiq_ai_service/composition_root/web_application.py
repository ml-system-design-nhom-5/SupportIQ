"""The FastAPI application of an ai-service replica, wired from the settings (ARCH-21).

Creating the application does no I/O. Every operation except the health checks checks the
service token (ADR-0018, Access), and every request continues or starts its trace (LOG-05).
The command creates the one HTTP client that leaves the system, and the lifespan closes it at
shutdown (ARCH-24, SEC-40).
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import Depends, FastAPI
from starlette.concurrency import run_in_threadpool

from supportiq_ai_service.platform import CheckReadiness, Clock, EventName, EventRecorder
from supportiq_ai_service.platform.adapters.trace_context import (
    OpenTelemetryTraceContext,
    TraceContextMiddleware,
)
from supportiq_ai_service.platform.settings import Settings
from supportiq_ai_service.platform.web import (
    RequestLoggingMiddleware,
    build_health_router,
    build_service_token_guard,
    install_exception_handling,
)
from supportiq_ai_service.release import GetAssetVersions, ReleaseReadinessProbe, ReleaseSource
from supportiq_ai_service.release.api import build_release_router
from supportiq_ai_service.retrieval import GetKbDocumentVersion, KbDocumentSource
from supportiq_ai_service.retrieval.api import build_retrieval_router
from supportiq_ai_service.suggestions import CreateAnalysis, CreateDraft, SuggestionPipeline
from supportiq_ai_service.suggestions.api import build_suggestions_router


@dataclass(frozen=True, slots=True)
class ServicePorts:
    """The ports that the operations of the contract run on.

    Attributes:
        release_source: Where the loaded release comes from.
        pipeline: The pipeline that computes analyses and drafts.
        kb_documents: Where the document versions of the loaded KB come from.
    """

    release_source: ReleaseSource
    pipeline: SuggestionPipeline
    kb_documents: KbDocumentSource


def create_app(
    settings: Settings,
    events: EventRecorder,
    clock: Clock,
    ports: ServicePorts,
    egress_client: httpx.Client,
) -> FastAPI:
    """Create the application with every route of the contract and the health checks.

    Args:
        settings: The validated settings.
        events: Where events are recorded.
        clock: The clock of the process.
        ports: The ports that the operations run on.
        egress_client: The client of the egress allow-list, which the lifespan closes.

    Returns:
        The application, ready for an ASGI server.
    """
    app = FastAPI(
        lifespan=_build_lifespan(events, egress_client),
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        # The contract defines no redirect, so a trailing slash is an unknown path.
        redirect_slashes=False,
    )
    install_exception_handling(app, events, OpenTelemetryTraceContext())
    app.add_middleware(RequestLoggingMiddleware, events=events, clock=clock)
    # Added last, so it runs first: every log line and error body of a request has its trace.
    app.add_middleware(TraceContextMiddleware)
    source = ports.release_source
    app.include_router(build_health_router(CheckReadiness((ReleaseReadinessProbe(source),))))
    service_token = Depends(build_service_token_guard(settings.service_token.get_secret_value()))
    for router in (
        build_suggestions_router(
            CreateAnalysis(source, ports.pipeline), CreateDraft(source, ports.pipeline)
        ),
        build_retrieval_router(GetKbDocumentVersion(source, ports.kb_documents)),
        build_release_router(GetAssetVersions(source)),
    ):
        app.include_router(router, dependencies=[service_token])
    return app


def _build_lifespan(
    events: EventRecorder, egress_client: httpx.Client
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        events.record(EventName.STARTUP_COMPLETED)
        yield
        events.record(EventName.SHUTDOWN_STARTED)
        # The command created this client once, before the server started. No adapter sends a
        # request with it yet, because the pipeline of `main` is not wired in. Closing it may
        # close sockets, so it runs off the event loop.
        await run_in_threadpool(egress_client.close)

    return lifespan

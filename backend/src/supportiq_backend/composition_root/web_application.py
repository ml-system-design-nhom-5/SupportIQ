"""The FastAPI application of the `backend` replicas, wired from the settings (ARCH-21).

Creating the application does no I/O. The engine connects on the first request, and the
lifespan closes the engine and the tracer provider at shutdown (ARCH-24, PY-34).
"""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from enum import StrEnum

from fastapi import FastAPI
from opentelemetry.trace import Tracer

from supportiq_backend.composition_root.runtime import Runtime, build_runtime
from supportiq_backend.platform import Clock, EventName, EventRecorder
from supportiq_backend.platform.adapters.telemetry import (
    OpenTelemetryTraceContext,
    instrument_application,
    instrument_engine,
    uninstrument_engines,
)
from supportiq_backend.platform.settings import Settings
from supportiq_backend.platform.web import (
    RequestLoggingMiddleware,
    build_health_router,
    install_exception_handling,
)

TRACER_NAME = "supportiq_backend"
START_SPAN = "start_backend"
STOP_SPAN = "stop_backend"


class BackgroundWork(StrEnum):
    """What a replica runs beside its requests (ARCH-41).

    A replica runs the claim loop of suggestion jobs. Tests of the HTTP operations run without
    it, so no job runs behind their back; the tests of the queue run the loop themselves.
    """

    SUGGESTION_JOBS = "suggestion_jobs"
    NONE = "none"


def create_app(
    settings: Settings,
    events: EventRecorder,
    clock: Clock,
    *,
    background: BackgroundWork = BackgroundWork.SUGGESTION_JOBS,
) -> FastAPI:
    """Create the application with every route of the contract and the health checks.

    Args:
        settings: The validated settings.
        events: Where events are recorded.
        clock: The clock of the process.
        background: What the replica runs beside its requests.

    Returns:
        The application, ready for an ASGI server.
    """
    runtime = build_runtime(settings, events, clock)
    app = FastAPI(
        lifespan=_build_lifespan(runtime, events, background),
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        # The contract defines no redirect, so a trailing slash is an unknown path.
        redirect_slashes=False,
    )
    install_exception_handling(app, events, OpenTelemetryTraceContext())
    app.add_middleware(RequestLoggingMiddleware, events=events, clock=clock)
    app.include_router(build_health_router(runtime.check_readiness))
    for router in runtime.routers:
        app.include_router(router)
    instrument_application(app, runtime.tracer_provider)
    return app


def _build_lifespan(
    runtime: Runtime, events: EventRecorder, background: BackgroundWork
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        tracer = runtime.tracer_provider.get_tracer(TRACER_NAME)
        with tracer.start_as_current_span(START_SPAN):
            instrument_engine(runtime.app_engine, runtime.tracer_provider)
            events.record(EventName.STARTUP_COMPLETED)
        try:
            # The claim loop is owned by a task group, so it is awaited at shutdown (PY-33).
            async with asyncio.TaskGroup() as group:
                if background is BackgroundWork.SUGGESTION_JOBS:
                    group.create_task(runtime.claim_loop.run())
                try:
                    yield
                finally:
                    runtime.claim_loop.stop()
        finally:
            await _shut_down(runtime, events, tracer)

    return lifespan


async def _shut_down(runtime: Runtime, events: EventRecorder, tracer: Tracer) -> None:
    # Every resource is released even when the server stops with an error.
    try:
        with tracer.start_as_current_span(STOP_SPAN):
            events.record(EventName.SHUTDOWN_STARTED)
            await runtime.ai_client.aclose()
            uninstrument_engines()
            await runtime.app_engine.dispose()
    finally:
        runtime.tracer_provider.shutdown()

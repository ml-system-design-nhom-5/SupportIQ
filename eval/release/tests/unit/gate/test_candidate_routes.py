"""The routes of the real application of `ai-service` are read through its included routers.

`create_app` of `ai-service` adds each router with `include_router`, which FastAPI keeps as one
route that holds the router. The first gate run failed its route check on this
(gate-run.json of release-2026-11-18-01), so these tests build the application with the real
`create_app` and its real routers. Only the ports are fakes, and no request reaches them: the
gate reads the routes of the application, then sends no case here.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import httpx
import pytest
from app.composition_root import CandidatePorts, ServicePorts, create_app
from app.platform import EventAttributeValue, EventName
from app.platform.settings import Settings
from app.release import LoadedRelease
from app.retrieval import KbDocument
from app.suggestions import Analysis, DraftOutcome, SuggestionInput
from fastapi import APIRouter, FastAPI, WebSocket
from starlette.applications import Starlette

from supportiq_release.gate.adapters import GatePorts, candidate_settings, run_cases
from supportiq_release.gate.domain import CONTRACT_ROUTES, CandidateCheck, candidate_checks
from tests.unit.gate.fakes import FAKE_LABELS

MANIFEST = Path("candidate/release-manifest.json")
BEARER = "fake-service-bearer"


class _NoRelease:
    def current(self) -> LoadedRelease | None:
        return None


class _NoPipeline:
    async def analyze(self, request: SuggestionInput, release: LoadedRelease) -> Analysis:
        del request, release
        message = "the gate reads the routes and sends no case here"
        raise AssertionError(message)

    async def draft(self, request: SuggestionInput, release: LoadedRelease) -> DraftOutcome:
        del request, release
        message = "the gate reads the routes and sends no case here"
        raise AssertionError(message)


class _NoKb:
    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        del document_id, version, release
        return None


class _NoEvents:
    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        del event, attributes


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 11, 18, tzinfo=UTC)


@pytest.fixture
def real_app() -> Iterator[FastAPI]:
    settings = Settings.model_validate(
        {
            "release_manifest_path": MANIFEST,
            **{name.lower(): value for name, value in candidate_settings(BEARER).items()},
        }
    )
    ports = ServicePorts(release_source=_NoRelease(), pipeline=_NoPipeline(), kb_documents=_NoKb())
    # The egress client of the application; no request uses it, and it is closed after the test.
    with httpx.Client() as egress_client:
        yield create_app(settings, _NoEvents(), _FixedClock(), ports, egress_client)


def _routes_of(app: FastAPI) -> frozenset[tuple[str, str]]:
    def build(manifest_path: Path, ports: CandidatePorts, log_stream: TextIO) -> Starlette:
        del manifest_path, ports, log_stream
        return app

    return run_cases(MANIFEST, [], GatePorts(labels=FAKE_LABELS), BEARER, build=build).routes


def test_the_real_application_serves_exactly_the_routes_of_contract_1_0_0(
    real_app: FastAPI,
) -> None:
    routes = _routes_of(real_app)

    assert routes == CONTRACT_ROUTES
    assert candidate_checks(routes, "", [], [], 0)[0].passed


def test_a_route_of_an_included_router_outside_the_contract_fails_the_check_and_is_named(
    real_app: FastAPI,
) -> None:
    app = real_app
    extra = APIRouter()

    @extra.post("/v1/refunds")
    async def refund() -> None: ...

    app.include_router(extra)

    routes = _routes_of(app)

    check = candidate_checks(routes, "", [], [], 0)[0]
    assert ("POST", "/v1/refunds") in routes
    assert (check.check, check.passed, check.observed) == (
        CandidateCheck.ROUTES,
        False,
        ("+POST /v1/refunds",),
    )


def test_a_nested_router_is_read_with_the_prefixes_of_its_inclusions(real_app: FastAPI) -> None:
    app = real_app
    inner, outer = APIRouter(), APIRouter()

    @inner.get("/orders")
    async def orders() -> None: ...

    outer.include_router(inner, prefix="/inner")
    app.include_router(outer, prefix="/v9")

    assert ("GET", "/v9/inner/orders") in _routes_of(app)


def test_an_unknown_kind_of_route_inside_an_included_router_fails_the_check(
    real_app: FastAPI,
) -> None:
    app = real_app
    sockets = APIRouter()

    @sockets.websocket("/v1/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.close()

    app.include_router(sockets)

    routes = _routes_of(app)

    unknown = {(kind, path) for kind, path in routes if path == "/v1/stream"}
    assert len(unknown) == 1
    assert unknown.isdisjoint(CONTRACT_ROUTES)
    assert not candidate_checks(routes, "", [], [], 0)[0].passed


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_the_reader_keeps_the_methods_of_each_route_without_head(
    real_app: FastAPI, prefix: str
) -> None:
    app = real_app
    router = APIRouter()

    @router.get("/probe")
    async def probe() -> None: ...

    app.include_router(router, prefix=prefix)

    assert {method for method, path in _routes_of(app) if path == f"{prefix}/probe"} == {"GET"}


def _frontend_folder(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<p>A page of a frontend build.</p>\n")
    return tmp_path


def test_the_frontend_of_an_included_router_fails_the_check(
    real_app: FastAPI, tmp_path: Path
) -> None:
    # FastAPI keeps the routes of `frontend()` apart, after the other routes, and serves them.
    router = APIRouter()
    router.frontend("/", directory=_frontend_folder(tmp_path))
    real_app.include_router(router)

    check = candidate_checks(_routes_of(real_app), "", [], [], 0)[0]

    assert not check.passed
    assert check.observed == ("+_FrontendRouteGroup /",)


def test_the_frontend_of_the_application_fails_the_check(real_app: FastAPI, tmp_path: Path) -> None:
    real_app.frontend("/", directory=_frontend_folder(tmp_path))

    check = candidate_checks(_routes_of(real_app), "", [], [], 0)[0]

    assert not check.passed
    assert check.observed == ("+_FrontendRouteGroup /",)

"""Run the escalation cases on the application of a candidate, in the process of the gate.

The application comes from `build_candidate_application` of `ai-service`, the one entry point
of the gate, with the ports of `gate_ports.py`. Each case sends its request to `createAnalysis`
and then to `createDraft` through an ASGI transport, inside the lifespan of the application, so
no port is opened. The cases run one at a time, because the ports serve one case at a time.

The settings of the candidate come from the environment of the process, as for `serve`, except
the manifest, which `build_candidate_application` takes as an argument. `candidate_settings`
returns the settings that the gate decides, and the composition root sets them before the run:
a service token made for this run only, and a model name and a key for the LLM provider that no
call ever uses, because the LLM step of the gate never calls a provider. This module never
changes the environment itself.

The routes of the application are read for the check of the contract routes. FastAPI keeps
each included router as one route, so the reader walks into it and reads its leaf routes, with
the prefix of the inclusion. A leaf route of another kind, such as a mount or a websocket
route, or a route for every method, is read under a name that no route of the contract has, so
the check fails on it instead of skipping it.
"""

import asyncio
import io
import secrets
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, cast

import httpx
from app.composition_root import (
    CandidatePorts,
    SettingsInvalidError,
    build_candidate_application,
)
from starlette.applications import Starlette
from starlette.routing import BaseRoute, Route

from supportiq_release.errors import ReleaseCommandError
from supportiq_release.gate.adapters.gate_ports import GatePorts
from supportiq_release.gate.domain import Case, Observation, Response

type ApplicationFactory = Callable[[Path, CandidatePorts, TextIO], Starlette]

# 32 random bytes, as the service token of `backend` has.
_SERVICE_TOKEN_BYTES = 32
# Settings that no LLM call reads: the LLM step of the gate never calls a provider.
_UNUSED_LLM_SETTINGS = {
    "GEMINI_API_KEY": "unused-by-the-gate",
    "GEMINI_MODEL": "gemini-unused-by-the-gate",
    "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "0",
    "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "0",
}
_BASE_URL = "http://candidate.gate"
_ANALYSES = "/v1/analyses"
_DRAFTS = "/v1/drafts"
# Starlette answers HEAD for every GET route by itself; the contract names GET only.
_IMPLICIT_METHODS = frozenset({"HEAD"})
# The method of a route that serves every method, which no route of the contract does.
_EVERY_METHOD = "*"


@dataclass(frozen=True, slots=True)
class CandidateRun:
    """What the candidate did during the run.

    Attributes:
        observations: One observation for each case, in the order of the cases.
        routes: Each method and path that the application serves.
        log_text: Every line that the candidate logged.
        llm_calls: The calls that the LLM step of the gate received.
    """

    observations: tuple[Observation, ...]
    routes: frozenset[tuple[str, str]]
    log_text: str
    llm_calls: int


class CandidateSettingsInvalidError(ReleaseCommandError):
    """A setting of the candidate is missing or invalid. The message names the settings only."""

    def __init__(self, setting_names: tuple[str, ...]) -> None:
        """Build the error with a message that names the settings, never their values.

        Args:
            setting_names: The names of the missing or invalid settings.
        """
        super().__init__("The settings of the candidate are refused: " + ", ".join(setting_names))
        self.setting_names = setting_names


def new_service_token() -> str:
    """Return a service token for one gate run.

    Returns:
        32 random bytes in URL-safe base64.
    """
    return secrets.token_urlsafe(_SERVICE_TOKEN_BYTES)


def candidate_settings(service_token: str) -> dict[str, str]:
    """Return the settings of the candidate that the gate decides, for the environment.

    Args:
        service_token: The service token of the run.

    Returns:
        The service token, and LLM settings that no call reads.
    """
    return {**_UNUSED_LLM_SETTINGS, "SERVICE_TOKEN": service_token}


def run_cases(
    manifest_path: Path,
    cases: Sequence[Case],
    ports: GatePorts,
    service_token: str,
    *,
    build: ApplicationFactory = build_candidate_application,
) -> CandidateRun:
    """Build the application of the candidate and send every case to it.

    The environment must already hold `candidate_settings(service_token)`.

    Args:
        manifest_path: The manifest of the candidate.
        cases: The cases, in their order.
        ports: The ports of the gate.
        service_token: The service token that the environment holds, sent with each request.
        build: The builder of the application; `build_candidate_application` of `ai-service`.

    Returns:
        The observations, the routes, the logs, and the LLM calls.

    Raises:
        ReleaseInvalidError: `ai-service` refuses the candidate.
        CandidateSettingsInvalidError: A setting of the candidate is missing or invalid.
    """
    log = io.StringIO()
    try:
        app = build(manifest_path, ports.candidate_ports(), log)
    except SettingsInvalidError as error:
        raise CandidateSettingsInvalidError(error.setting_names) from error
    observations = asyncio.run(_observe(app, cases, ports, service_token))
    return CandidateRun(
        observations=observations,
        routes=_routes(app),
        log_text=log.getvalue(),
        llm_calls=ports.llm_calls,
    )


async def _observe(
    app: Starlette, cases: Sequence[Case], ports: GatePorts, service_token: str
) -> tuple[Observation, ...]:
    headers = {"Authorization": f"Bearer {service_token}"}
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url=_BASE_URL, headers=headers) as client,
    ):
        return tuple([await _observe_case(client, case, ports) for case in cases])


async def _observe_case(client: httpx.AsyncClient, case: Case, ports: GatePorts) -> Observation:
    ports.use(case.injection)
    try:
        analysis = await _post(client, _ANALYSES, case.request)
        calls_before_the_draft = ports.llm_calls
        draft = await _post(client, _DRAFTS, case.request)
    finally:
        ports.use(None)
    return Observation(
        analysis=analysis,
        draft=draft,
        llm_called=ports.llm_calls > calls_before_the_draft,
        llm_sources=frozenset(
            version for sources in ports.llm_sources[calls_before_the_draft:] for version in sources
        ),
    )


async def _post(client: httpx.AsyncClient, path: str, body: Mapping[str, object]) -> Response:
    response = await client.post(path, json=body)
    try:
        content: object = response.json()
    except ValueError:
        content = None
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    return Response(
        status=response.status_code,
        body=cast("dict[str, object]", content) if isinstance(content, dict) else {},
    )


def _routes(app: Starlette) -> frozenset[tuple[str, str]]:
    # A router that the gate cannot read gives no route, so the check of the routes fails.
    return frozenset(_leaf_routes(_routes_of_router(app.router) or (), ""))


def _leaf_routes(routes: Sequence[BaseRoute], prefix: str) -> Iterator[tuple[str, str]]:
    for route in routes:
        included = _included_router(route)
        if included is None:
            yield from _methods_and_path(route, prefix)
        else:
            router_routes, router_prefix = included
            yield from _leaf_routes(router_routes, prefix + router_prefix)


def _included_router(route: BaseRoute) -> tuple[Sequence[BaseRoute], str] | None:
    # FastAPI keeps each router that `include_router` added as one route, which holds the router
    # as `original_router` and the prefix of the inclusion in `include_context`. Anything else
    # is a leaf, so a router of another shape is read as an unknown route and fails the check.
    routes = _routes_of_router(getattr(route, "original_router", None))
    prefix = getattr(getattr(route, "include_context", None), "prefix", None)
    if routes is None or not isinstance(prefix, str):
        return None
    return routes, prefix


def _routes_of_router(router: object) -> Sequence[BaseRoute] | None:
    # Every route that a router serves: `routes`, and the routes that FastAPI serves after them,
    # such as those of `frontend()`, which it keeps in `_low_priority_routes`.
    routes = getattr(router, "routes", None)
    low_priority = getattr(router, "_low_priority_routes", [])
    if not isinstance(routes, list) or not isinstance(low_priority, list):
        return None
    # The casts only name the type of the routes of a router, which `isinstance` found (PY-12).
    return [*cast("list[BaseRoute]", routes), *cast("list[BaseRoute]", low_priority)]


def _methods_and_path(route: BaseRoute, prefix: str) -> frozenset[tuple[str, str]]:
    if not isinstance(route, Route):
        # A route of another kind, such as the frontend group at the root, whose path is empty.
        unknown_path = prefix + str(getattr(route, "path", ""))
        return frozenset({(type(route).__name__, unknown_path or "/")})
    path = prefix + route.path
    if route.methods is None:
        return frozenset({(_EVERY_METHOD, path)})
    return frozenset((method, path) for method in route.methods if method not in _IMPLICIT_METHODS)

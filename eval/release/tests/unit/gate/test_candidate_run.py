"""The run sends every case to the application of the candidate and observes what it did."""

from http import HTTPStatus
from pathlib import Path
from typing import TextIO

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocket
from supportiq_ai_service.composition_root import CandidatePorts, SettingsInvalidError

from supportiq_release.gate.adapters import (
    CandidateSettingsInvalidError,
    GatePorts,
    candidate_settings,
    new_service_token,
    run_cases,
)
from supportiq_release.gate.domain import CONTRACT_ROUTES, Case, Failure, Injection
from tests.unit.gate.fakes import (
    ABSTAIN,
    FAILS,
    FAKE_LABELS,
    INTERNAL_ERROR,
    LLM_MESSAGE,
    MESSAGE,
    fake_application_factory,
)

MANIFEST = Path("candidate/release-manifest.json")
BEARER = "fake-service-token"
# The length of 32 random bytes in URL-safe base64, without padding.
TOKEN_LENGTH = 43


def _case(case_id: str, injection: Injection | None = None, message: str = MESSAGE) -> Case:
    return Case(
        case_id=case_id,
        esc_rule="ESC-04",
        request={"message": message, "as_of": "2026-11-17T09:00:00Z"},
        injection=injection,
        depends_on_model=injection is None,
        expected=ABSTAIN if injection is None or injection.failure is None else FAILS,
    )


def test_every_case_is_sent_to_both_operations_in_order() -> None:
    built: dict[str, object] = {}
    cases = [_case("a"), _case("b")]

    run = run_cases(
        MANIFEST,
        cases,
        GatePorts(labels=FAKE_LABELS),
        BEARER,
        build=fake_application_factory(BEARER, built=built),
    )

    assert built == {"manifest_path": MANIFEST, "service_token": BEARER}
    assert len(run.observations) == len(cases)
    for observation in run.observations:
        assert observation.analysis.status == observation.draft.status == HTTPStatus.OK
        assert observation.analysis.body == {
            "routing": {"recommendation": "abstain", "reason_codes": ["no_valid_document"]}
        }
        assert observation.draft.body["status"] == "abstained"
        assert not observation.llm_called
    assert run.routes == CONTRACT_ROUTES
    assert run.llm_calls == 0
    assert run.log_text == '{"event": "analysis_created"}\n' * 4


def test_the_requests_carry_the_service_token_of_the_run() -> None:
    run = run_cases(
        MANIFEST,
        [_case("a")],
        GatePorts(labels=FAKE_LABELS),
        "another-token",
        build=fake_application_factory(BEARER),
    )

    assert run.observations[0].analysis.status == HTTPStatus.UNAUTHORIZED


def test_the_settings_of_the_gate_are_a_service_token_and_llm_settings_that_no_call_reads() -> None:
    first, second = new_service_token(), new_service_token()

    settings = candidate_settings(first)

    assert len(first) >= TOKEN_LENGTH
    assert first != second
    assert settings == {
        "GEMINI_API_KEY": "unused-by-the-gate",
        "GEMINI_MODEL": "gemini-unused-by-the-gate",
        "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "0",
        "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS": "0",
        "SERVICE_TOKEN": first,
    }
    # The manifest is an argument of the builder, never a setting of the environment.
    assert "RELEASE_MANIFEST_PATH" not in settings


def test_an_injected_distribution_reaches_the_candidate_for_its_case_only() -> None:
    injection = Injection(intent_distribution=(("human_agent", 0.95),), failure=None)

    run = run_cases(
        MANIFEST,
        [_case("injected", injection), _case("real")],
        GatePorts(labels=FAKE_LABELS),
        BEARER,
        build=fake_application_factory(BEARER),
    )

    injected, real = run.observations
    assert injected.analysis.body["routing"] == {
        "recommendation": "escalate",
        "reason_codes": ["human_agent_requested", "no_valid_document"],
    }
    assert injected.draft.body["status"] == "escalation_recommended"
    assert real.analysis.body["routing"] == {
        "recommendation": "abstain",
        "reason_codes": ["no_valid_document"],
    }


@pytest.mark.parametrize("failure", [Failure.INTENT_MODEL, Failure.RETRIEVAL])
def test_an_injected_failure_fails_both_operations_of_its_case_only(failure: Failure) -> None:
    cases = [_case("failed", Injection(intent_distribution=None, failure=failure)), _case("real")]

    run = run_cases(
        MANIFEST,
        cases,
        GatePorts(labels=FAKE_LABELS),
        BEARER,
        build=fake_application_factory(BEARER),
    )

    failed, real = run.observations
    assert failed.analysis.status == failed.draft.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert failed.analysis.body == failed.draft.body == {"type": INTERNAL_ERROR}
    assert real.analysis.status == HTTPStatus.OK


def test_a_call_of_the_llm_step_is_observed_for_its_case_and_counted() -> None:
    cases = [_case("calls", message=LLM_MESSAGE), _case("does-not-call")]

    run = run_cases(
        MANIFEST,
        cases,
        GatePorts(labels=FAKE_LABELS),
        BEARER,
        build=fake_application_factory(BEARER),
    )

    calls, does_not_call = run.observations
    assert calls.llm_called
    assert calls.draft.body["reason_codes"] == ["no_valid_document", "llm_unavailable"]
    assert not does_not_call.llm_called
    assert run.llm_calls == 1


def test_the_routes_and_the_logs_are_those_of_the_application() -> None:
    build = fake_application_factory(BEARER, leak_message=True, extra_route="/v1/refunds")

    run = run_cases(MANIFEST, [_case("a")], GatePorts(labels=FAKE_LABELS), BEARER, build=build)

    assert run.routes == CONTRACT_ROUTES | {("POST", "/v1/refunds")}
    assert MESSAGE in run.log_text


def _with_routes(*routes: Route | Mount | WebSocketRoute) -> Starlette:
    async def analyses(request: Request) -> JSONResponse:
        del request
        return JSONResponse({})

    return Starlette(
        routes=[
            Route("/v1/analyses", analyses, methods=["POST"]),
            Route("/v1/drafts", analyses, methods=["POST"]),
            *routes,
        ]
    )


async def _socket(websocket: WebSocket) -> None:
    await websocket.close()


class _EveryMethod:
    # An ASGI application as an endpoint, which Starlette serves for every method.
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send


@pytest.mark.parametrize(
    ("route", "entry"),
    [
        (Mount("/admin", app=Starlette()), ("Mount", "/admin")),
        (WebSocketRoute("/v1/stream", _socket), ("WebSocketRoute", "/v1/stream")),
        (Route("/v1/any", _EveryMethod()), ("*", "/v1/any")),
    ],
    ids=["a mount", "a websocket route", "a route for every method"],
)
def test_a_route_of_another_kind_is_read_under_a_name_that_fails_the_route_check(
    route: Route | Mount | WebSocketRoute, entry: tuple[str, str]
) -> None:
    def build(manifest_path: Path, ports: CandidatePorts, log_stream: TextIO) -> Starlette:
        del manifest_path, ports, log_stream
        return _with_routes(route)

    run = run_cases(MANIFEST, [_case("a")], GatePorts(labels=FAKE_LABELS), BEARER, build=build)

    assert entry in run.routes
    assert entry not in CONTRACT_ROUTES


def test_a_body_that_is_not_a_json_object_is_observed_as_empty() -> None:
    async def text(request: Request) -> PlainTextResponse:
        del request
        return PlainTextResponse("not json", 502)

    def build(manifest_path: Path, ports: CandidatePorts, log_stream: TextIO) -> Starlette:
        del manifest_path, ports, log_stream
        return Starlette(
            routes=[
                Route("/v1/analyses", text, methods=["POST"]),
                Route("/v1/drafts", text, methods=["POST"]),
            ]
        )

    run = run_cases(MANIFEST, [_case("a")], GatePorts(labels=FAKE_LABELS), BEARER, build=build)

    (observation,) = run.observations
    assert (observation.analysis.status, observation.analysis.body) == (502, {})
    assert (observation.draft.status, observation.draft.body) == (502, {})


def test_settings_that_the_candidate_refuses_name_the_settings_only() -> None:
    def build(manifest_path: Path, ports: CandidatePorts, log_stream: TextIO) -> Starlette:
        del manifest_path, ports, log_stream
        raise SettingsInvalidError(("GEMINI_MODEL",))

    with pytest.raises(CandidateSettingsInvalidError) as refused:
        run_cases(MANIFEST, [_case("a")], GatePorts(labels=FAKE_LABELS), BEARER, build=build)

    assert refused.value.setting_names == ("GEMINI_MODEL",)
    assert str(refused.value) == "The settings of the candidate are refused: GEMINI_MODEL"

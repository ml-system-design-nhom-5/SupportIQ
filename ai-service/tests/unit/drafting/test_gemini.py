"""One Gemini call sends the prompts of the release and the request as data, and reads the reply."""

import dataclasses
from http import HTTPStatus

import httpx
import pytest

from supportiq_ai_service.drafting import LlmFailure, TokenUsage, UnanswerableRequest, WrittenDraft
from supportiq_ai_service.drafting.adapters.gemini import (
    GeminiCallError,
    GeminiClient,
    GeminiFailure,
)
from supportiq_ai_service.platform.egress import EgressAllowList, create_egress_client
from tests.unit.drafting.fakes import (
    API_KEY,
    AUTHORITY_INSTRUCTIONS,
    OPTIONS,
    PROMPTS,
    REQUEST,
    SYSTEM_INSTRUCTIONS,
    ScriptedNetwork,
    answer,
    error_response,
    gemini_client,
    gemini_response,
    retry_info,
)
from tests.unit.platform.fakes import FakeClock

TIMEOUT_SECONDS = 4.0
USAGE = TokenUsage(input_token_count=12, output_token_count=10)


def _failure(network: ScriptedNetwork, clock: FakeClock | None = None) -> GeminiCallError:
    with pytest.raises(GeminiCallError) as raised:
        gemini_client(network, clock).call(REQUEST, TIMEOUT_SECONDS)
    assert API_KEY not in str(raised.value)
    return raised.value


def test_a_call_sends_the_prompt_and_the_request_as_data_with_the_key_in_its_header() -> None:
    network = ScriptedNetwork([gemini_response()])

    gemini_client(network).call(REQUEST, TIMEOUT_SECONDS)

    (request,) = network.requests
    assert request.url == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite"
        ":generateContent"
    )
    assert request.headers["x-goog-api-key"] == API_KEY
    assert API_KEY not in request.content.decode()
    (payload,) = network.payloads()
    assert payload["systemInstruction"] == {"parts": [{"text": SYSTEM_INSTRUCTIONS}]}
    assert network.user_data() == {
        "message": REQUEST.message,
        "intent": "track_order",
        "policy_sources": [
            {
                "source_id": "S1",
                "document_id": "SAMPLE-DELIVERY-001",
                "version": "1.0",
                "title": "A fake delivery policy",
                "text": "A fake passage about deliveries.",
            }
        ],
        "order_facts": [{"source_id": "S2", "field": "shipment_status", "value": "in_transit"}],
    }


def test_when_authority_is_required_the_prompt_asks_for_supporting_information_only() -> None:
    network = ScriptedNetwork([gemini_response(), gemini_response()])
    client = gemini_client(network)

    client.call(REQUEST, TIMEOUT_SECONDS)
    client.call(dataclasses.replace(REQUEST, requires_authority=True), TIMEOUT_SECONDS)

    without, with_authority = (
        payload["systemInstruction"]["parts"][0]["text"] for payload in network.payloads()
    )
    assert AUTHORITY_INSTRUCTIONS not in without
    assert with_authority == f"{PROMPTS.system_instructions}\n\n{AUTHORITY_INSTRUCTIONS}"


def test_the_output_must_follow_the_schema_of_the_request() -> None:
    network = ScriptedNetwork([gemini_response()])

    gemini_client(network).call(REQUEST, TIMEOUT_SECONDS)

    (payload,) = network.payloads()
    config = payload["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseSchema"]["required"] == ["answerable", "answer", "citations"]
    assert config["maxOutputTokens"] == OPTIONS.max_output_tokens
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert "temperature" not in config


def test_a_gemini_2_5_model_gets_the_temperature_and_no_thinking() -> None:
    network = ScriptedNetwork([gemini_response()])
    options = dataclasses.replace(OPTIONS, model="gemini-2.5-flash")

    gemini_client(network, options=options).call(REQUEST, TIMEOUT_SECONDS)

    (payload,) = network.payloads()
    assert payload["generationConfig"]["temperature"] == OPTIONS.temperature
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}


def test_another_gemini_model_gets_a_low_thinking_level() -> None:
    network = ScriptedNetwork([gemini_response()])
    options = dataclasses.replace(OPTIONS, model="gemini-2.0-flash")

    gemini_client(network, options=options).call(REQUEST, TIMEOUT_SECONDS)

    (payload,) = network.payloads()
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "temperature" not in payload["generationConfig"]


def test_a_draft_is_read_with_its_citations_and_tokens_thinking_counted_as_output() -> None:
    network = ScriptedNetwork([gemini_response(answer("Your order is in_transit [S2].  "))])

    reply = gemini_client(network).call(REQUEST, TIMEOUT_SECONDS)

    assert reply == WrittenDraft(
        text="Your order is in_transit [S2].",
        cited_source_ids=("S2",),
        is_clarification=False,
        usage=USAGE,
    )


def test_a_request_that_the_sources_do_not_answer_gives_no_draft() -> None:
    network = ScriptedNetwork([gemini_response(answer("", (), answerable=False))])

    reply = gemini_client(network).call(REQUEST, TIMEOUT_SECONDS)

    assert reply == UnanswerableRequest(usage=USAGE)


@pytest.mark.parametrize(
    "output",
    [
        "not JSON",
        '{"answerable": true, "answer": "A draft", "citations": []',
        '{"answerable": "yes", "answer": "A draft", "citations": []}',
        '{"answerable": true, "answer": "A draft", "citations": [], "extra": 1}',
        '{"answerable": true, "answer": "  ", "citations": []}',
    ],
)
def test_an_output_that_breaks_the_schema_is_refused_with_its_tokens(output: str) -> None:
    error = _failure(ScriptedNetwork([gemini_response(output)]))

    assert (error.failure, error.usage) == (GeminiFailure.INVALID_OUTPUT, USAGE)
    assert error.failure.llm_failure is LlmFailure.INVALID_OUTPUT


def test_a_blocked_or_unfinished_answer_is_refused_with_its_tokens() -> None:
    blocked = httpx.Response(
        HTTPStatus.OK,
        json={
            "promptFeedback": {"blockReason": "SAFETY"},
            "usageMetadata": {"promptTokenCount": 12},
        },
    )

    errors = [
        _failure(ScriptedNetwork([blocked])),
        _failure(ScriptedNetwork([gemini_response(finish_reason="MAX_TOKENS")])),
    ]

    assert [(error.failure, error.usage) for error in errors] == [
        (GeminiFailure.INVALID_OUTPUT, TokenUsage(12, 0)),
        (GeminiFailure.INVALID_OUTPUT, USAGE),
    ]


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b'{"candidates": []}',
        b'{"usageMetadata": {"promptTokenCount": -1}}',
        b'{"usageMetadata": {"promptTokenCount": "12"}}',
    ],
)
def test_a_response_without_valid_usage_is_refused(body: bytes) -> None:
    error = _failure(ScriptedNetwork([httpx.Response(HTTPStatus.OK, content=body)]))

    assert (error.failure, error.usage) == (GeminiFailure.INVALID_OUTPUT, None)


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (HTTPStatus.BAD_REQUEST, GeminiFailure.REJECTED),
        (HTTPStatus.UNAUTHORIZED, GeminiFailure.REJECTED),
        (HTTPStatus.FORBIDDEN, GeminiFailure.REJECTED),
        (HTTPStatus.NOT_FOUND, GeminiFailure.REJECTED),
        (HTTPStatus.REQUEST_TIMEOUT, GeminiFailure.REJECTED),
        (HTTPStatus.INTERNAL_SERVER_ERROR, GeminiFailure.REJECTED),
        (HTTPStatus.BAD_GATEWAY, GeminiFailure.UNAVAILABLE),
        (HTTPStatus.SERVICE_UNAVAILABLE, GeminiFailure.UNAVAILABLE),
        (HTTPStatus.GATEWAY_TIMEOUT, GeminiFailure.UNAVAILABLE),
        (HTTPStatus.TOO_MANY_REQUESTS, GeminiFailure.RATE_LIMITED),
    ],
)
def test_only_the_statuses_of_err_12_are_retryable(
    status: HTTPStatus, failure: GeminiFailure
) -> None:
    error = _failure(ScriptedNetwork([error_response(status)]))

    assert error.failure is failure
    assert error.failure.retryable is (failure is not GeminiFailure.REJECTED)
    assert error.failure.llm_failure is LlmFailure.UNAVAILABLE
    assert (error.usage, error.retry_after_seconds, error.retry_forbidden) == (None, None, False)


@pytest.mark.parametrize(
    ("headers", "body", "delay", "forbidden"),
    [
        ({"retry-after": "3"}, None, 3.0, False),
        ({"retry-after": "0"}, None, 0.0, False),
        ({"retry-after": " 1.5 "}, None, 1.5, False),
        ({"retry-after": "Fri, 13 Nov 2026 09:00:10 GMT"}, None, 10.0, False),
        ({"retry-after": "soon"}, None, None, True),
        ({"retry-after": "-1"}, None, None, True),
        ({"retry-after": "86401"}, None, None, True),
        ({"retry-after": "Fri, 13 Nov 2026 09:00:10"}, None, None, True),
        ({}, retry_info("2s"), 2.0, False),
        ({}, retry_info("2"), None, False),
        ({}, retry_info("2.5xs"), None, False),
        ({}, {"error": {"details": [{"@type": "other", "retryDelay": "2s"}]}}, None, False),
    ],
)
def test_the_delay_that_gemini_asks_for_is_read_defensively(
    headers: dict[str, str], body: object, delay: float | None, *, forbidden: bool
) -> None:
    network = ScriptedNetwork(
        [error_response(HTTPStatus.SERVICE_UNAVAILABLE, body=body, headers=headers)]
    )

    error = _failure(network, FakeClock())

    assert (error.retry_after_seconds, error.retry_forbidden) == (delay, forbidden)


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "Quota exceeded: requests per day."}},
        {
            "error": {
                "message": "Resource exhausted.",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}],
                    }
                ],
            }
        },
    ],
)
def test_a_hard_quota_forbids_every_retry(body: object) -> None:
    network = ScriptedNetwork(
        [error_response(HTTPStatus.TOO_MANY_REQUESTS, body=body, headers={"retry-after": "1"})]
    )

    error = _failure(network)

    assert (error.failure, error.retry_forbidden) == (GeminiFailure.RATE_LIMITED, True)


@pytest.mark.parametrize(
    ("raised", "failure"),
    [
        (httpx.ReadTimeout("slow"), GeminiFailure.TIMEOUT),
        (httpx.ConnectTimeout("slow"), GeminiFailure.TIMEOUT),
        (httpx.ConnectError("down"), GeminiFailure.UNAVAILABLE),
        (httpx.RemoteProtocolError("closed"), GeminiFailure.UNAVAILABLE),
    ],
)
def test_a_transport_failure_is_retryable(raised: httpx.HTTPError, failure: GeminiFailure) -> None:
    error = _failure(ScriptedNetwork([raised]))

    assert (error.failure, error.failure.retryable) == (failure, True)


def test_a_refusal_of_the_egress_allow_list_is_never_retried() -> None:
    network = ScriptedNetwork([])
    # An allow-list without the host of Gemini.
    http_client = create_egress_client(
        EgressAllowList(version="1", hosts=frozenset({"other.example"})), network
    )
    client = GeminiClient(http_client, OPTIONS, PROMPTS, FakeClock())

    with pytest.raises(GeminiCallError) as raised:
        client.call(REQUEST, TIMEOUT_SECONDS)

    assert (raised.value.failure, raised.value.failure.retryable) == (
        GeminiFailure.EGRESS_REFUSED,
        False,
    )
    assert raised.value.failure.llm_failure is LlmFailure.UNAVAILABLE
    assert network.requests == []


def test_the_timeout_of_an_attempt_bounds_every_phase_of_the_request() -> None:
    network = ScriptedNetwork([gemini_response()])

    gemini_client(network).call(REQUEST, TIMEOUT_SECONDS)

    (request,) = network.requests
    assert request.extensions["timeout"] == {
        "connect": TIMEOUT_SECONDS,
        "read": TIMEOUT_SECONDS,
        "write": TIMEOUT_SECONDS,
        "pool": TIMEOUT_SECONDS,
    }


@pytest.mark.parametrize(
    "details",
    [
        [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "per day"}],
        [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": "per day"}],
        [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"x": "y"}]}],
        [
            {
                "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                "violations": [{"quotaId": "GenerateRequestsPerDayPerProject"}],
            }
        ],
    ],
)
def test_a_rate_limit_without_a_hard_quota_may_be_retried(details: list[object]) -> None:
    body = {"error": {"message": "Resource exhausted.", "details": details}}
    network = ScriptedNetwork([error_response(HTTPStatus.TOO_MANY_REQUESTS, body=body)])

    error = _failure(network)

    assert (error.failure, error.retry_forbidden) == (GeminiFailure.RATE_LIMITED, False)


def test_a_hard_quota_applies_only_to_a_rate_limit() -> None:
    body = {"error": {"message": "Quota exceeded: requests per day."}}
    network = ScriptedNetwork([error_response(HTTPStatus.SERVICE_UNAVAILABLE, body=body)])

    error = _failure(network)

    assert (error.failure, error.retry_forbidden) == (GeminiFailure.UNAVAILABLE, False)

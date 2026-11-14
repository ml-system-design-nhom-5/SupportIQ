"""Adapter tests of `HttpAiService`: timeouts, retries, errors, and headers (TEST-01, ERR-21).

The client talks to an in-memory `httpx.MockTransport`, so no socket opens and no test waits.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider

from supportiq_backend.suggestions import (
    AiServiceContractError,
    AiServiceUnavailableError,
    KbDocumentId,
    KbDocumentVersion,
    KbDocumentVersionTag,
    SuggestionRequest,
)
from supportiq_backend.suggestions.adapters.ai_service_client import (
    AiServiceTimeouts,
    HttpAiService,
    create_ai_service_client,
)

EXAMPLES = Path(__file__).parents[4] / "contracts" / "examples"
BASE_URL = "http://ai-service.test"
SERVICE_TOKEN = "service-token-for-tests"
CALL_AND_RETRY = 2
TIMEOUTS = AiServiceTimeouts(analysis_ms=3_000, draft_ms=11_000, read_ms=3_000)
REQUEST = SuggestionRequest(
    message="Where is my refund for [ORDER_ID_1]?",
    order_context=None,
    as_of=datetime(2026, 11, 5, 8, 12, 30, tzinfo=UTC),
    intent_override=None,
)
# The document version of the example `getKbDocumentVersion/found.json`.
DOCUMENT_ID = KbDocumentId("SAMPLE-REFUND-001")
DOCUMENT_VERSION = KbDocumentVersionTag("1.0")
DOCUMENT_PATH = "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0"


def example_body(operation: str, name: str) -> bytes:
    example = json.loads((EXAMPLES / operation / f"{name}.json").read_text(encoding="utf-8"))
    return json.dumps(example["value"]).encode()


@dataclass(slots=True)
class ScriptedAiService:
    """Answer each call with the next response of a script, and keep every request."""

    responses: list[httpx.Response | httpx.RequestError]
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Answer the next scripted response."""
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, httpx.RequestError):
            raise response
        return response


def build_client(script: ScriptedAiService) -> HttpAiService:
    client = create_ai_service_client(
        BASE_URL, SERVICE_TOKEN, transport=httpx.MockTransport(script.handle)
    )
    return HttpAiService(client, TIMEOUTS)


def ok(operation: str, name: str) -> httpx.Response:
    return httpx.Response(HTTPStatus.OK, content=example_body(operation, name))


@pytest.mark.anyio
async def test_every_call_sends_the_service_token_and_the_json_body() -> None:
    script = ScriptedAiService([ok("createAnalysis", "draft")])

    await build_client(script).analyze(REQUEST)

    (sent,) = script.requests
    assert sent.headers["Authorization"] == f"Bearer {SERVICE_TOKEN}"
    assert sent.url.path == "/v1/analyses"
    assert json.loads(sent.content)["as_of"] == "2026-11-05T08:12:30Z"


@pytest.mark.anyio
async def test_a_call_inside_a_span_sends_its_traceparent() -> None:
    script = ScriptedAiService([ok("createDraft", "draft-ready")])
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("run_suggestion_job"):
        await build_client(script).draft(REQUEST)

    assert script.requests[0].headers["traceparent"].startswith("00-")


@pytest.mark.anyio
@pytest.mark.parametrize("status", [HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE])
async def test_a_502_or_503_is_retried_once(status: HTTPStatus) -> None:
    script = ScriptedAiService([httpx.Response(status), ok("createDraft", "draft-ready")])

    received = await build_client(script).draft(REQUEST)

    assert len(script.requests) == CALL_AND_RETRY
    assert received.body


@pytest.mark.anyio
async def test_a_connection_error_is_retried_once() -> None:
    script = ScriptedAiService([httpx.ConnectError("refused"), ok("createAnalysis", "draft")])

    await build_client(script).analyze(REQUEST)

    assert len(script.requests) == CALL_AND_RETRY


@pytest.mark.anyio
async def test_a_second_failure_makes_the_call_unavailable() -> None:
    script = ScriptedAiService(
        [httpx.Response(HTTPStatus.SERVICE_UNAVAILABLE), httpx.ConnectError("refused")]
    )

    with pytest.raises(AiServiceUnavailableError):
        await build_client(script).draft(REQUEST)


@pytest.mark.anyio
async def test_a_timeout_is_never_retried() -> None:
    script = ScriptedAiService([httpx.ReadTimeout("slow"), ok("createDraft", "draft-ready")])

    with pytest.raises(AiServiceUnavailableError):
        await build_client(script).draft(REQUEST)

    assert len(script.requests) == 1


@pytest.mark.anyio
async def test_a_500_makes_the_call_unavailable_without_a_retry() -> None:
    script = ScriptedAiService([httpx.Response(HTTPStatus.INTERNAL_SERVER_ERROR)])

    with pytest.raises(AiServiceUnavailableError) as caught:
        await build_client(script).analyze(REQUEST)

    assert not isinstance(caught.value, AiServiceContractError)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT, HTTPStatus.NOT_FOUND]
)
async def test_a_4xx_is_a_contract_error(status: HTTPStatus) -> None:
    script = ScriptedAiService(
        [httpx.Response(status, content=example_body("problems", "invalid-request"))]
    )

    with pytest.raises(AiServiceContractError):
        await build_client(script).draft(REQUEST)

    assert len(script.requests) == 1


@pytest.mark.anyio
async def test_a_body_that_is_not_json_is_a_contract_error() -> None:
    script = ScriptedAiService([httpx.Response(HTTPStatus.OK, content=b"<html>")])

    with pytest.raises(AiServiceContractError):
        await build_client(script).analyze(REQUEST)


@pytest.mark.anyio
async def test_a_body_that_its_encoding_cannot_decode_is_a_contract_error() -> None:
    body = httpx.ByteStream(b"not gzip")
    script = ScriptedAiService(
        [httpx.Response(HTTPStatus.OK, stream=body, headers={"Content-Encoding": "gzip"})]
    )

    with pytest.raises(AiServiceContractError):
        await build_client(script).analyze(REQUEST)


@pytest.mark.anyio
async def test_any_other_error_of_the_library_makes_the_call_unavailable() -> None:
    script = ScriptedAiService([httpx.TooManyRedirects("redirect loop")])

    with pytest.raises(AiServiceUnavailableError) as caught:
        await build_client(script).draft(REQUEST)

    assert not isinstance(caught.value, AiServiceContractError)
    assert len(script.requests) == 1


@pytest.mark.anyio
async def test_the_read_of_the_versions_is_not_retried() -> None:
    script = ScriptedAiService([httpx.Response(HTTPStatus.SERVICE_UNAVAILABLE)])

    with pytest.raises(AiServiceUnavailableError):
        await build_client(script).fetch_asset_versions()

    assert len(script.requests) == 1


@pytest.mark.anyio
async def test_the_read_of_the_versions_returns_the_loaded_kb_version() -> None:
    script = ScriptedAiService([ok("getAssetVersions", "loaded")])

    versions = await build_client(script).fetch_asset_versions()

    assert versions.kb_version == "kb-sample-1"


def found_document(**changes: object) -> httpx.Response:
    example = json.loads(example_body("getKbDocumentVersion", "found"))
    return httpx.Response(HTTPStatus.OK, content=json.dumps(example | changes).encode())


async def read_document(script: ScriptedAiService) -> KbDocumentVersion | None:
    return await build_client(script).fetch_kb_document_version(DOCUMENT_ID, DOCUMENT_VERSION)


@pytest.mark.anyio
async def test_the_read_of_a_kb_document_version_gets_its_path_and_parses_every_field() -> None:
    script = ScriptedAiService([found_document(last_reviewed_at="2026-06-30T12:00:00.125Z")])

    document = await read_document(script)

    (sent,) = script.requests
    assert (sent.method, sent.url.path, sent.content) == ("GET", DOCUMENT_PATH, b"")
    assert document == KbDocumentVersion(
        document_id=DOCUMENT_ID,
        version=DOCUMENT_VERSION,
        title="Sample refund document",
        body=(
            "This is sample text. It is not KB content and not a policy. The document version"
            " opens here in full, so staff can check a citation against its source."
        ),
        policy_key="sample_refund_review",
        effective_start_at=datetime(2026, 1, 1, tzinfo=UTC),
        effective_end_at=None,
        owner="Policy owner",
        source="Sample source document",
        last_reviewed_at=datetime(2026, 6, 30, 12, 0, 0, 125_000, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_the_kb_read_sends_the_service_token_and_its_traceparent() -> None:
    script = ScriptedAiService([found_document()])
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("get_console_kb_document_version"):
        await read_document(script)

    (sent,) = script.requests
    assert sent.headers["Authorization"] == f"Bearer {SERVICE_TOKEN}"
    assert sent.headers["traceparent"].startswith("00-")


@pytest.mark.anyio
async def test_a_404_of_the_kb_read_means_that_the_loaded_kb_has_no_such_version() -> None:
    not_found = example_body("problems", "not-found")
    script = ScriptedAiService([httpx.Response(HTTPStatus.NOT_FOUND, content=not_found)])

    assert await read_document(script) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(HTTPStatus.SERVICE_UNAVAILABLE),
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
    ],
    ids=["503", "connection-error", "timeout"],
)
async def test_a_failed_kb_read_is_unavailable_and_never_retried(
    failure: httpx.Response | httpx.RequestError,
) -> None:
    script = ScriptedAiService([failure, found_document()])

    with pytest.raises(AiServiceUnavailableError) as caught:
        await read_document(script)

    assert not isinstance(caught.value, AiServiceContractError)
    assert len(script.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status", [HTTPStatus.UNAUTHORIZED, HTTPStatus.UNPROCESSABLE_CONTENT])
async def test_another_4xx_of_the_kb_read_is_a_contract_error(status: HTTPStatus) -> None:
    script = ScriptedAiService(
        [httpx.Response(status, content=example_body("problems", "invalid-request"))]
    )

    with pytest.raises(AiServiceContractError):
        await read_document(script)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "change",
    [
        {"body": ""},
        {"title": 7},
        {"effective_start_at": "2026-01-01T07:00:00+07:00"},
        {"document_id": "SAMPLE-REFUND-002"},
        {"version": "2.0"},
    ],
    ids=["empty-body", "number-title", "offset-time", "other-document", "other-version"],
)
async def test_a_kb_document_version_outside_the_contract_is_a_contract_error(
    change: dict[str, object],
) -> None:
    script = ScriptedAiService([found_document(**change)])

    with pytest.raises(AiServiceContractError):
        await read_document(script)


@pytest.mark.anyio
async def test_each_identifier_of_the_kb_read_stays_one_segment_of_the_path() -> None:
    script = ScriptedAiService([httpx.Response(HTTPStatus.NOT_FOUND)])

    await build_client(script).fetch_kb_document_version(
        KbDocumentId("a/b?c#d"), KbDocumentVersionTag("1 0")
    )

    assert script.requests[0].url.raw_path == b"/v1/kb-documents/a%2Fb%3Fc%23d/versions/1%200"

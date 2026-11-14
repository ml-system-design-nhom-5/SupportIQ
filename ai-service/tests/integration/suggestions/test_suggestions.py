"""`createAnalysis` and `createDraft` over HTTP: strict requests and contract bodies."""

import json
from http import HTTPStatus
from pathlib import Path

import pytest

from supportiq_ai_service.platform import EventName
from tests.integration.application import SERVICE_TOKEN_HEADERS, running_ai_service
from tests.unit.release.fakes import StaticReleaseSource
from tests.unit.suggestions.fakes import EXAMPLE_LLM_UNAVAILABLE, FailingPipeline, FakePipeline

pytestmark = pytest.mark.anyio

EXAMPLES = Path(__file__).parents[4] / "contracts/examples"
ANALYSES = "/v1/analyses"
DRAFTS = "/v1/drafts"
SUGGESTION_PATHS = (ANALYSES, DRAFTS)
VALID_REQUEST = {"message": "Where is my refund for [ORDER_ID_1]?", "as_of": "2026-11-05T09:30:00Z"}
MESSAGE_LIMIT = 4_000


def example(name: str) -> dict[str, object]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))["value"]


async def test_an_analysis_is_the_body_of_the_pipeline_result() -> None:
    async with running_ai_service() as service:
        response = await service.client.post(
            ANALYSES, json=VALID_REQUEST, headers=SERVICE_TOKEN_HEADERS
        )

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == example("createAnalysis/draft.json")


@pytest.mark.parametrize(
    ("pipeline", "example_name"),
    [
        (FakePipeline(), "createDraft/draft-ready.json"),
        (FakePipeline(outcome=EXAMPLE_LLM_UNAVAILABLE), "createDraft/llm-unavailable.json"),
    ],
)
async def test_a_draft_outcome_is_the_body_of_the_pipeline_result(
    pipeline: FakePipeline, example_name: str
) -> None:
    async with running_ai_service(pipeline=pipeline) as service:
        response = await service.client.post(
            DRAFTS, json=VALID_REQUEST, headers=SERVICE_TOKEN_HEADERS
        )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == example(example_name)


@pytest.mark.parametrize("path", SUGGESTION_PATHS)
async def test_the_loaded_kb_version_is_accepted(path: str) -> None:
    body = VALID_REQUEST | {"kb_version": "kb-sample-1"}
    async with running_ai_service() as service:
        response = await service.client.post(path, json=body, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.OK


@pytest.mark.parametrize("path", SUGGESTION_PATHS)
async def test_another_kb_version_is_an_invalid_request(path: str) -> None:
    pipeline = FakePipeline()
    body = VALID_REQUEST | {"kb_version": "kb-other"}
    async with running_ai_service(pipeline=pipeline) as service:
        response = await service.client.post(path, json=body, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    expected = example("problems/unknown-kb-version.json")
    assert response.json()["detail"] == expected["detail"]
    assert pipeline.requests == []


@pytest.mark.parametrize("path", SUGGESTION_PATHS)
@pytest.mark.parametrize(
    ("content", "location"),
    [
        (b"{not json", "body"),
        (json.dumps({"as_of": "2026-11-05T09:30:00Z"}).encode(), "body.message"),
        (json.dumps(VALID_REQUEST | {"ticket_id": "T-1"}).encode(), "body.ticket_id"),
        (json.dumps(VALID_REQUEST | {"message": ""}).encode(), "body.message"),
        (
            json.dumps(VALID_REQUEST | {"message": "x" * (MESSAGE_LIMIT + 1)}).encode(),
            "body.message",
        ),
        (json.dumps(VALID_REQUEST | {"message": None}).encode(), "body.message"),
        (json.dumps(VALID_REQUEST | {"kb_version": None}).encode(), "body.kb_version"),
        (json.dumps(VALID_REQUEST | {"as_of": "2026-11-05T09:30:00"}).encode(), "body.as_of"),
        (
            json.dumps(VALID_REQUEST | {"as_of": "2026-11-05T16:30:00+07:00"}).encode(),
            "body.as_of",
        ),
        (
            json.dumps(VALID_REQUEST | {"intent_override": "refund_now"}).encode(),
            "body.intent_override",
        ),
        (
            json.dumps(VALID_REQUEST | {"order_context": {"order_id": "ORD-1"}}).encode(),
            "body.order_context.order_id",
        ),
        (
            json.dumps(VALID_REQUEST | {"order_context": {"order_status": "lost"}}).encode(),
            "body.order_context.order_status",
        ),
        (
            json.dumps(
                VALID_REQUEST | {"order_context": {"placed_at": "2026-11-05T09:30:00"}}
            ).encode(),
            "body.order_context.placed_at",
        ),
    ],
)
async def test_a_request_that_breaks_the_contract_is_invalid_and_names_only_the_location(
    path: str, content: bytes, location: str
) -> None:
    pipeline = FakePipeline()
    headers = SERVICE_TOKEN_HEADERS | {"Content-Type": "application/json"}
    async with running_ai_service(pipeline=pipeline) as service:
        response = await service.client.post(path, content=content, headers=headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    body = response.json()
    assert body["type"] == "urn:supportiq:problem:invalid-request"
    assert location in body["detail"]
    assert "ORD-1" not in response.text
    assert "refund_now" not in response.text
    assert pipeline.requests == []


@pytest.mark.parametrize("path", SUGGESTION_PATHS)
async def test_without_a_loaded_release_a_suggestion_is_not_ready(path: str) -> None:
    pipeline = FakePipeline()
    async with running_ai_service(StaticReleaseSource(None), pipeline=pipeline) as service:
        response = await service.client.post(
            path, json=VALID_REQUEST, headers=SERVICE_TOKEN_HEADERS
        )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"
    assert pipeline.requests == []


@pytest.mark.parametrize("path", SUGGESTION_PATHS)
async def test_a_failure_of_the_pipeline_is_an_internal_error_without_the_message(
    path: str,
) -> None:
    async with running_ai_service(pipeline=FailingPipeline()) as service:
        response = await service.client.post(
            path, json=VALID_REQUEST, headers=SERVICE_TOKEN_HEADERS
        )

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "pipeline failed" not in response.text
    assert "ORDER_ID_1" not in response.text
    (failed,) = service.events.of(EventName.REQUEST_FAILED)
    assert failed.attributes == {"error_type": "RuntimeError"}

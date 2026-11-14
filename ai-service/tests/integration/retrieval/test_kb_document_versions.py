"""`getKbDocumentVersion` over HTTP: only versions of the loaded KB (UI-20, DATA-56)."""

import json
from http import HTTPStatus
from pathlib import Path

import pytest

from tests.integration.application import SERVICE_TOKEN_HEADERS, running_ai_service
from tests.unit.release.fakes import StaticReleaseSource

pytestmark = pytest.mark.anyio

EXAMPLE = Path(__file__).parents[4] / "contracts/examples/getKbDocumentVersion/found.json"
FOUND_PATH = "/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0"


async def test_a_version_of_the_loaded_kb_is_its_contract_body() -> None:
    async with running_ai_service() as service:
        response = await service.client.get(FOUND_PATH, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == json.loads(EXAMPLE.read_text(encoding="utf-8"))["value"]


@pytest.mark.parametrize(
    "path",
    [
        "/v1/kb-documents/SAMPLE-REFUND-001/versions/0.9",
        "/v1/kb-documents/UNKNOWN-001/versions/1.0",
    ],
)
async def test_a_version_outside_the_loaded_kb_is_not_found(path: str) -> None:
    async with running_ai_service() as service:
        response = await service.client.get(path, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["type"] == "urn:supportiq:problem:not-found"


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/v1/kb-documents/-starts-with-a-dash/versions/1.0", "path.document_id"),
        (f"/v1/kb-documents/{'A' * 65}/versions/1.0", "path.document_id"),
        ("/v1/kb-documents/SAMPLE-REFUND-001/versions/1.0%20beta", "path.version"),
    ],
)
async def test_a_path_parameter_that_breaks_its_schema_is_invalid(path: str, location: str) -> None:
    async with running_ai_service() as service:
        response = await service.client.get(path, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_CONTENT
    assert location in response.json()["detail"]


async def test_without_a_loaded_release_no_document_is_served() -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.get(FOUND_PATH, headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE

"""`getAssetVersions` returns `AssetVersions` itself, or `503` without a release (DATA-56)."""

import json
from http import HTTPStatus
from pathlib import Path

import pytest

from tests.integration.application import SERVICE_TOKEN_HEADERS, running_ai_service
from tests.unit.release.fakes import StaticReleaseSource

pytestmark = pytest.mark.anyio

EXAMPLE = Path(__file__).parents[4] / "contracts/examples/getAssetVersions/loaded.json"


async def test_the_asset_versions_are_the_body_itself_without_a_wrapper() -> None:
    async with running_ai_service() as service:
        response = await service.client.get("/v1/asset-versions", headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/json"
    assert response.json() == json.loads(EXAMPLE.read_text(encoding="utf-8"))["value"]


async def test_without_a_loaded_release_the_asset_versions_are_not_ready() -> None:
    async with running_ai_service(StaticReleaseSource(None)) as service:
        response = await service.client.get("/v1/asset-versions", headers=SERVICE_TOKEN_HEADERS)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"

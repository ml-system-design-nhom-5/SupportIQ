"""The route of `getAssetVersions` and the mapping of its body (DATA-56)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.generated import AssetVersion
from app.generated import AssetVersions as AssetVersionsBody
from app.platform.web import json_response, provide
from app.release.application import GetAssetVersions
from app.release.domain import AssetVersions


def build_release_router(get_asset_versions: GetAssetVersions) -> APIRouter:
    """Build the router of the release operations.

    Args:
        get_asset_versions: The use case of `getAssetVersions`.

    Returns:
        The router with `GET /v1/asset-versions`. The composition root adds the service token
        check to it.
    """
    router = APIRouter()
    use_case = Depends(provide(get_asset_versions))

    @router.get("/v1/asset-versions")
    async def handle_get_asset_versions(
        get_versions: Annotated[GetAssetVersions, use_case],
    ) -> Response:
        return json_response(asset_versions_body(get_versions.execute()))

    return router


def asset_versions_body(versions: AssetVersions) -> AssetVersionsBody:
    """Map the asset versions to the contract's `AssetVersions`, itself and not wrapped.

    Args:
        versions: The versions of the loaded release.

    Returns:
        The body of `getAssetVersions`, also embedded in every analysis and draft.
    """
    return AssetVersionsBody(
        release_id=versions.release_id,
        model_version=AssetVersion(versions.model_version),
        kb_version=AssetVersion(versions.kb_version),
        mapping_version=AssetVersion(versions.mapping_version),
        prompt_version=AssetVersion(versions.prompt_version),
        routing_version=AssetVersion(versions.routing_version),
        index_version=AssetVersion(versions.index_version),
    )

"""The versions in use, for the admin area (`getAdminVersions`, ADR-0012).

The response holds versions only: no ticket, message, order, or report (SEC-41). The role
check is the first step of the use case, before ai-service is read.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from supportiq_backend.accounts import AuthenticatedSession
from supportiq_backend.generated import AdminVersionsView, AiServiceStatus, AssetVersion
from supportiq_backend.generated import AssetVersions as ContractAssetVersions
from supportiq_backend.platform.web import RequestDependency, json_response, provide
from supportiq_backend.suggestions.application import GetAdminVersions, VersionsInUse
from supportiq_backend.suggestions.domain import AssetVersions

ADMIN_VERSIONS_PATH = "/v1/admin/versions"


@dataclass(frozen=True, slots=True)
class AdminVersionsRoutes:
    """What the route of the versions in use needs from the composition root.

    Attributes:
        get_versions: The read.
        current_session: The session of a request.
    """

    get_versions: GetAdminVersions
    current_session: RequestDependency[AuthenticatedSession]


def to_admin_versions_view(versions: VersionsInUse) -> AdminVersionsView:
    """Map the versions in use to the contract.

    Args:
        versions: The versions.

    Returns:
        The contract model: `ai_service_versions` is present exactly when
        `ai_service_status` is `available`.
    """
    if versions.ai_service_versions is None:
        return AdminVersionsView(
            backend_version=versions.backend_version,
            ai_service_status=AiServiceStatus.unavailable,
        )
    return AdminVersionsView(
        backend_version=versions.backend_version,
        ai_service_status=AiServiceStatus.available,
        ai_service_versions=to_asset_versions_view(versions.ai_service_versions),
    )


def to_asset_versions_view(versions: AssetVersions) -> ContractAssetVersions:
    """Map the release and asset versions of ai-service to the contract.

    Args:
        versions: The versions.

    Returns:
        The contract model.
    """
    return ContractAssetVersions(
        release_id=versions.release_id,
        model_version=AssetVersion(versions.model_version),
        kb_version=AssetVersion(versions.kb_version),
        mapping_version=AssetVersion(versions.mapping_version),
        prompt_version=AssetVersion(versions.prompt_version),
        routing_version=AssetVersion(versions.routing_version),
        index_version=AssetVersion(versions.index_version),
    )


def build_admin_versions_router(routes: AdminVersionsRoutes) -> APIRouter:
    """Build the router of the versions in use.

    Args:
        routes: The use case and the session dependency.

    Returns:
        The router.
    """
    router = APIRouter()
    current_session = Depends(routes.current_session)
    get_versions = Depends(provide(routes.get_versions))

    @router.get(ADMIN_VERSIONS_PATH, status_code=HTTPStatus.OK)
    async def handle_get_admin_versions(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetAdminVersions, get_versions],
    ) -> Response:
        versions = await use_case.execute(session.principal)
        return json_response(to_admin_versions_view(versions))

    return router

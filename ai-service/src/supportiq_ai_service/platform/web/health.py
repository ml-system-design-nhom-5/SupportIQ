"""The health checks `checkLiveness` and `checkReadiness` (ERR-18)."""

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from supportiq_ai_service.platform import CheckReadiness
from supportiq_ai_service.platform.web.responses import provide


def build_health_router(check_readiness: CheckReadiness) -> APIRouter:
    """Build the router of the health checks, which need no service token (ADR-0018, Access).

    Args:
        check_readiness: The readiness use case.

    Returns:
        The router with `GET /health/live` and `GET /health/ready`.
    """
    router = APIRouter()
    readiness = Depends(provide(check_readiness))

    @router.get("/health/live", status_code=HTTPStatus.NO_CONTENT)
    async def handle_check_liveness() -> Response:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    @router.get("/health/ready", status_code=HTTPStatus.NO_CONTENT)
    async def handle_check_readiness(
        use_case: Annotated[CheckReadiness, readiness],
    ) -> Response:
        use_case.execute()
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return router

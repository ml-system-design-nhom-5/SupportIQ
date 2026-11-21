"""The console's report route: `getConsoleReport`, for managers only.

The handler is thin: the role check runs before the period is parsed, so another role gets
`403` whatever it sent; then it parses the period, calls the use case, and maps the result
(ARCH-14, PY-36).
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.accounts import AuthenticatedSession
from app.platform.web import RequestDependency, json_response, provide
from app.reports.api.report_requests import parse_report_period
from app.reports.api.report_views import to_console_report
from app.reports.application import GetConsoleReport

CONSOLE_REPORTS_PATH = "/v1/console/reports"


@dataclass(frozen=True, slots=True)
class ConsoleReportRoutes:
    """What the report route needs from the composition root.

    Attributes:
        get_report: The report.
        current_session: The session of a request.
    """

    get_report: GetConsoleReport
    current_session: RequestDependency[AuthenticatedSession]


def build_console_reports_router(routes: ConsoleReportRoutes) -> APIRouter:
    """Build the router of the console's report.

    Args:
        routes: The use case and the session dependency.

    Returns:
        The router.
    """
    router = APIRouter()
    current_session = Depends(routes.current_session)
    get_report = Depends(provide(routes.get_report))

    @router.get(CONSOLE_REPORTS_PATH, status_code=HTTPStatus.OK)
    async def handle_get_console_report(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[GetConsoleReport, get_report],
        start_at: Annotated[str | None, Query()] = None,
        end_at: Annotated[str | None, Query()] = None,
    ) -> Response:
        manager = use_case.authorize(session.principal)
        period = parse_report_period(start_at, end_at)
        return json_response(to_console_report(await use_case.execute(manager, period)))

    return router

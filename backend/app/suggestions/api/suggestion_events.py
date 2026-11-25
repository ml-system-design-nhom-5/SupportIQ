"""The suggestion progress stream of the console (`getSuggestionEvents`, ADR-0022).

The handler checks the role first, reads the current state, and answers `204` when there is
nothing to follow, so every refusal is sent before the stream starts. The stream asks
`EventSource` to reconnect after 3 s, then sends one `suggestion` event per item, or a ping
comment. An event holds only the suggestion ID and the two part statuses (SEC-01).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.sse import EventSourceResponse

from app.accounts import AuthenticatedSession
from app.generated import AnalysisStatus, DraftStatus, SuggestionProgressEvent
from app.platform.web import RequestDependency, provide
from app.suggestions.application import WatchSuggestionProgress
from app.suggestions.domain import SuggestionProgress, SuggestionTicketId

SUGGESTION_EVENTS_PATH = "/v1/console/tickets/{ticket_id}/suggestion-events"
RETRY_FRAME = b"retry: 3000\n\n"
PING_FRAME = b": ping\n\n"
# A proxy must neither cache nor buffer the stream (ADR-0022, Context).
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@dataclass(frozen=True, slots=True)
class SuggestionEventsRoutes:
    """What the route of the stream needs from the composition root.

    Attributes:
        watch_progress: The stream.
        current_session: The session of a request.
    """

    watch_progress: WatchSuggestionProgress
    current_session: RequestDependency[AuthenticatedSession]


def to_event_frame(progress: SuggestionProgress) -> bytes:
    """Write one `suggestion` event whose data is a `SuggestionProgressEvent`.

    Args:
        progress: The part statuses of the current suggestion, which is never superseded.

    Returns:
        The event in the format of server-sent events.
    """
    data = SuggestionProgressEvent(
        suggestion_id=progress.suggestion_id,
        analysis_status=AnalysisStatus(progress.analysis_status.value),
        draft_status=DraftStatus(progress.draft_status.value),
    ).model_dump_json()
    return f"event: suggestion\ndata: {data}\n\n".encode()


def build_suggestion_events_router(routes: SuggestionEventsRoutes) -> APIRouter:
    """Build the router of the stream.

    Args:
        routes: The use case and the session dependency.

    Returns:
        The router.
    """
    router = APIRouter()
    current_session = Depends(routes.current_session)
    watch_progress = Depends(provide(routes.watch_progress))

    @router.get(SUGGESTION_EVENTS_PATH, status_code=HTTPStatus.OK)
    async def handle_get_suggestion_events(
        ticket_id: str,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[WatchSuggestionProgress, watch_progress],
    ) -> Response:
        use_case.authorize(session.principal)
        stream = await use_case.open(SuggestionTicketId(ticket_id))
        if stream is None:
            return Response(status_code=HTTPStatus.NO_CONTENT)
        return EventSourceResponse(_frames(stream), headers=STREAM_HEADERS)

    return router


async def _frames(stream: AsyncIterator[SuggestionProgress | None]) -> AsyncIterator[bytes]:
    yield RETRY_FRAME
    async for progress in stream:
        yield PING_FRAME if progress is None else to_event_frame(progress)

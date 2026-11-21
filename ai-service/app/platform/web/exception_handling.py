"""The single exception handler of ai-service (PY-38, ERR-03).

Every error that leaves a request becomes a Problem Details body here and nowhere else:
errors of ai-service, framework validation errors, unknown routes, and unexpected
exceptions. An error is logged once, here, where it is handled (ERR-05). Bodies never carry a
stack trace, an internal name, or a value that was sent (CON-12). This module follows the
exception handler of backend.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import assert_never, cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import iter_route_contexts
from starlette.exceptions import HTTPException
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform import (
    AiServiceError,
    ErrorCode,
    EventName,
    EventRecorder,
    InvalidRequestError,
    RequestContractError,
    ResourceNotFoundError,
    TraceContext,
    UnexpectedFailureError,
)
from app.platform.web.problems import build_problem_response

ALLOW_HEADER = "Allow"
_WHOLE_REQUEST = "request"


@dataclass(slots=True)
class _ResponseProgress:
    has_started: bool = False


class MethodNotAllowedError(InvalidRequestError):
    """The path exists, but the contract defines no operation for this method."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The contract defines no operation for this method on this path.")


def install_exception_handling(
    app: FastAPI, events: EventRecorder, trace_context: TraceContext
) -> None:
    """Register the exception handler and the middleware that catches unexpected errors.

    Args:
        app: The application.
        events: Where handled failures and refusals are logged once.
        trace_context: The trace of the request, for the `trace_id` of every body (LOG-04).
    """
    handler = _ProblemHandler(events, trace_context)
    app.add_exception_handler(AiServiceError, handler.handle_service_error)
    app.add_exception_handler(RequestValidationError, handler.handle_validation_error)
    app.add_exception_handler(HTTPException, handler.handle_http_exception)
    app.add_middleware(UnhandledErrorMiddleware, handler=handler)


def locations_of(
    errors: Iterable[Mapping[str, object]], *, prefix: tuple[str, ...] = ()
) -> tuple[str, ...]:
    """Return the locations of validation errors, such as `body.message`, without repeats.

    Args:
        errors: The errors of Pydantic or FastAPI, each with a `loc` entry.
        prefix: Parts placed before each location, such as `("body",)`.

    Returns:
        The locations, in the order of the errors.
    """
    locations: list[str] = []
    for error in errors:
        location = error.get("loc", ())
        # Validation errors hold their location as a tuple of names and indexes.
        parts = cast("tuple[object, ...]", location) if isinstance(location, tuple) else ()
        locations.append(".".join(prefix + tuple(str(part) for part in parts)) or _WHOLE_REQUEST)
    return tuple(dict.fromkeys(locations))


class UnhandledErrorMiddleware:
    """Turn every exception that no handler took into a `500 internal-error` body."""

    def __init__(self, app: ASGIApp, handler: _ProblemHandler) -> None:
        """Wrap the application.

        Args:
            app: The inner application.
            handler: The problem handler of `install_exception_handling`.
        """
        self._app = app
        self._handler = handler

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run the request and answer `500` if it raises before a response started.

        Args:
            scope: The ASGI scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        progress = _ResponseProgress()

        async def send_and_track(message: Message) -> None:
            if message["type"] == "http.response.start":
                progress.has_started = True
            await send(message)

        try:
            await self._app(scope, receive, send_and_track)
        # The one catch-all of the interface layer (PY-21, CODE-40): it logs once and converts.
        except Exception as error:
            failure = UnexpectedFailureError()
            failure.__cause__ = error
            response = self._handler.respond(failure)
            if not progress.has_started:
                await response(scope, receive, send)


class _ProblemHandler:
    def __init__(self, events: EventRecorder, trace_context: TraceContext) -> None:
        self._events = events
        self._trace_context = trace_context

    def respond(self, error: AiServiceError) -> Response:
        self._record(error)
        return build_problem_response(error, self._trace_context.current_trace_id())

    async def handle_service_error(self, _request: Request, error: Exception) -> Response:
        if not isinstance(error, AiServiceError):
            return self.respond(UnexpectedFailureError())
        return self.respond(error)

    async def handle_validation_error(self, _request: Request, error: Exception) -> Response:
        if not isinstance(error, RequestValidationError):
            return self.respond(UnexpectedFailureError())
        return self.respond(RequestContractError(locations_of(error.errors())))

    async def handle_http_exception(self, request: Request, error: Exception) -> Response:
        if isinstance(error, HTTPException) and error.status_code == HTTPStatus.METHOD_NOT_ALLOWED:
            return build_problem_response(
                MethodNotAllowedError(),
                self._trace_context.current_trace_id(),
                status=HTTPStatus.METHOD_NOT_ALLOWED,
                headers={ALLOW_HEADER: _allowed_methods(request)},
            )
        return self.respond(ResourceNotFoundError())

    def _record(self, error: AiServiceError) -> None:
        # One log line per refusal or failure (ERR-05). An invalid request or an unknown path
        # is the caller's error and is logged by backend, which receives the 4xx.
        match error.code:
            case ErrorCode.INTERNAL_ERROR:
                cause = error if error.__cause__ is None else error.__cause__
                self._events.record(EventName.REQUEST_FAILED, error_type=type(cause).__name__)
            case ErrorCode.NOT_READY:
                self._events.record(EventName.REQUEST_REFUSED, error_type=type(error).__name__)
            case ErrorCode.UNAUTHENTICATED:
                self._events.record(EventName.SERVICE_TOKEN_REJECTED)
            case ErrorCode.INVALID_REQUEST | ErrorCode.NOT_FOUND:
                return
            case _:
                assert_never(error.code)


def _allowed_methods(request: Request) -> str:
    # Starlette names only the first route of a path, and a path can have one route per method,
    # while `Allow` must list every method of the resource (RFC 9110, section 15.5.6).
    methods = {
        method
        for route in iter_route_contexts(request.app.routes)
        if route.matches(request.scope)[0] is not Match.NONE
        for method in route.methods or ()
    }
    return ", ".join(sorted(methods))

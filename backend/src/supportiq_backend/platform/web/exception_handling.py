"""The single exception handler of backend (PY-38, ERR-03).

Every error that leaves a request becomes a Problem Details body here and nowhere else:
domain errors, framework validation errors, unknown routes, and unexpected exceptions. An
error is logged once, here, where it is handled (ERR-05): unexpected failures as
`request.failed` and database failures as `database.call_failed`. Bodies never carry a stack
trace, an internal name, or a value that was sent (CON-12).
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import assert_never

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import iter_route_contexts
from starlette.exceptions import HTTPException
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from supportiq_backend.platform import (
    BackendError,
    ErrorCode,
    EventName,
    EventRecorder,
    InvalidRequestError,
    RequestContractError,
    ResourceNotFoundError,
    TraceContext,
    UnexpectedFailureError,
)
from supportiq_backend.platform.web.problems import build_problem_response
from supportiq_backend.platform.web.requests import locations_of

ALLOW_HEADER = "Allow"


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
        events: Where handled failures are logged once.
        trace_context: The trace of the request, for the `trace_id` of every body (LOG-04).
    """
    handler = _ProblemHandler(events, trace_context)
    app.add_exception_handler(BackendError, handler.handle_backend_error)
    app.add_exception_handler(RequestValidationError, handler.handle_validation_error)
    app.add_exception_handler(HTTPException, handler.handle_http_exception)
    app.add_middleware(UnhandledErrorMiddleware, handler=handler)


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

    def respond(self, error: BackendError) -> Response:
        self._record_failure(error)
        return build_problem_response(error, self._trace_context.current_trace_id())

    async def handle_backend_error(self, _request: Request, error: Exception) -> Response:
        if not isinstance(error, BackendError):
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

    def _record_failure(self, error: BackendError) -> None:
        # One log line and the span of the request (ERR-05, LOG-22). A refusal is no failure.
        cause = _cause_of(error)
        match error.code:
            case ErrorCode.NOT_READY:
                event = EventName.DATABASE_CALL_FAILED
                error_type = type(error).__name__
            case ErrorCode.INTERNAL_ERROR:
                event = EventName.REQUEST_FAILED
                error_type = type(cause).__name__
            case (
                ErrorCode.INVALID_REQUEST
                | ErrorCode.UNAUTHENTICATED
                | ErrorCode.FORBIDDEN
                | ErrorCode.NOT_FOUND
                | ErrorCode.IDEMPOTENCY_KEY_REUSED
                | ErrorCode.LOGIN_NAME_TAKEN
            ):
                return
            case _:
                assert_never(error.code)
        self._events.record(event, error_type=error_type)
        self._trace_context.record_failure(cause)


def _cause_of(error: BackendError) -> BaseException:
    return error if error.__cause__ is None else error.__cause__


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

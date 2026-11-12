"""Problem Details bodies: the one mapping from error codes to HTTP responses (ERR-03, CON-12)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from types import MappingProxyType

from fastapi import Response

from supportiq_backend.generated import ProblemDetails, Type
from supportiq_backend.platform import BackendError, ErrorCode, TraceId

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:supportiq:problem:"


@dataclass(frozen=True, slots=True)
class ProblemDescription:
    """The HTTP status and the fixed title of one problem type.

    Attributes:
        status: The HTTP status of the response.
        title: The title, the same for every occurrence of the type.
    """

    status: HTTPStatus
    title: str


PROBLEM_DESCRIPTIONS: Mapping[ErrorCode, ProblemDescription] = MappingProxyType(
    {
        ErrorCode.INVALID_REQUEST: ProblemDescription(
            HTTPStatus.UNPROCESSABLE_CONTENT, "Invalid request"
        ),
        ErrorCode.UNAUTHENTICATED: ProblemDescription(HTTPStatus.UNAUTHORIZED, "Not authenticated"),
        ErrorCode.FORBIDDEN: ProblemDescription(HTTPStatus.FORBIDDEN, "Forbidden"),
        ErrorCode.NOT_FOUND: ProblemDescription(HTTPStatus.NOT_FOUND, "Not found"),
        ErrorCode.IDEMPOTENCY_KEY_REUSED: ProblemDescription(
            HTTPStatus.CONFLICT, "Idempotency key reused"
        ),
        ErrorCode.LOGIN_NAME_TAKEN: ProblemDescription(HTTPStatus.CONFLICT, "Login name taken"),
        ErrorCode.NOT_READY: ProblemDescription(HTTPStatus.SERVICE_UNAVAILABLE, "Not ready"),
        ErrorCode.INTERNAL_ERROR: ProblemDescription(
            HTTPStatus.INTERNAL_SERVER_ERROR, "Internal error"
        ),
    }
)


def build_problem_response(
    error: BackendError,
    trace_id: TraceId,
    *,
    status: HTTPStatus | None = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """Build the Problem Details response of an error, with the trace ID of the request.

    Args:
        error: The error to describe.
        trace_id: The trace ID of the request (LOG-04).
        status: A status that replaces the one of the error's code. Only the framework's
            `405 Method Not Allowed` uses it, for a method that the contract does not define.
        headers: Headers of the response, such as `Allow` with a `405`.

    Returns:
        The response with the media type `application/problem+json`.
    """
    description = PROBLEM_DESCRIPTIONS[error.code]
    response_status = description.status if status is None else status
    problem = ProblemDetails(
        type=Type(PROBLEM_TYPE_PREFIX + error.code.value),
        title=description.title,
        status=response_status.value,
        detail=error.detail,
        trace_id=trace_id,
    )
    body = problem.model_dump(mode="json") | dict(error.problem_extensions())
    return Response(
        content=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        status_code=response_status.value,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=None if headers is None else dict(headers),
    )

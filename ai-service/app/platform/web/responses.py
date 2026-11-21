"""Writing responses: JSON bodies, timestamps, and dependency providers (PY-35, PY-37)."""

from collections.abc import Callable
from datetime import datetime, timedelta
from http import HTTPStatus

from fastapi import Response
from pydantic import BaseModel

from app.platform import UnexpectedFailureError

JSON_MEDIA_TYPE = "application/json"
UTC_OFFSET = timedelta(0)
_UTC_DESIGNATOR = "Z"


class NonUtcTimestampError(UnexpectedFailureError):
    """A timestamp reached a response without being in UTC: a defect (PY-26)."""


def render_json(model: BaseModel) -> str:
    """Render a generated contract model as the JSON text of a response body.

    Optional fields that are absent stay absent: the contract never uses `null` (CON-08).

    Args:
        model: The generated response model.

    Returns:
        The JSON text.
    """
    return model.model_dump_json(exclude_none=True, by_alias=True)


def json_response(model: BaseModel, *, status: HTTPStatus = HTTPStatus.OK) -> Response:
    """Build the response of a generated contract model.

    Args:
        model: The generated response model.
        status: The HTTP status.

    Returns:
        The response with the media type `application/json`.
    """
    return Response(
        content=render_json(model), status_code=status.value, media_type=JSON_MEDIA_TYPE
    )


def format_timestamp(moment: datetime) -> str:
    """Write a time as the contract's `Timestamp`: RFC 3339 in UTC with `Z` (CON-17).

    Args:
        moment: A timezone-aware time in UTC.

    Returns:
        The time with seconds, and microseconds only when they are not zero.

    Raises:
        NonUtcTimestampError: The time is naive or not in UTC.
    """
    if moment.utcoffset() != UTC_OFFSET:
        raise NonUtcTimestampError
    timespec = "microseconds" if moment.microsecond else "seconds"
    return moment.replace(tzinfo=None).isoformat(timespec=timespec) + _UTC_DESIGNATOR


def provide[ValueT](value: ValueT) -> Callable[[], ValueT]:
    """Return a FastAPI dependency that provides a value of the composition root (PY-37).

    Args:
        value: A use case or another dependency created once at startup.

    Returns:
        The dependency function, for `Depends`.
    """

    def provider() -> ValueT:
        return value

    return provider

"""Writing responses: JSON bodies, timestamps, and dependency providers (PY-35, PY-37)."""

from collections.abc import Callable
from datetime import datetime
from http import HTTPStatus

from fastapi import Response
from pydantic import MISSING, BaseModel

from supportiq_backend.platform import NonUtcTimestampError, format_timestamp

JSON_MEDIA_TYPE = "application/json"

__all__ = [
    "JSON_MEDIA_TYPE",
    "NonUtcTimestampError",
    "format_optional_timestamp",
    "format_timestamp",
    "json_response",
    "provide",
    "render_json",
    "stored_json_response",
]


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


def stored_json_response(status_code: int, body: str) -> Response:
    """Build the response of an idempotent write from its stored text, byte for byte (ERR-15).

    Args:
        status_code: The HTTP status of the first response.
        body: The exact JSON text of the first response.

    Returns:
        The response with the media type `application/json`.
    """
    return Response(content=body, status_code=status_code, media_type=JSON_MEDIA_TYPE)


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


def format_optional_timestamp(moment: datetime | None) -> str | MISSING:
    """Write an optional time as the contract's `Timestamp`, absent when there is none (CON-08).

    Args:
        moment: A timezone-aware time in UTC, or None.

    Returns:
        The time as `format_timestamp` writes it, or `MISSING`, so the field stays absent.
    """
    return MISSING if moment is None else format_timestamp(moment)

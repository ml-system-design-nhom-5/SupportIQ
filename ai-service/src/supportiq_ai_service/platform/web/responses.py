"""Writing responses: JSON bodies and dependency providers (PY-35, PY-37)."""

from collections.abc import Callable
from http import HTTPStatus

from fastapi import Response
from pydantic import BaseModel

JSON_MEDIA_TYPE = "application/json"


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

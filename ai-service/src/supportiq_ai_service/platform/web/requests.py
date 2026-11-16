"""Reading request input: strict JSON bodies and contract timestamps.

Bodies are parsed in strict mode, so a value of the wrong JSON type is rejected instead of
coerced (SEC-21: invalid input is rejected, never repaired), and unknown fields are rejected
by the generated models (CON-07). A validation error names only the location, never the
value that was sent. This module follows the request reading of backend.

A number with a zero fraction, such as `7.0` or `1e3`, is read as the integer it is. JSON
Schema counts it as an integer, so this counts integers as the contract does and repairs no
value; strict mode alone would refuse it for an integer field.
"""

from datetime import UTC, datetime
from typing import cast

from fastapi import Request
from pydantic import BaseModel, ValidationError
from pydantic_core import from_json, to_json

from supportiq_ai_service.platform import TIMESTAMP_PATTERN, RequestContractError
from supportiq_ai_service.platform.web.exception_handling import locations_of

_BODY_LOCATION = ("body",)


async def parse_json_body[ModelT: BaseModel](request: Request, model: type[ModelT]) -> ModelT:
    """Parse the request body into a generated contract model, strictly.

    Args:
        request: The request.
        model: The generated request model.

    Returns:
        The parsed body.

    Raises:
        RequestContractError: The body is not valid JSON or does not match the contract.
    """
    body = await request.body()
    try:
        return model.model_validate_json(_with_integral_numbers_as_integers(body), strict=True)
    except ValidationError as error:
        locations = locations_of(error.errors(include_input=False), prefix=_BODY_LOCATION)
        raise RequestContractError(locations) from error


def parse_timestamp(text: str, location: str) -> datetime:
    """Read a contract `Timestamp`: RFC 3339 in UTC with `Z`.

    A time without a time zone, or with an offset other than `Z`, is rejected, never completed
    (contracts v1 design, Work for the join). The generated models hold timestamps as text,
    because Pydantic cannot apply a pattern to a datetime, so every timestamp of a request is
    read here.

    Args:
        text: The timestamp as the request holds it.
        location: Where it is, such as `body.as_of`, for the error.

    Returns:
        The time, timezone-aware in UTC.

    Raises:
        RequestContractError: The text is not a contract `Timestamp`.
    """
    if not TIMESTAMP_PATTERN.fullmatch(text):
        raise RequestContractError((location,))
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise RequestContractError((location,)) from error
    return moment.astimezone(UTC)


def _with_integral_numbers_as_integers(body: bytes) -> bytes:
    # Malformed JSON stays as it was sent, so the model reports it as `json_invalid`.
    try:
        value: object = from_json(body, allow_inf_nan=False)
    except ValueError:
        return body
    return to_json(_integral_numbers_as_integers(value))


def _integral_numbers_as_integers(value: object) -> object:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        members = cast("dict[str, object]", value)
        return {name: _integral_numbers_as_integers(member) for name, member in members.items()}
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [_integral_numbers_as_integers(item) for item in items]
    return value

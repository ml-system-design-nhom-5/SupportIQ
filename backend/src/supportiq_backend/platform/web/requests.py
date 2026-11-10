"""Reading request input: strict JSON bodies and the locations of validation errors.

Bodies are parsed in strict mode, so a value of the wrong JSON type is rejected instead of
coerced (SEC-21: invalid input is rejected, never repaired), and unknown fields are rejected
by the generated models (CON-07). A validation error names only the location, never the
value that was sent.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import cast

from fastapi import Request
from pydantic import BaseModel, ValidationError

from supportiq_backend.platform import RequestContractError

IDEMPOTENCY_KEY_HEADER = "idempotency-key"
_BODY_LOCATION = ("body",)
_WHOLE_REQUEST = "request"

# A FastAPI dependency that the composition root builds and passes to a router, such as the
# session of a request, which `accounts` owns.
type RequestDependency[ValueT] = Callable[[Request], Awaitable[ValueT]]


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
        return model.model_validate_json(body, strict=True)
    except ValidationError as error:
        locations = locations_of(error.errors(include_input=False), prefix=_BODY_LOCATION)
        raise RequestContractError(locations) from error

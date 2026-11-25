"""The operations of the contract, read from the schema with plain types (CON-27)."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
import schemathesis
from schemathesis import BaseSchema

CONTRACT_FILE = Path(__file__).parents[3] / "contracts" / "ai-service.openapi.yaml"


@dataclass(frozen=True, slots=True)
class DocumentedOperation:
    """One operation as the contract documents it.

    Attributes:
        operation_id: The `operationId`.
        method: The HTTP method, in capitals.
        path: The path template.
        statuses: The documented statuses.
        needs_service_token: Whether the operation names the `serviceToken` scheme.
    """

    operation_id: str
    method: str
    path: str
    statuses: frozenset[int]
    needs_service_token: bool


def load_contract() -> BaseSchema:
    """Load `contracts/ai-service.openapi.yaml` with its relative references.

    Returns:
        The contract.
    """
    return schemathesis.openapi.from_path(CONTRACT_FILE)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves PathLike unparametrized, as in backend (#3)


def list_operations(contract: BaseSchema) -> tuple[DocumentedOperation, ...]:
    """List the operations of the contract.

    Args:
        contract: The contract.

    Returns:
        The operations, in the order of the file.
    """
    # The file that Redocly validates in `contracts/`, so its shape is known at this boundary.
    paths = cast("Mapping[str, Mapping[str, Mapping[str, object]]]", contract.raw_schema["paths"])
    return tuple(
        DocumentedOperation(
            operation_id=str(operation["operationId"]),
            method=method.upper(),
            path=path,
            statuses=frozenset(int(status) for status in _texts(operation["responses"])),
            needs_service_token=bool(operation.get("security", ())),
        )
        for path, path_item in paths.items()
        for method, operation in path_item.items()
    )


def _texts(values: object) -> Iterable[str]:
    # Status codes are the keys of a mapping: they iterate as text.
    return cast("Iterable[str]", values)


def validate_response(contract: BaseSchema, operation_id: str, response: httpx.Response) -> None:
    """Check a response against the contract: status, media type, and schema.

    Args:
        contract: The contract.
        operation_id: The operation that answered.
        response: The response.

    Raises:
        FailureGroup: The response does not conform.
    """
    operation = contract.find_operation_by_id(operation_id)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]  # the method belongs to the OpenAPI schema class, and Schemathesis leaves `APIOperation` unparametrized, as in backend (#3)
    operation.validate_response(response)  # pyright: ignore[reportUnknownMemberType]  # Schemathesis leaves `APIOperation` unparametrized, as in backend (#3)

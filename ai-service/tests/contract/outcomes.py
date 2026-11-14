"""The table of documented outcomes: one row for each status of each operation (CON-27).

Each row names the state of the replica and the change that turns the valid call of its
operation into the request that gets this status.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from http import HTTPStatus
from types import MappingProxyType

VALID_SUGGESTION = {
    "message": "Where is my refund for [ORDER_ID_1]?",
    "as_of": "2026-11-05T09:30:00Z",
}
KB_DOCUMENTS = "/v1/kb-documents"


class Condition(StrEnum):
    """The state of the replica that answers."""

    HEALTHY = "healthy"
    REQUEST_FAILS = "request-fails"
    NO_RELEASE = "no-release"


@dataclass(frozen=True, slots=True)
class Call:
    """One request.

    Attributes:
        method: The HTTP method.
        path: The path.
        body: The JSON body; None when the request has none.
        has_service_token: Whether the request carries the service token.
    """

    method: str
    path: str
    body: Mapping[str, object] | None = None
    has_service_token: bool = True


VALID_CALLS: Mapping[str, Call] = MappingProxyType(
    {
        "createAnalysis": Call("POST", "/v1/analyses", VALID_SUGGESTION),
        "createDraft": Call("POST", "/v1/drafts", VALID_SUGGESTION),
        "getKbDocumentVersion": Call("GET", f"{KB_DOCUMENTS}/SAMPLE-REFUND-001/versions/1.0"),
        "getAssetVersions": Call("GET", "/v1/asset-versions"),
        "checkLiveness": Call("GET", "/health/live", has_service_token=False),
        "checkReadiness": Call("GET", "/health/ready", has_service_token=False),
    }
)


def unchanged(call: Call) -> Call:
    return call


def without_service_token(call: Call) -> Call:
    return replace(call, has_service_token=False)


def without_message(call: Call) -> Call:
    return replace(call, body={"as_of": VALID_SUGGESTION["as_of"]})


def with_unknown_version(call: Call) -> Call:
    return replace(call, path=f"{KB_DOCUMENTS}/SAMPLE-REFUND-001/versions/0.9")


def with_invalid_document_id(call: Call) -> Call:
    return replace(call, path=f"{KB_DOCUMENTS}/-starts-with-a-dash/versions/1.0")


@dataclass(frozen=True, slots=True)
class Outcome:
    """One documented status of one operation.

    Attributes:
        operation_id: The operation.
        status: The status.
        condition: The state of the replica.
        change: Turns the valid call into the one that gets this status.
    """

    operation_id: str
    status: HTTPStatus
    condition: Condition = Condition.HEALTHY
    change: Callable[[Call], Call] = unchanged

    def __str__(self) -> str:
        """Name the test after the operation and the status."""
        return f"{self.operation_id}-{self.status.value}"


def _suggestion_outcomes(operation_id: str) -> tuple[Outcome, ...]:
    return (
        Outcome(operation_id, HTTPStatus.OK),
        Outcome(operation_id, HTTPStatus.UNAUTHORIZED, change=without_service_token),
        Outcome(operation_id, HTTPStatus.UNPROCESSABLE_CONTENT, change=without_message),
        Outcome(operation_id, HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS),
        Outcome(operation_id, HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_RELEASE),
    )


OUTCOMES = (
    *_suggestion_outcomes("createAnalysis"),
    *_suggestion_outcomes("createDraft"),
    Outcome("getKbDocumentVersion", HTTPStatus.OK),
    Outcome("getKbDocumentVersion", HTTPStatus.UNAUTHORIZED, change=without_service_token),
    Outcome("getKbDocumentVersion", HTTPStatus.NOT_FOUND, change=with_unknown_version),
    Outcome(
        "getKbDocumentVersion", HTTPStatus.UNPROCESSABLE_CONTENT, change=with_invalid_document_id
    ),
    Outcome("getKbDocumentVersion", HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS),
    Outcome("getKbDocumentVersion", HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_RELEASE),
    Outcome("getAssetVersions", HTTPStatus.OK),
    Outcome("getAssetVersions", HTTPStatus.UNAUTHORIZED, change=without_service_token),
    Outcome("getAssetVersions", HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS),
    Outcome("getAssetVersions", HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_RELEASE),
    Outcome("checkLiveness", HTTPStatus.NO_CONTENT),
    Outcome("checkLiveness", HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS),
    Outcome("checkReadiness", HTTPStatus.NO_CONTENT),
    Outcome("checkReadiness", HTTPStatus.INTERNAL_SERVER_ERROR, Condition.REQUEST_FAILS),
    Outcome("checkReadiness", HTTPStatus.SERVICE_UNAVAILABLE, Condition.NO_RELEASE),
)

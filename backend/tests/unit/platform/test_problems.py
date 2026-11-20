"""Tests of the Problem Details mapping: one status and title per error code (ERR-03, CON-12)."""

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import ClassVar

import pytest

from app.platform import (
    BackendError,
    DatabaseUnavailableError,
    ErrorCode,
    ResourceNotFoundError,
    TraceId,
)
from app.platform.web import PROBLEM_MEDIA_TYPE, build_problem_response
from app.platform.web.problems import PROBLEM_DESCRIPTIONS

TRACE_ID = TraceId("4bf92f3577b34da6a3ce929d0e0e4736")


class RefusedWithRuleError(BackendError):
    """An error with an extension member, as an admin refusal has `violated_rule`."""

    code: ClassVar[ErrorCode] = ErrorCode.INVALID_REQUEST

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The change is refused.")

    def problem_extensions(self) -> Mapping[str, str]:
        """Return the extension member of the refusal."""
        return {"violated_rule": "own_account"}


def test_every_error_code_has_a_problem_description() -> None:
    described = set(PROBLEM_DESCRIPTIONS)

    assert described == set(ErrorCode)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ErrorCode.INVALID_REQUEST, HTTPStatus.UNPROCESSABLE_CONTENT),
        (ErrorCode.UNAUTHENTICATED, HTTPStatus.UNAUTHORIZED),
        (ErrorCode.FORBIDDEN, HTTPStatus.FORBIDDEN),
        (ErrorCode.NOT_FOUND, HTTPStatus.NOT_FOUND),
        (ErrorCode.IDEMPOTENCY_KEY_REUSED, HTTPStatus.CONFLICT),
        (ErrorCode.LOGIN_NAME_TAKEN, HTTPStatus.CONFLICT),
        (ErrorCode.NOT_READY, HTTPStatus.SERVICE_UNAVAILABLE),
        (ErrorCode.INTERNAL_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_error_code_maps_to_the_status_of_the_contract(code: ErrorCode, status: HTTPStatus) -> None:
    description = PROBLEM_DESCRIPTIONS[code]

    assert description.status == status


def test_problem_response_holds_every_required_member() -> None:
    response = build_problem_response(DatabaseUnavailableError(), TRACE_ID)

    body = json.loads(bytes(response.body))

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.media_type == PROBLEM_MEDIA_TYPE
    assert body == {
        "type": "urn:supportiq:problem:not-ready",
        "title": "Not ready",
        "status": 503,
        "detail": "The database is not available.",
        "trace_id": TRACE_ID,
    }


def test_problem_response_adds_the_extension_members_of_the_error() -> None:
    response = build_problem_response(RefusedWithRuleError(), TRACE_ID)

    body = json.loads(bytes(response.body))

    assert body["violated_rule"] == "own_account"
    assert body["status"] == HTTPStatus.UNPROCESSABLE_CONTENT


def test_problem_response_can_replace_the_status_and_add_headers() -> None:
    response = build_problem_response(
        ResourceNotFoundError(),
        TRACE_ID,
        status=HTTPStatus.METHOD_NOT_ALLOWED,
        headers={"Allow": "GET"},
    )

    body = json.loads(bytes(response.body))

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert body["status"] == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["allow"] == "GET"

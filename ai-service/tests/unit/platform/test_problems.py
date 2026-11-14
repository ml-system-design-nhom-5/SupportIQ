"""Each error code becomes one Problem Details body of the contract (CON-12, ERR-03)."""

import json
from http import HTTPStatus

import pytest

from supportiq_ai_service.platform import (
    AiServiceError,
    RequestContractError,
    ResourceNotFoundError,
    ServiceTokenRejectedError,
    UnexpectedFailureError,
)
from supportiq_ai_service.platform.web import PROBLEM_MEDIA_TYPE, build_problem_response
from supportiq_ai_service.release import ReleaseNotLoadedError
from tests.unit.platform.fakes import FAKE_TRACE_ID


@pytest.mark.parametrize(
    ("error", "status", "problem_type", "title", "detail"),
    [
        (
            RequestContractError(("body.message",)),
            HTTPStatus.UNPROCESSABLE_CONTENT,
            "invalid-request",
            "Invalid request",
            "The request does not match the contract at: body.message.",
        ),
        (
            ServiceTokenRejectedError(),
            HTTPStatus.UNAUTHORIZED,
            "unauthenticated",
            "Not authenticated",
            "The request has no valid service token.",
        ),
        (
            ResourceNotFoundError(),
            HTTPStatus.NOT_FOUND,
            "not-found",
            "Not found",
            "The resource was not found.",
        ),
        (
            ReleaseNotLoadedError(),
            HTTPStatus.SERVICE_UNAVAILABLE,
            "not-ready",
            "Not ready",
            "The release manifest is not loaded.",
        ),
        (
            UnexpectedFailureError(),
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "internal-error",
            "Internal error",
            "An unexpected error occurred.",
        ),
    ],
)
def test_an_error_becomes_its_problem_details_body(
    error: AiServiceError, status: HTTPStatus, problem_type: str, title: str, detail: str
) -> None:
    response = build_problem_response(error, FAKE_TRACE_ID)

    assert response.status_code == status
    assert response.media_type == PROBLEM_MEDIA_TYPE
    assert json.loads(bytes(response.body)) == {
        "type": f"urn:supportiq:problem:{problem_type}",
        "title": title,
        "status": status.value,
        "detail": detail,
        "trace_id": FAKE_TRACE_ID,
    }


def test_a_replaced_status_keeps_the_problem_type_and_adds_the_headers() -> None:
    response = build_problem_response(
        RequestContractError(("request",)),
        FAKE_TRACE_ID,
        status=HTTPStatus.METHOD_NOT_ALLOWED,
        headers={"Allow": "GET"},
    )

    assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
    assert response.headers["Allow"] == "GET"
    assert json.loads(bytes(response.body))["status"] == HTTPStatus.METHOD_NOT_ALLOWED.value

"""The service token guard admits only `Authorization: Bearer <service token>` (ADR-0018)."""

import pytest
from fastapi import Request

from supportiq_ai_service.platform import ServiceTokenRejectedError
from supportiq_ai_service.platform.web import build_service_token_guard

SERVICE_TOKEN = "service-token-for-unit-tests"


def request_with(headers: dict[str, str]) -> Request:
    raw_headers = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_the_service_token_is_admitted_with_any_case_of_the_scheme(scheme: str) -> None:
    guard = build_service_token_guard(SERVICE_TOKEN)

    guard(request_with({"Authorization": f"{scheme} {SERVICE_TOKEN}"}))


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": f"Basic {SERVICE_TOKEN}"},
        {"Authorization": f"Bearer {SERVICE_TOKEN}x"},
        {"Authorization": f"Bearer  {SERVICE_TOKEN}"},
        {"Authorization": "Bearer another-token"},
    ],
)
def test_a_missing_or_wrong_token_is_rejected(headers: dict[str, str]) -> None:
    guard = build_service_token_guard(SERVICE_TOKEN)

    with pytest.raises(ServiceTokenRejectedError) as raised:
        guard(request_with(headers))

    assert SERVICE_TOKEN not in raised.value.detail

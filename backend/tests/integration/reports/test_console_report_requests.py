"""`getConsoleReport` over HTTP: managers only, a valid period, and the empty-period example."""

import json
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import pytest

from app.platform import EventName
from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.reports.report_rows import CONSOLE_REPORTS, END_TEXT, PERIOD, START_TEXT

pytestmark = pytest.mark.anyio

EXAMPLES = Path(__file__).parents[4] / "contracts/examples/getConsoleReport"
FORBIDDEN = "urn:supportiq:problem:forbidden"
UNAUTHENTICATED = "urn:supportiq:problem:unauthenticated"
INVALID_REQUEST = "urn:supportiq:problem:invalid-request"
EMPTY_PERIOD = {"start_at": "2026-12-01T00:00:00Z", "end_at": "2026-12-08T00:00:00Z"}
WITHOUT_DURATION = {"start_at": START_TEXT, "end_at": START_TEXT}


async def internal_account(builder: DatabaseBuilder, role: str) -> UUID:
    return await builder.account(AccountSpec(role))


async def customer_account(builder: DatabaseBuilder, _role: str) -> UUID:
    account_id, _customer_id = await builder.customer_account()
    return account_id


REFUSED_ROLES = [
    ("staff", internal_account),
    ("admin", internal_account),
    ("customer", customer_account),
]


def without_trace_id(body: dict[str, object]) -> dict[str, object]:
    return {name: value for name, value in body.items() if name != "trace_id"}


async def test_report_of_an_empty_period_is_the_contract_example(
    backend: RunningBackend, manager_headers: dict[str, str]
) -> None:
    example = json.loads((EXAMPLES / "empty-period.json").read_text(encoding="utf-8"))

    response = await backend.client.get(
        CONSOLE_REPORTS, params=EMPTY_PERIOD, headers=manager_headers
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json() == example["value"]


async def test_report_is_recorded_as_built_for_the_manager(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    account_id = await builder.account(AccountSpec("manager"))
    headers = session_headers(await builder.session(account_id, "manager"))

    await backend.client.get(CONSOLE_REPORTS, params=PERIOD, headers=headers)

    (built,) = backend.events.of(EventName.REPORT_BUILT)
    assert built.attributes == {"account_id": str(account_id)}


@pytest.mark.parametrize(
    ("role", "create_account"), REFUSED_ROLES, ids=["staff", "admin", "customer"]
)
async def test_report_refuses_every_role_but_manager_before_reading_the_period(
    backend: RunningBackend,
    builder: DatabaseBuilder,
    role: str,
    create_account: Callable[[DatabaseBuilder, str], Awaitable[UUID]],
) -> None:
    account_id = await create_account(builder, role)
    headers = session_headers(await builder.session(account_id, role))

    response = await backend.client.get(CONSOLE_REPORTS, params=WITHOUT_DURATION, headers=headers)

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["type"] == FORBIDDEN


async def test_report_without_a_session_returns_401(backend: RunningBackend) -> None:
    response = await backend.client.get(CONSOLE_REPORTS, params=PERIOD)

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert response.json()["type"] == UNAUTHENTICATED


async def test_report_of_a_period_without_duration_returns_the_invalid_period_example(
    backend: RunningBackend, manager_headers: dict[str, str]
) -> None:
    example = json.loads((EXAMPLES.parent / "problems/invalid-period.json").read_text("utf-8"))

    response = await backend.client.get(
        CONSOLE_REPORTS, params=WITHOUT_DURATION, headers=manager_headers
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert without_trace_id(response.json()) == without_trace_id(example["value"])


@pytest.mark.parametrize(
    ("params", "detail"),
    [
        ({"end_at": END_TEXT}, "The parameter start_at is not valid."),
        ({"start_at": START_TEXT}, "The parameter end_at is not valid."),
        (
            {"start_at": "2026-11-02T00:00:00+07:00", "end_at": END_TEXT},
            "The parameter start_at is not valid.",
        ),
        ({"start_at": START_TEXT, "end_at": "2026-11-09"}, "The parameter end_at is not valid."),
    ],
    ids=["no-start", "no-end", "start-with-offset", "end-without-time"],
)
async def test_report_with_a_missing_or_malformed_time_returns_422_naming_it(
    backend: RunningBackend,
    manager_headers: dict[str, str],
    params: dict[str, str],
    detail: str,
) -> None:
    response = await backend.client.get(CONSOLE_REPORTS, params=params, headers=manager_headers)

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (response.json()["type"], response.json()["detail"]) == (INVALID_REQUEST, detail)

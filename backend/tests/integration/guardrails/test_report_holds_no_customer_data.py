"""Guardrail: the report of a period holds figures only, never what a ticket says (TEST-26).

A report is computed from backend's own records (FR-10), and the figures it returns are counts,
shares, codes, and times: Internal values only. Staff answer one ticket and escalate another
with a note, and the report of the period that holds them carries no customer, message, reply
body, note, or identifier of a ticket or an order (SEC-01, LOG-29).
"""

from http import HTTPStatus

import pytest

from tests.integration.application import RunningBackend, session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder, TicketSpec

pytestmark = pytest.mark.anyio

CONSOLE_TICKETS = "/v1/console/tickets"
CONSOLE_REPORTS = "/v1/console/reports"
KEY = "00000000-0000-4000-8000-000000000001"
CUSTOMER_NAME = "Report Guardrailcustomer"
MESSAGE = "My parcel to 7 Ly Thai To street never arrived."
REPLY_TEXT = "We have sent a new parcel to the same address."
NOTE = "The customer named the courier who left the parcel."
# A period that holds every time of the fake clock and of the builder.
PERIOD = {"start_at": "2020-01-01T00:00:00Z", "end_at": "2100-01-01T00:00:00Z"}


async def test_the_report_of_a_period_with_activity_holds_figures_only(
    backend: RunningBackend, builder: DatabaseBuilder
) -> None:
    _, customer_id = await builder.customer_account(display_name=CUSTOMER_NAME)
    order_id = await builder.order_of_one_product(customer_id)
    answered = await builder.ticket(customer_id, order_id, TicketSpec(message=MESSAGE))
    escalated = await builder.ticket(customer_id, order_id, TicketSpec(message=MESSAGE))
    staff = session_headers(
        await builder.session(await builder.account(AccountSpec("staff")), "staff")
    )
    manager = session_headers(
        await builder.session(await builder.account(AccountSpec("manager")), "manager")
    )

    replied = await backend.client.post(
        f"{CONSOLE_TICKETS}/{answered}/replies",
        json={"basis": "no_ai_draft", "body": REPLY_TEXT},
        headers={**staff, "Idempotency-Key": KEY},
    )
    escalation = await backend.client.post(
        f"{CONSOLE_TICKETS}/{escalated}/escalations",
        json={"staff_reason_codes": ["other"], "note": NOTE},
        headers={**staff, "Idempotency-Key": KEY},
    )
    report = await backend.client.get(CONSOLE_REPORTS, params=PERIOD, headers=manager)

    seeded = (CUSTOMER_NAME, MESSAGE, REPLY_TEXT, NOTE, answered, escalated, order_id)
    assert (replied.status_code, escalation.status_code) == (HTTPStatus.CREATED, HTTPStatus.CREATED)
    assert report.status_code == HTTPStatus.OK
    assert [value for value in seeded if value in report.text] == []

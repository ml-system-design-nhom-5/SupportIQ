"""Guardrail: no password sent to backend is ever kept or shown (TEST-26, ADR-0015, ERR-15).

A known password goes through sign-in and through every operation that takes one, and none
appears in an idempotency record, a response body, a log line, an exported span, or an audit
log entry. The whole telemetry pipeline of a replica runs, as in the telemetry guardrail.
"""

import io

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from supportiq_backend.accounts import PasswordHash
from supportiq_backend.composition_root.cli import build_redactor
from supportiq_backend.platform.adapters.logging_setup import (
    StandardLibraryEventRecorder,
    configure_logging,
)
from tests.integration.accounts.admin_requests import KEY, OTHER_KEY
from tests.integration.accounts.password_requests import (
    NEW_ACCOUNT,
    OwnChange,
    Reset,
    change_own_password,
    create_account,
    reset_password,
    sign_in,
)
from tests.integration.application import build_settings, running_client
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.guardrails.exported_spans import spans_as_text
from tests.unit.accounts.fakes import KNOWN_PASSWORD
from tests.unit.platform.fakes import FakeClock

pytestmark = pytest.mark.anyio

ADMIN_LOGIN_NAME = "admin-passwords"
STAFF_LOGIN_NAME = "staff-passwords"
CREATED_PASSWORD = "created-account-guardrail-password"
RESET_PASSWORD = "reset-account-guardrail-password"
CHANGED_PASSWORD = "changed-own-guardrail-password"
WRONG_PASSWORD = "wrong-current-guardrail-password"
PASSWORDS = (KNOWN_PASSWORD, CREATED_PASSWORD, RESET_PASSWORD, CHANGED_PASSWORD, WRONG_PASSWORD)
SUCCESSFUL_WRITE_COUNT = 3
SESSION_COOKIE = "supportiq_session"


async def send_every_password(client: httpx.AsyncClient, staff_id: object) -> str:
    admin = await sign_in(client, ADMIN_LOGIN_NAME, KNOWN_PASSWORD)
    admin_token = admin.cookies[SESSION_COOKIE]
    created = await create_account(
        client, admin_token, {**NEW_ACCOUNT, "password": CREATED_PASSWORD}
    )
    reset = await reset_password(client, admin_token, staff_id, Reset(RESET_PASSWORD))
    staff = await sign_in(client, STAFF_LOGIN_NAME, RESET_PASSWORD)
    staff_token = staff.cookies[SESSION_COOKIE]
    refused = await change_own_password(
        client, staff_token, OwnChange(WRONG_PASSWORD, CHANGED_PASSWORD), key=KEY
    )
    changed = await change_own_password(
        client, staff_token, OwnChange(RESET_PASSWORD, CHANGED_PASSWORD), key=OTHER_KEY
    )
    responses = (admin, created, reset, staff, refused, changed)
    return " ".join(response.text for response in responses)


@pytest.mark.usefixtures("restored_root_logger")
async def test_no_password_reaches_a_record_a_response_a_log_line_or_a_span(
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    known_password_hash: PasswordHash,
    exported_spans: InMemorySpanExporter,
) -> None:
    await builder.account(
        AccountSpec("admin", login_name=ADMIN_LOGIN_NAME, password_hash=known_password_hash)
    )
    staff_id = await builder.account(AccountSpec("staff", login_name=STAFF_LOGIN_NAME))
    log_stream = io.StringIO()
    events = StandardLibraryEventRecorder(configure_logging(log_stream, build_redactor()))

    async with running_client(build_settings(worker_database), events, FakeClock()) as client:
        responses = await send_every_password(client, staff_id)

    logs = log_stream.getvalue()
    spans = spans_as_text(exported_spans)
    records = str(
        await builder.scalar("SELECT string_agg(response_body::text, ' ') FROM idempotency_records")
    )
    audit_entries = str(
        await builder.scalar("SELECT string_agg(data::text, ' ') FROM audit_log_entries")
    )
    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == SUCCESSFUL_WRITE_COUNT
    assert [password for password in PASSWORDS if password in records] == []
    assert [password for password in PASSWORDS if password in responses] == []
    assert [password for password in PASSWORDS if password in logs] == []
    assert [password for password in PASSWORDS if password in spans] == []
    assert [password for password in PASSWORDS if password in audit_entries] == []

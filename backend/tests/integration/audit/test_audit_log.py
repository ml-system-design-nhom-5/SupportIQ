"""Integration tests of `PostgresAuditLog`: entries live and die with their transaction."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
)
from app.audit.adapters.audit_log import PostgresAuditLog
from app.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_session_factory,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.unit.platform.fakes import FAKE_CLOCK_START, FAKE_TRACE_ID

pytestmark = pytest.mark.anyio

ENTRY_ID = AuditEntryId(UUID(int=7))
DATA = {"target_account_id": "x", "old_role": "staff", "new_role": "manager"}


def audit_runner(engine: AsyncEngine) -> SqlAlchemyTransactionRunner[PostgresAuditLog]:
    return SqlAlchemyTransactionRunner(create_session_factory(engine), build_audit_log)


def build_audit_log(session: AsyncSession) -> PostgresAuditLog:
    return PostgresAuditLog(session)


def build_entry(actor_account_id: ActorAccountId | None) -> AuditEntry:
    return AuditEntry(
        entry_id=ENTRY_ID,
        occurred_at=FAKE_CLOCK_START,
        event_type=AuditEventType.ACCOUNT_ROLE_CHANGED,
        actor_account_id=actor_account_id,
        ticket_id=None,
        trace_id=FAKE_TRACE_ID,
        data=DATA,
    )


async def test_committed_entry_is_stored_with_its_data(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    actor_id = await builder.account(AccountSpec("admin"))

    async with audit_runner(app_engine).begin() as transaction:
        await transaction.stores.append(build_entry(ActorAccountId(str(actor_id))))
        await transaction.commit()

    assert await builder.scalar("SELECT data FROM audit_log_entries") == DATA
    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") == actor_id
    assert await builder.scalar("SELECT trace_id FROM audit_log_entries") == FAKE_TRACE_ID


async def test_entry_of_a_system_event_has_no_actor(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    async with audit_runner(app_engine).begin() as transaction:
        await transaction.stores.append(build_entry(None))
        await transaction.commit()

    assert await builder.scalar("SELECT actor_account_id FROM audit_log_entries") is None


async def test_entry_of_a_rolled_back_change_is_not_stored(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    async with audit_runner(app_engine).begin() as transaction:
        await transaction.stores.append(build_entry(None))

    assert await builder.scalar("SELECT count(*) FROM audit_log_entries") == 0

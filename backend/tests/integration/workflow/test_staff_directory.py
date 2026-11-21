"""Adapter tests of `PostgresStaffDirectory` against PostgreSQL 17 (TEST-01).

The console names the staff and managers who acted on a ticket, and never a customer account
(ADR-0012, SEC-41). The display names are synthetic (TEST-18).
"""

from collections.abc import Mapping
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import AccountId, DisplayName
from app.accounts.adapters.staff_directory import PostgresStaffDirectory
from app.platform.adapters.database import create_session_factory
from tests.integration.builders import AccountSpec, DatabaseBuilder

pytestmark = pytest.mark.anyio

STAFF_NAME = DisplayName("Mai Nguyen")
MANAGER_NAME = DisplayName("Hung Le")
UNKNOWN_ACCOUNT_ID = AccountId("ffffffff-0000-4000-8000-000000000000")


async def load_display_names(
    engine: AsyncEngine, account_ids: frozenset[AccountId]
) -> Mapping[AccountId, DisplayName]:
    async with create_session_factory(engine)() as session:
        return await PostgresStaffDirectory(session).load_display_names(account_ids)


def to_account_id(account_id: UUID) -> AccountId:
    return AccountId(str(account_id))


async def test_load_display_names_returns_the_names_of_staff_and_managers(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    staff_id = to_account_id(await builder.account(AccountSpec("staff", display_name=STAFF_NAME)))
    manager_id = to_account_id(
        await builder.account(AccountSpec("manager", display_name=MANAGER_NAME))
    )

    names = await load_display_names(
        app_engine, frozenset({staff_id, manager_id, UNKNOWN_ACCOUNT_ID})
    )

    assert names == {staff_id: STAFF_NAME, manager_id: MANAGER_NAME}


async def test_load_display_names_never_returns_a_customer_account(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    customer_account_id, _customer_id = await builder.customer_account()
    staff_id = to_account_id(await builder.account(AccountSpec("staff", display_name=STAFF_NAME)))

    names = await load_display_names(
        app_engine, frozenset({to_account_id(customer_account_id), staff_id})
    )

    assert names == {staff_id: STAFF_NAME}


async def test_load_display_names_of_no_account_is_empty(app_engine: AsyncEngine) -> None:
    assert await load_display_names(app_engine, frozenset()) == {}

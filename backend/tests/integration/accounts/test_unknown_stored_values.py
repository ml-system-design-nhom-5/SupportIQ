"""Adapter tests of stored roles that no enum of backend has, against PostgreSQL 17 (PY-20).

The stores that read a role read an unknown one as an unexpected failure (ERR-05). A role has a
check constraint, which the test drops (`session_without_check`); a trigger refuses a change of
role, so the owner inserts the account with the unknown role. The store of internal accounts
selects only the internal roles, so an account of an unknown role is no internal account and an
admin never sees it.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from app.accounts.adapters.account_store import PostgresAccountStore
from app.accounts.adapters.internal_accounts import PostgresInternalAccountStore
from app.accounts.adapters.password_store import PostgresPasswordStore
from app.accounts.adapters.session_store import PostgresSessionStore
from app.accounts.adapters.tables import AccountRow, SessionRow
from app.accounts.domain import (
    AccountId,
    LoginName,
    OwnAccount,
    SessionIdHash,
    SignInAccount,
)
from app.platform import UnexpectedFailureError
from tests.integration.builders import UNUSABLE_PASSWORD_HASH, AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.stored_values import UNKNOWN_VALUE, session_without_check
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

LOGIN_NAME = "staff-41"
DROP_ACCOUNT_ROLE_CHECK = "ALTER TABLE accounts DROP CONSTRAINT accounts_role_check"
DROP_SESSION_ROLE_CHECK = "ALTER TABLE sessions DROP CONSTRAINT sessions_role_check"
SESSION_ID_HASH_OF_ACCOUNT = "SELECT session_id_hash FROM sessions WHERE account_id = :account_id"
type ReadAccount = Callable[[AsyncSession, UUID], Awaitable[OwnAccount | SignInAccount | None]]


async def load_own_account(session: AsyncSession, account_id: UUID) -> OwnAccount | None:
    return await PostgresPasswordStore(session).load_own_account(AccountId(str(account_id)))


async def load_for_sign_in(session: AsyncSession, _: UUID) -> SignInAccount | None:
    return await PostgresAccountStore(session).load_for_sign_in(LoginName(LOGIN_NAME))


def account_of_an_unknown_role(account_id: UUID) -> Executable:
    return insert(AccountRow).values(
        account_id=account_id,
        login_name=LOGIN_NAME,
        display_name="Staff 41",
        role=UNKNOWN_VALUE,
        is_active=True,
        customer_id=None,
        password_hash=UNUSABLE_PASSWORD_HASH,
        created_at=FAKE_CLOCK_START,
    )


@pytest.mark.parametrize(
    "read_account", [load_own_account, load_for_sign_in], ids=["password-store", "account-store"]
)
async def test_reading_an_account_of_an_unknown_role_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, read_account: ReadAccount
) -> None:
    account_id = builder.next_uuid()

    async with session_without_check(
        worker_database, DROP_ACCOUNT_ROLE_CHECK, account_of_an_unknown_role(account_id)
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await read_account(session, account_id)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_session_of_an_unknown_role_at_creation_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    account_id = await builder.account(AccountSpec("staff"))
    await builder.session(account_id, "staff")
    session_id_hash = await builder.scalar(SESSION_ID_HASH_OF_ACCOUNT, account_id=account_id)
    assert isinstance(session_id_hash, bytes)
    unknown_role = (
        update(SessionRow).where(SessionRow.account_id == account_id).values(role=UNKNOWN_VALUE)
    )

    async with session_without_check(
        worker_database, DROP_SESSION_ROLE_CHECK, unknown_role
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresSessionStore(session).load(SessionIdHash(session_id_hash))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_an_account_of_an_unknown_role_is_no_internal_account(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    account_id = builder.next_uuid()

    async with session_without_check(
        worker_database, DROP_ACCOUNT_ROLE_CHECK, account_of_an_unknown_role(account_id)
    ) as session:
        accounts = PostgresInternalAccountStore(session)
        loaded = await accounts.load_internal(AccountId(str(account_id)))
        page = await accounts.load_page(None, 10)

    assert (loaded, page) == (None, ())

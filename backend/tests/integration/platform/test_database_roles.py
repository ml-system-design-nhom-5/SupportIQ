"""Integration tests of the script that creates `supportiq_app` (backend foundation design)."""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.platform.adapters.database_roles import app_role_password, apply_app_role
from tests.integration.database import WorkerDatabase, create_owner_engine

pytestmark = pytest.mark.anyio

ROLE_ATTRIBUTES = text(
    "SELECT rolcanlogin, rolsuper, rolinherit, rolcreatedb, rolcreaterole, rolreplication,"
    " rolbypassrls FROM pg_roles WHERE rolname = 'supportiq_app'"
)
CAN_CONNECT = text("SELECT has_database_privilege('supportiq_app', current_database(), 'CONNECT')")


async def test_app_role_can_log_in_and_has_no_other_attribute(
    worker_database: WorkerDatabase,
) -> None:
    owner_engine = create_owner_engine(worker_database)

    await apply_app_role(owner_engine, app_role_password(worker_database.app_url))
    async with owner_engine.connect() as connection:
        attributes = (await connection.execute(ROLE_ATTRIBUTES)).one()
        can_connect = await connection.scalar(CAN_CONNECT)
    await owner_engine.dispose()

    assert tuple(attributes) == (True, False, False, False, False, False, False)
    assert can_connect is True


async def test_app_role_password_comes_from_the_app_url(worker_database: WorkerDatabase) -> None:
    password = app_role_password(worker_database.app_url)

    assert password == make_url(worker_database.app_url).password

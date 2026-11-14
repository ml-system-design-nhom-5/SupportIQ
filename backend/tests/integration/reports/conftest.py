"""Fixtures of the report and export tests: the row builder and a signed-in manager."""

from collections.abc import AsyncIterator

import pytest

from tests.integration.application import session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.reports.report_rows import ReportRows


@pytest.fixture
async def rows(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> AsyncIterator[ReportRows]:
    engine = create_owner_engine(worker_database)
    account_id = await builder.account(AccountSpec("staff"))
    yield ReportRows(engine, builder, account_id)
    await engine.dispose()


@pytest.fixture
async def manager_headers(builder: DatabaseBuilder) -> dict[str, str]:
    account_id = await builder.account(AccountSpec("manager"))
    return session_headers(await builder.session(account_id, "manager"))

"""Fixtures of the report and export tests: the row builder and a signed-in manager."""

import pytest

from tests.integration.application import session_headers
from tests.integration.builders import AccountSpec, DatabaseBuilder
from tests.integration.reports.report_rows import ReportRows


@pytest.fixture
async def rows(builder: DatabaseBuilder) -> ReportRows:
    account_id = await builder.account(AccountSpec("staff"))
    return ReportRows(builder, account_id)


@pytest.fixture
async def manager_headers(builder: DatabaseBuilder) -> dict[str, str]:
    account_id = await builder.account(AccountSpec("manager"))
    return session_headers(await builder.session(account_id, "manager"))

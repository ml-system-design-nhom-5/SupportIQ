"""Fixtures of the account tests: a signed-in admin."""

from uuid import UUID

import pytest

from tests.integration.accounts.admin_requests import (
    sign_in_as_new_admin,
)
from tests.integration.builders import DatabaseBuilder


@pytest.fixture
async def admin(builder: DatabaseBuilder) -> tuple[UUID, str]:
    return await sign_in_as_new_admin(builder)


@pytest.fixture
async def admin_token(admin: tuple[UUID, str]) -> str:
    return admin[1]

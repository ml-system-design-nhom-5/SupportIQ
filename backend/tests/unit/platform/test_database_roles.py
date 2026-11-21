"""Tests of reading the password of `supportiq_app` from `database_url_app`."""

import pytest

from app.platform.adapters.database_roles import AppRoleUrlError, app_role_password


def test_app_role_password_is_the_password_of_the_app_url() -> None:
    password = app_role_password(
        "postgresql+asyncpg://supportiq_app:app-test-password@127.0.0.1:5433/supportiq"
    )

    assert password == "app-test-password"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://supportiq_owner:owner-test-password@127.0.0.1:5433/supportiq",
        "postgresql+asyncpg://supportiq_app@127.0.0.1:5433/supportiq",
        "postgresql+asyncpg://supportiq_app:@127.0.0.1:5433/supportiq",
    ],
)
def test_app_role_password_refuses_another_role_or_a_missing_password(url: str) -> None:
    with pytest.raises(AppRoleUrlError) as caught:
        app_role_password(url)

    assert str(caught.value) == (
        "database_url_app must connect as supportiq_app and contain its password"
    )

"""The role `supportiq_app` of the backend replicas, created by a SQL script as the owner."""

from importlib import resources
from typing import ClassVar

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.platform.adapters.database import begin_transaction
from supportiq_backend.platform.domain import BackendError, ErrorCode

APP_ROLE_NAME = "supportiq_app"
_SCRIPT_PACKAGE = "supportiq_backend.migrations"
_SCRIPT_NAME = "create_app_role.sql"
_CREDENTIAL_SETTING_NAME = "supportiq.app_role_password"


class AppRoleUrlError(BackendError):
    """`database_url_app` does not name the role `supportiq_app` with a password."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error; it never repeats the URL, which holds a password."""
        super().__init__(
            f"database_url_app must connect as {APP_ROLE_NAME} and contain its password"
        )


def app_role_password(database_url_app: str) -> str:
    """Return the password of `supportiq_app` from the URL of the replicas.

    Args:
        database_url_app: The `database_url_app` setting.

    Returns:
        The password.

    Raises:
        AppRoleUrlError: The URL names another role or holds no password.
    """
    url = make_url(database_url_app)
    if url.username != APP_ROLE_NAME or not url.password:
        raise AppRoleUrlError
    return str(url.password)


async def apply_app_role(owner_engine: AsyncEngine, password: str) -> None:
    """Create `supportiq_app`, or update its attributes and password, in one transaction.

    Args:
        owner_engine: An engine that connects as the database owner.
        password: The password of `supportiq_app`.
    """
    script = resources.files(_SCRIPT_PACKAGE).joinpath(_SCRIPT_NAME).read_text(encoding="utf-8")
    async with begin_transaction(owner_engine) as connection:
        await connection.execute(
            text("SELECT set_config(:setting, :password, true)"),
            {"setting": _CREDENTIAL_SETTING_NAME, "password": password},
        )
        await connection.exec_driver_sql(script)

"""Running the Alembic migrations of backend on an owner connection (PY-40, ADR-0011)."""

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.platform.adapters.database import begin_transaction

SCRIPT_LOCATION = "app:migrations"
HEAD = "head"
BASE = "base"


async def upgrade_database(owner_engine: AsyncEngine, *, revision: str = HEAD) -> str | None:
    """Apply every migration up to a revision, in one transaction.

    Args:
        owner_engine: An engine that connects as the owner.
        revision: The target revision; the latest by default.

    Returns:
        The revision of the database afterwards.
    """
    async with begin_transaction(owner_engine) as connection:
        return await connection.run_sync(_upgrade, revision)


async def downgrade_database(owner_engine: AsyncEngine, *, revision: str = BASE) -> str | None:
    """Revert migrations down to a revision, in one transaction.

    Args:
        owner_engine: An engine that connects as the owner.
        revision: The target revision; before the first migration by default.

    Returns:
        The revision of the database afterwards, None before the first migration.
    """
    async with begin_transaction(owner_engine) as connection:
        return await connection.run_sync(_downgrade, revision)


def head_revision() -> str | None:
    """Return the latest revision of the migrations.

    Returns:
        The revision that `upgrade_database` reaches by default.
    """
    return ScriptDirectory.from_config(_build_config(None)).get_current_head()


def _upgrade(connection: Connection, revision: str) -> str | None:
    command.upgrade(_build_config(connection), revision)
    return MigrationContext.configure(connection).get_current_revision()


def _downgrade(connection: Connection, revision: str) -> str | None:
    command.downgrade(_build_config(connection), revision)
    return MigrationContext.configure(connection).get_current_revision()


def _build_config(connection: Connection | None) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.attributes["connection"] = connection
    return config

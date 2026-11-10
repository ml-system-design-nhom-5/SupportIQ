"""The one-off database commands, run as the owner `supportiq_owner` (ADR-0011, statement 3).

The replicas never run them and never receive the owner's connection string (backend
foundation design, Database roles and privileges).
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root.runtime import database_timeouts
from supportiq_backend.composition_root.settings_loading import require_setting
from supportiq_backend.platform import EventName, EventRecorder
from supportiq_backend.platform.adapters.database import create_database_engine
from supportiq_backend.platform.adapters.database_roles import app_role_password, apply_app_role
from supportiq_backend.platform.adapters.migrations import upgrade_database
from supportiq_backend.platform.settings import Settings


async def create_app_role(settings: Settings, events: EventRecorder) -> None:
    """Create or update `supportiq_app` with the password of `database_url_app`.

    Args:
        settings: The validated settings, with `database_url_owner`.
        events: Where `database_role.applied` is recorded.

    Raises:
        SettingRequiredError: `database_url_owner` is absent.
        AppRoleUrlError: `database_url_app` names another role or holds no password.
    """
    password = app_role_password(settings.database_url_app.get_secret_value())
    engine = create_owner_engine(settings)
    try:
        await apply_app_role(engine, password)
    finally:
        await engine.dispose()
    events.record(EventName.DATABASE_ROLE_APPLIED)


async def migrate(settings: Settings, events: EventRecorder) -> None:
    """Apply every migration that the database lacks, in one transaction (PY-40).

    Args:
        settings: The validated settings, with `database_url_owner`.
        events: Where `database.migrated` is recorded with the revision.

    Raises:
        SettingRequiredError: `database_url_owner` is absent.
    """
    engine = create_owner_engine(settings)
    try:
        revision = await upgrade_database(engine)
    finally:
        await engine.dispose()
    events.record(EventName.DATABASE_MIGRATED, revision=revision or "")


def create_owner_engine(settings: Settings) -> AsyncEngine:
    """Create an engine that connects as the owner, with the timeouts of the settings.

    Args:
        settings: The validated settings.

    Returns:
        The engine; the caller disposes it.

    Raises:
        SettingRequiredError: `database_url_owner` is absent.
    """
    owner_url = require_setting(settings.database_url_owner, "database_url_owner")
    return create_database_engine(owner_url.get_secret_value(), database_timeouts(settings))

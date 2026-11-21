"""Integration tests of the one-off database commands, run as the owner (ADR-0011)."""

import pytest

from app.composition_root.database_commands import create_app_role, migrate
from app.composition_root.settings_loading import SettingRequiredError
from app.platform import EventName
from tests.integration.application import build_settings
from tests.integration.database import WorkerDatabase
from tests.integration.schema.test_migration import HEAD_REVISION
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio


async def test_migrate_on_a_migrated_database_records_the_head_revision(
    worker_database: WorkerDatabase,
) -> None:
    events = RecordingEventRecorder()
    settings = build_settings(worker_database, database_url_owner=worker_database.owner_url)

    await migrate(settings, events)

    (migrated,) = events.of(EventName.DATABASE_MIGRATED)
    assert migrated.attributes == {"revision": HEAD_REVISION}


async def test_create_app_role_records_that_the_role_was_applied(
    worker_database: WorkerDatabase,
) -> None:
    events = RecordingEventRecorder()
    settings = build_settings(worker_database, database_url_owner=worker_database.owner_url)

    await create_app_role(settings, events)

    assert events.names() == (EventName.DATABASE_ROLE_APPLIED,)


async def test_database_commands_need_the_owner_url(worker_database: WorkerDatabase) -> None:
    settings = build_settings(worker_database)

    with pytest.raises(SettingRequiredError) as caught:
        await migrate(settings, RecordingEventRecorder())

    assert caught.value.setting_name == "database_url_owner"

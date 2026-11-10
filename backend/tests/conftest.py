"""Configuration shared by every test layer, and the fixtures of the layers with a database.

Unit tests run with sockets disabled (TEST-16, `--disable-socket` in pyproject.toml). The
integration and contract layers reach the local PostgreSQL, so their tests get the
`allow_hosts` marker here, which limits them to the loopback addresses.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from hypothesis import settings
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.accounts import Password, PasswordHash
from supportiq_backend.accounts.adapters.credentials import Argon2Passwords
from supportiq_backend.platform.adapters.database import create_database_engine
from tests.integration.application import RunningBackend, build_settings, running_client
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import (
    DESIGN_TIMEOUTS,
    WorkerDatabase,
    create_owner_engine,
    drop_database,
    load_test_database,
    migrate_database,
    recreate_database,
)
from tests.unit.accounts.fakes import KNOWN_PASSWORD
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

_TESTS_ROOT = Path(__file__).parent
_LAYERS_WITH_DATABASE = frozenset({"integration", "contract"})
_LOOPBACK_ADDRESSES = ["127.0.0.1", "::1"]
_HYPOTHESIS_PROFILE = "deterministic"


def pytest_configure() -> None:
    """Make Hypothesis repeatable: the same examples on every run, with no state on disk."""
    settings.register_profile(_HYPOTHESIS_PROFILE, derandomize=True, database=None, deadline=None)
    settings.load_profile(_HYPOTHESIS_PROFILE)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Let the tests of the layers that use the database reach the loopback addresses.

    Args:
        items: The collected tests.
    """
    for item in items:
        layer = item.path.relative_to(_TESTS_ROOT).parts[0]
        if layer in _LAYERS_WITH_DATABASE:
            item.add_marker(pytest.mark.allow_hosts(_LOOPBACK_ADDRESSES))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio, the event loop of uvicorn and asyncpg."""
    return "asyncio"


@pytest.fixture(scope="session")
def worker_database(worker_id: str) -> Iterator[WorkerDatabase]:
    """Create and migrate the database of this worker, and drop it after the session.

    Args:
        worker_id: The pytest-xdist worker ID.

    Yields:
        The database of the worker.
    """
    database = load_test_database(worker_id)
    asyncio.run(recreate_database(database))
    asyncio.run(migrate_database(database))
    yield database
    asyncio.run(drop_database(database))


@pytest.fixture
async def app_engine(worker_database: WorkerDatabase) -> AsyncIterator[AsyncEngine]:
    """Connect as `supportiq_app` with the timeouts of the design.

    Args:
        worker_database: The database of the worker.

    Yields:
        The engine, disposed after the test.
    """
    engine = create_database_engine(worker_database.app_url, DESIGN_TIMEOUTS)
    yield engine
    await engine.dispose()


@pytest.fixture
async def backend(worker_database: WorkerDatabase) -> AsyncIterator[RunningBackend]:
    """Run the wired application against the worker database.

    Args:
        worker_database: The database of the worker.

    Yields:
        The running application with its fake clock and its recorded events.
    """
    clock = FakeClock()
    events = RecordingEventRecorder()
    async with running_client(build_settings(worker_database), events, clock) as client:
        yield RunningBackend(client, clock, events)


@pytest.fixture(scope="session")
def known_password_hash() -> PasswordHash:
    """Hash the known test password once per worker, because Argon2id is slow on purpose."""
    return Argon2Passwords().hash_blocking(Password(KNOWN_PASSWORD))


@pytest.fixture
async def builder(worker_database: WorkerDatabase) -> AsyncIterator[DatabaseBuilder]:
    """Insert test data as the owner, with sensible defaults (TEST-05).

    Args:
        worker_database: The database of the worker.

    Yields:
        The builder, whose engine is disposed after the test.
    """
    engine = create_owner_engine(worker_database)
    yield DatabaseBuilder(engine)
    await engine.dispose()

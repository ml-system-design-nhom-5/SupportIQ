"""The seed and reset commands, run as the owner (backend foundation design, Seed and reset).

The same file always produces the same rows, IDs, and times, apart from `password_hash`, which
Argon2id salts randomly. Reset empties every backend table and seeds again in one transaction,
so a failure leaves the database as it was.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.accounts import (
    LoginName,
    Password,
    PasswordHash,
    PasswordHasher,
    Role,
)
from app.accounts.adapters.credentials import Argon2Passwords
from app.accounts.adapters.seed import SeedAccount, insert_accounts
from app.commerce.adapters.seed import (
    CommerceSeed,
    insert_catalog_and_orders,
    insert_customers,
)
from app.composition_root.database_commands import create_owner_engine
from app.composition_root.settings_loading import require_setting
from app.migrations.tables import TRUNCATE_EVERY_TABLE
from app.platform import EventName, EventRecorder, UnexpectedFailureError
from app.platform.adapters.database import begin_transaction
from app.platform.settings import Settings

# Relative to the working directory: `backend/` in a clone, the working directory of the image.
# TODO(#11): the seed file has no dataset manifest (DATA-09).
SEED_FILE = Path("seed/synthetic-dev-only-v1.json")

# Whether one of the tables that the seed writes holds a row (local run design, Data and
# contracts). The seed writes them in one transaction, so they are all empty or all seeded.
_SEED_ROWS_EXIST = text(
    "SELECT EXISTS (SELECT FROM customers) OR EXISTS (SELECT FROM accounts) "
    "OR EXISTS (SELECT FROM products) OR EXISTS (SELECT FROM orders) "
    "OR EXISTS (SELECT FROM order_lines) OR EXISTS (SELECT FROM shipments) "
    "OR EXISTS (SELECT FROM refunds)"
)


class SeedFileInvalidError(UnexpectedFailureError):
    """The seed file is missing or does not match its format."""


class SeedDocument(BaseModel):
    """The seed file, labeled `synthetic-dev-only` (DATA-03, DATA-04)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: Literal["synthetic-dev-only"]
    version: str
    accounts: tuple[SeedAccount, ...]
    commerce: CommerceSeed


def load_seed_document(seed_file: Path) -> SeedDocument:
    """Read and validate the seed file.

    Args:
        seed_file: The path of the file.

    Returns:
        The validated document.

    Raises:
        SeedFileInvalidError: The file is missing or invalid.
    """
    try:
        return SeedDocument.model_validate(json.loads(seed_file.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as error:
        raise SeedFileInvalidError from error


def seed_passwords(settings: Settings) -> Mapping[Role, Password]:
    """Collect the password of each role, one secret setting per role (ADR-0009, statement 1).

    Args:
        settings: The validated settings.

    Returns:
        The passwords by role.

    Raises:
        SettingRequiredError: A password setting is absent.
    """
    secrets = {
        Role.CUSTOMER: require_setting(settings.seed_password_customer, "seed_password_customer"),
        Role.STAFF: require_setting(settings.seed_password_staff, "seed_password_staff"),
        Role.MANAGER: require_setting(settings.seed_password_manager, "seed_password_manager"),
        Role.ADMIN: require_setting(settings.seed_password_admin, "seed_password_admin"),
    }
    return {role: Password(secret.get_secret_value()) for role, secret in secrets.items()}


async def hash_account_passwords(
    document: SeedDocument, passwords: Mapping[Role, Password]
) -> Mapping[LoginName, PasswordHash]:
    """Hash the password of every account, with a new salt per account.

    The seed uses the same port and adapter as every write that sets a password (ADR-0015).

    Args:
        document: The seed file.
        passwords: The passwords by role.

    Returns:
        The hashes by login name.
    """
    hasher: PasswordHasher = Argon2Passwords()
    return {
        LoginName(account.login_name): await hasher.hash_password(passwords[account.role])
        for account in document.accounts
    }


async def insert_seed(
    connection: AsyncConnection,
    document: SeedDocument,
    password_hashes: Mapping[LoginName, PasswordHash],
) -> None:
    """Insert the seed rows in the order of their foreign keys.

    Args:
        connection: An owner connection in the transaction of the command.
        document: The seed file.
        password_hashes: The hashes by login name.
    """
    await insert_customers(connection, document.commerce)
    await insert_accounts(connection, document.accounts, password_hashes)
    await insert_catalog_and_orders(connection, document.commerce)


async def seed(settings: Settings, events: EventRecorder, *, seed_file: Path = SEED_FILE) -> None:
    """Load the seed file into an empty database, as the owner.

    Args:
        settings: The validated settings, with the owner URL and the seed passwords.
        events: Where `seed.loaded` is recorded.
        seed_file: The seed file.

    Raises:
        SettingRequiredError: A setting that the command needs is absent.
        SeedFileInvalidError: The file is missing or invalid.
        DatabaseOperationError: The database already holds seed rows.
    """
    document = load_seed_document(seed_file)
    password_hashes = await hash_account_passwords(document, seed_passwords(settings))
    engine = create_owner_engine(settings)
    try:
        async with begin_transaction(engine) as connection:
            await insert_seed(connection, document, password_hashes)
    finally:
        await engine.dispose()
    events.record(EventName.SEED_LOADED)


async def seed_if_empty(
    settings: Settings, events: EventRecorder, *, seed_file: Path = SEED_FILE
) -> None:
    """Load the seed file as `seed` does, or change nothing when the database is seeded.

    The local run calls it at every start, so a second start keeps the data of the first
    (local run design, Data and contracts). The check and the inserts share one transaction,
    and the passwords are hashed only when the seed is loaded.

    Args:
        settings: The validated settings, with the owner URL and the seed passwords.
        events: Where `seed.loaded` or `seed.skipped` is recorded.
        seed_file: The seed file.

    Raises:
        SettingRequiredError: A setting that the command needs is absent.
        SeedFileInvalidError: The file is missing or invalid.
    """
    document = load_seed_document(seed_file)
    passwords = seed_passwords(settings)
    engine = create_owner_engine(settings)
    try:
        async with begin_transaction(engine) as connection:
            if await connection.scalar(_SEED_ROWS_EXIST):
                events.record(EventName.SEED_SKIPPED)
                return
            password_hashes = await hash_account_passwords(document, passwords)
            await insert_seed(connection, document, password_hashes)
    finally:
        await engine.dispose()
    events.record(EventName.SEED_LOADED)


async def reset(settings: Settings, events: EventRecorder, *, seed_file: Path = SEED_FILE) -> None:
    """Empty every backend table and seed again, in one transaction (SEC-32).

    Role changes, deactivations, tickets, and audit log entries all return to the seeded state.

    Args:
        settings: The validated settings, with the owner URL and the seed passwords.
        events: Where `seed.reset` is recorded.
        seed_file: The seed file.

    Raises:
        SettingRequiredError: A setting that the command needs is absent.
        SeedFileInvalidError: The file is missing or invalid.
    """
    document = load_seed_document(seed_file)
    password_hashes = await hash_account_passwords(document, seed_passwords(settings))
    engine = create_owner_engine(settings)
    try:
        async with begin_transaction(engine) as connection:
            await connection.execute(text(TRUNCATE_EVERY_TABLE))
            await insert_seed(connection, document, password_hashes)
    finally:
        await engine.dispose()
    events.record(EventName.SEED_RESET)

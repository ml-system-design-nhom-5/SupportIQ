"""The accounts section of the seed file, and its insert as the owner (ADR-0009, ADR-0012).

Admin and customer accounts exist only through the seed: `supportiq_app` inserts only `staff`
and `manager` accounts (ADR-0015). Passwords never come from the file; each role has a secret
setting, hashed here with a new salt per account.
"""

from collections.abc import Mapping, Sequence
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.accounts.adapters.tables import AccountRow
from app.accounts.domain import LoginName, PasswordHash, Role, normalize_login_name


class SeedLoginNameError(ValueError):
    """A login name of the seed file is not in its normalized form."""

    def __init__(self) -> None:
        """Build the error."""
        super().__init__("Seed login names are normalized, such as `staff-1`")


def _require_normalized(login_name: str) -> str:
    if normalize_login_name(login_name) != login_name:
        raise SeedLoginNameError
    return login_name


class SeedAccount(BaseModel):
    """An account of the seed file, without any password."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: UUID
    login_name: Annotated[str, Field(min_length=1), AfterValidator(_require_normalized)]
    display_name: Annotated[str, Field(min_length=1)]
    role: Role
    is_active: bool
    customer_id: UUID | None
    created_at: AwareDatetime


async def insert_accounts(
    connection: AsyncConnection,
    accounts: Sequence[SeedAccount],
    password_hash_by_login_name: Mapping[LoginName, PasswordHash],
) -> None:
    """Insert the accounts with their password hashes.

    Args:
        connection: An owner connection in the transaction of the command.
        accounts: The accounts of the seed file.
        password_hash_by_login_name: The Argon2id hash of each account.
    """
    await connection.execute(
        insert(AccountRow),
        [
            {
                "account_id": account.account_id,
                "login_name": account.login_name,
                "display_name": account.display_name,
                "role": account.role.value,
                "is_active": account.is_active,
                "customer_id": account.customer_id,
                "password_hash": password_hash_by_login_name[LoginName(account.login_name)],
                "created_at": account.created_at,
            }
            for account in accounts
        ],
    )

"""The Alembic environment of backend: migrations run on a connection the caller provides.

`backend migrate` opens the connection as the owner and passes it in the configuration
attribute `connection`, so this module never reads a URL or the environment (ARCH-33). There
is no autogeneration: each migration is written by hand and reviewed (PY-40).
"""

from typing import ClassVar

from alembic import context
from sqlalchemy.engine import Connection

from app.platform import BackendError, ErrorCode

_CONNECTION_ATTRIBUTE = "connection"


class MigrationConnectionMissingError(BackendError):
    """Alembic ran without the connection that `backend migrate` provides."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error."""
        super().__init__("Run migrations with `backend migrate`, which provides the connection")


def run_migrations() -> None:
    """Run the migrations on the connection of the configuration, in its transaction.

    Raises:
        MigrationConnectionMissingError: No connection was provided.
    """
    connection = context.config.attributes.get(_CONNECTION_ATTRIBUTE)
    if not isinstance(connection, Connection):
        raise MigrationConnectionMissingError
    context.configure(connection=connection, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations()

"""What the PostgreSQL adapters of every feature share.

This is a public entry point of `platform`, next to `platform.web`, for adapters only: it uses
SQLAlchemy, so `platform/__init__.py` does not export it.
"""

from sqlalchemy import ColumnElement, Text, delete, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Compares text by Unicode code point, whatever the locale of the database.
BYTE_ORDER_COLLATION = "C"
_ROW_ADDRESS = literal_column("ctid", type_=Text())


async def delete_rows_not_held(
    session: AsyncSession, table: type[DeclarativeBase], condition: ColumnElement[bool]
) -> None:
    """Delete the rows of a condition; rows that another transaction holds are left for later.

    The deletion of expired rows runs inside other writes, so it must never wait for a lock
    that a concurrent request holds (ARCH-41).

    Args:
        session: The session of the transaction.
        table: The ORM model of the table.
        condition: Which rows to delete.
    """
    held_elsewhere_skipped = (
        select(_ROW_ADDRESS).select_from(table).where(condition).with_for_update(skip_locked=True)
    )
    await session.execute(
        delete(table)
        .where(_ROW_ADDRESS.in_(held_elsewhere_skipped))
        .execution_options(synchronize_session=False)
    )

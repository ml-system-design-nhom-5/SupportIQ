"""What the PostgreSQL adapters of every feature share.

This is a public entry point of `platform`, next to `platform.web`, for adapters only: it uses
SQLAlchemy, so `platform/__init__.py` does not export it.
"""

from enum import StrEnum

from sqlalchemy import ColumnElement, Text, delete, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.platform import UnexpectedFailureError

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


def parse_stored_enum[EnumT: StrEnum](enum_type: type[EnumT], value: str) -> EnumT:
    """Turn a text that an adapter stored from an enum back into its member.

    Backend stores only values of its enums, so a value that no member has is a defect of
    backend, such as a migration that allows a value this code does not know, and the read fails
    as an unexpected failure (ERR-05).

    Args:
        enum_type: The enum of the column.
        value: The stored text.

    Returns:
        The member with that value.

    Raises:
        UnexpectedFailureError: No member has the value; the `ValueError` is its cause.
    """
    try:
        return enum_type(value)
    except ValueError as error:
        raise UnexpectedFailureError from error


def parse_optional_stored_enum[EnumT: StrEnum](
    enum_type: type[EnumT], value: str | None
) -> EnumT | None:
    """Turn a nullable text that an adapter stored from an enum back into its member.

    Args:
        enum_type: The enum of the column.
        value: The stored text, or None for SQL `NULL`.

    Returns:
        The member with that value, or None for None.

    Raises:
        UnexpectedFailureError: No member has the value; the `ValueError` is its cause.
    """
    return None if value is None else parse_stored_enum(enum_type, value)

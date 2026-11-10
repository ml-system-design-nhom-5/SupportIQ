"""Running raw SQL as a database role and reading the SQLSTATE of a refusal."""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"


async def run_statement(engine: AsyncEngine, statement: str, **parameters: object) -> None:
    """Run one statement in its own committed transaction.

    Args:
        engine: The engine of the role under test.
        statement: The SQL text with bound parameters.
        **parameters: The parameters.
    """
    async with engine.begin() as connection:
        await connection.execute(text(statement), parameters)


async def sqlstate_of_refusal(engine: AsyncEngine, statement: str, **parameters: object) -> str:
    """Run a statement that the database must refuse, and return the SQLSTATE of the refusal.

    Args:
        engine: The engine of the role under test.
        statement: The SQL text with bound parameters.
        **parameters: The parameters.

    Returns:
        The SQLSTATE, or `accepted` when the statement ran.
    """
    try:
        await run_statement(engine, statement, **parameters)
    except DBAPIError as error:
        sqlstate: object = getattr(error.orig, "sqlstate", None)
        return str(sqlstate)
    return "accepted"

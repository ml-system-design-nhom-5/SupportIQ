"""One row per code of a JSON array column, for the breakdowns of the report by reason code.

The reason codes of decisions, escalations, and suggestion parts are JSON arrays of text, as
the stores of tickets and suggestions write them. A record with two codes gives two rows, so it
counts once under each code (backend ticket workflow design, Reports).
"""

from sqlalchemy import ColumnElement, FromClause, func, true
from sqlalchemy.sql.selectable import LateralFromClause

CODE_COLUMN = "code"


def expand_codes(codes: ColumnElement[object], alias: str) -> LateralFromClause:
    """Return `jsonb_array_elements_text` of a column as a LATERAL table with one `code` column.

    Args:
        codes: A `jsonb` array column of the table that the result is joined to.
        alias: The name of the expansion in FROM.

    Returns:
        The expansion; join it with `join_codes`.
    """
    return (
        func.jsonb_array_elements_text(codes)
        .table_valued(CODE_COLUMN)
        .render_derived()
        .lateral(alias)
    )


def join_codes(table: FromClause, codes: LateralFromClause) -> FromClause:
    """Join a table to the expansion of one of its code columns.

    Args:
        table: The table.
        codes: The expansion of `expand_codes`.

    Returns:
        `table JOIN LATERAL ... ON true`; a record without a code gives no row.
    """
    return table.join(codes, true())

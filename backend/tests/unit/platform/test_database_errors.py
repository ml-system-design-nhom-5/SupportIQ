"""Tests of the classification of database errors: not available now, or a defect (ERR-09)."""

import pytest

from app.platform.adapters.database import is_database_unavailable


class DriverError(Exception):
    """A driver error with the SQLSTATE that PostgreSQL returned."""

    def __init__(self, sqlstate: str | None) -> None:
        """Keep the SQLSTATE, as asyncpg errors do."""
        super().__init__("driver error")
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    "error",
    [
        DriverError("57014"),
        DriverError("55P03"),
        DriverError("40001"),
        DriverError("40P01"),
        DriverError("08006"),
        DriverError("53300"),
        DriverError("57P01"),
        ConnectionRefusedError(),
        TimeoutError(),
    ],
)
def test_timeouts_lock_waits_and_connection_failures_mean_unavailable(error: Exception) -> None:
    is_unavailable = is_database_unavailable(error, is_disconnect=False)

    assert is_unavailable


@pytest.mark.parametrize(
    "error", [DriverError("23505"), DriverError("42501"), DriverError("P0001"), DriverError(None)]
)
def test_other_database_errors_are_defects(error: Exception) -> None:
    is_unavailable = is_database_unavailable(error, is_disconnect=False)

    assert not is_unavailable


def test_a_lost_connection_means_unavailable() -> None:
    is_unavailable = is_database_unavailable(DriverError("23505"), is_disconnect=True)

    assert is_unavailable

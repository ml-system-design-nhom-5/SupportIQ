"""The limits of the test layers: loopback only, and no password in a repr (TEST-16, PY-44)."""

import socket

import pytest
from pytest_socket import SocketConnectBlockedError

from tests.integration.database import WorkerDatabase

ADDRESS_OUTSIDE_THE_LOOPBACK = ("192.0.2.1", 80)


def test_an_integration_test_cannot_connect_outside_the_loopback() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection,
        pytest.warns(UserWarning, match="192.0.2.1"),
        pytest.raises(SocketConnectBlockedError),
    ):
        connection.connect(ADDRESS_OUTSIDE_THE_LOOPBACK)


def test_the_repr_of_a_worker_database_holds_no_url(worker_database: WorkerDatabase) -> None:
    assert "postgresql" not in repr(worker_database)

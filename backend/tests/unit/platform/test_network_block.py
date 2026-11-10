"""The test runner blocks the network in the unit layer (TEST-16)."""

import socket

import pytest
from pytest_socket import SocketBlockedError


def test_a_unit_test_cannot_open_a_network_socket() -> None:
    with pytest.warns(UserWarning, match="socket"), pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)

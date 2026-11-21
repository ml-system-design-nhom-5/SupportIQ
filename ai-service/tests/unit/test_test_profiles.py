"""The test setup keeps every test offline, away from cached weights, and without keys."""

import os
import socket
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError

from tests.conftest import HUGGING_FACE_HOME_VARIABLE, OFFLINE_ENVIRONMENT, PROVIDER_KEY_VARIABLES


def test_a_unit_test_cannot_open_a_network_socket() -> None:
    with pytest.warns(UserWarning, match="socket"), pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_hugging_face_runs_offline() -> None:
    for name, value in OFFLINE_ENVIRONMENT.items():
        assert os.environ[name] == value


def test_the_hugging_face_home_holds_no_cached_model() -> None:
    home = Path(os.environ[HUGGING_FACE_HOME_VARIABLE])

    assert home.is_dir()
    assert not any(home.iterdir())


def test_no_key_of_the_llm_provider_reaches_a_test() -> None:
    assert not any(name in os.environ for name in PROVIDER_KEY_VARIABLES)


def test_tests_with_real_weights_are_deselected_by_default(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.getoption("markexpr") == "not real_model"

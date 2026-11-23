"""Resource boundaries must fail before accessing network, keys or weights."""
import socket

import pytest
transformers = pytest.importorskip("transformers")
AutoTokenizer = transformers.AutoTokenizer


def test_default_profile_blocks_network_before_connect():
    with socket.socket() as client:
        with pytest.raises(RuntimeError, match="offline"):
            client.connect(("127.0.0.1", 9))


def test_default_profile_blocks_cached_and_remote_weights(tmp_path):
    with pytest.raises(RuntimeError, match="real_model"):
        AutoTokenizer.from_pretrained(str(tmp_path))


def test_default_profile_blocks_udp():
    with socket.socket(type=socket.SOCK_DGRAM) as client:
        with pytest.raises(RuntimeError, match="offline"):
            client.sendto(b"test", ("127.0.0.1", 9))


@pytest.mark.parametrize("method,host", [
    ("gethostbyname", "localhost"),
    ("gethostbyname_ex", "localhost"),
    ("gethostbyaddr", "127.0.0.1"),
])
def test_default_profile_blocks_native_dns(method, host):
    with pytest.raises(RuntimeError, match="offline"):
        getattr(socket, method)(host)


def test_live_preflight_requires_explicit_credentials(monkeypatch):
    from tests.conftest import pytest_collection_modifyitems
    from types import SimpleNamespace

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    config = SimpleNamespace(getoption=lambda name: True)
    item = SimpleNamespace(keywords={"live": True})
    with pytest.raises(pytest.UsageError, match="GEMINI_API_KEY"):
        pytest_collection_modifyitems(config, [item])

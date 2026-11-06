"""Offline provider fixtures and test profile configuration.
Ensures tests never call external network services unless explicitly opted-in via --run-live.
"""
import json
import ipaddress
import os
import socket
import threading
import uuid
from pathlib import Path
import httpx
import pytest

from apps.core_backend.llm.gemini import GeminiDraftClient


def pytest_configure(config):
    if not config.option.basetemp:
        config.option.basetemp = str(Path(__file__).resolve().parents[1] / "tmp" / "pytest" / uuid.uuid4().hex)
    Path(config.option.basetemp).parent.mkdir(parents=True, exist_ok=True)


def pytest_sessionstart(session):
    # Shared open handles allow parallel runs; the cleaner requires exclusive access.
    session._cleanup_lock = (Path(__file__).resolve().parents[1] / ".pytest-cleanup.lock").open("a+b")


def pytest_sessionfinish(session, exitstatus):
    session._cleanup_lock.close()


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests requiring valid external credentials and network egress",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in Path(str(getattr(item, "path", ""))).parts:
            item.add_marker(pytest.mark.integration)
    if config.getoption("--run-live") and any("live" in item.keywords for item in items):
        if not os.environ.get("GEMINI_API_KEY"):
            raise pytest.UsageError("Live profile requires explicit GEMINI_API_KEY; .env is not loaded by pytest")
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="requires --run-live option and valid credentials")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def offline_resources(monkeypatch, request):
    if request.node.get_closest_marker("live") and request.config.getoption("--run-live"):
        return
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    integration = request.node.get_closest_marker("integration") is not None
    local_pair = threading.local()
    original_pair = socket.socketpair
    def socketpair(*args, **kwargs):
        # Windows asyncio builds its local wakeup pipe through TCP socketpair.
        local_pair.active = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            local_pair.active = False
    monkeypatch.setattr(socket, "socketpair", socketpair)

    def check_address(address):
        host = address[0] if isinstance(address, tuple) else address
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not (loopback and (integration or getattr(local_pair, "active", False))):
            raise RuntimeError("offline test blocked network; loopback requires integration marker")

    for method in ("connect", "connect_ex"):
        original = getattr(socket.socket, method)
        def guarded_connect(client, address, _original=original):
            check_address(address)
            return _original(client, address)
        monkeypatch.setattr(socket.socket, method, guarded_connect)
    original_sendto = socket.socket.sendto
    def guarded_sendto(client, *args):
        check_address(args[-1])
        return original_sendto(client, *args)
    monkeypatch.setattr(socket.socket, "sendto", guarded_sendto)
    original_lookup = socket.getaddrinfo
    def guarded_lookup(host, port, *args, **kwargs):
        check_address((host, port))
        return original_lookup(host, port, *args, **kwargs)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_lookup)
    for method in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        original = getattr(socket, method)
        def guarded_resolve(host, _original=original):
            check_address((host, 0))
            return _original(host)
        monkeypatch.setattr(socket, method, guarded_resolve)

    if not request.node.get_closest_marker("real_model"):
        def no_weights(*args, **kwargs):
            raise RuntimeError("loading weights/tokenizer requires explicit real_model profile")
        try:
            import transformers
            monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", no_weights)
            monkeypatch.setattr("transformers.models.auto.auto_factory._BaseAutoModelClass.from_pretrained", no_weights)
        except ImportError:
            pass


@pytest.fixture
def offline_retrieval():
    """Exercise real eligibility/index code with explicit synthetic embeddings."""
    from apps.core_backend.retrieval.adapter import RetrievalAdapter
    from pipeline.evaluation.mock_dependencies import MockPolicyEncoder
    return RetrievalAdapter(encoder=MockPolicyEncoder(), relevance_threshold=0.35)


@pytest.fixture
def fake_llm():
    def handler(request):
        return httpx.Response(200, json={"modelVersion": "gemini-2.5-flash", "candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": json.dumps({
                "answerable": True, "answer": "Standard Return Policy: Return within 30 days. [S1]",
                "citations": ["S1"]})}]}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        yield GeminiDraftClient(api_key="offline-test-key", model="gemini-2.5-flash", http_client=transport)

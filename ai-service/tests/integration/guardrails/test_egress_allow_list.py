"""ai-service connects outside the system only to the hosts of its egress allow-list (SEC-40).

The allow-list ships with the package and holds only the Gemini host (ADR-0010, Egress
control; ADR-0018, Egress). The one client that the command creates refuses every other
request before it connects, and the lifespan closes it at shutdown. No module other than the
egress module creates an HTTP client or a transport, opens a connection, or imports a library
that exists to open one. Integration tests may connect only to loopback, so a request that the
client did not refuse would fail here with a blocked socket, not with `EgressRefusedError`.
"""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

import supportiq_ai_service
from supportiq_ai_service.composition_root import cli
from supportiq_ai_service.platform.adapters.egress import (
    EgressAllowList,
    EgressRefusedError,
    packaged_egress_allow_list,
)
from tests.integration.application import build_settings
from tests.unit.platform.fakes import RecordingEgressClientFactory, RecordingEventRecorder
from tests.unit.release.release_folder import write_release

GEMINI_HOST = "generativelanguage.googleapis.com"
# Hosts outside the allow-list, as addresses, so that a client that failed to refuse would
# reach the socket block without a DNS lookup.
OTHER_HOST_URLS = (
    "https://203.0.113.10/v1beta/models",
    "http://203.0.113.10/v1beta/models",
    "https://203.0.113.10:8443/v1beta/models",
    "https://[2001:db8::10]/v1beta/models",
)
SOURCE_ROOT = Path(supportiq_ai_service.__file__).parent
EGRESS_MODULE = SOURCE_ROOT / "platform" / "adapters" / "egress.py"
# The calls that create an HTTP client or a transport, or open a connection, by module. Only a
# call counts, so a type annotation such as `httpx.Client` does not.
CONNECTING_NAMES = {
    "httpx": frozenset(
        {"Client", "AsyncClient", "HTTPTransport", "AsyncHTTPTransport"}
        | {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
    ),
    "socket": frozenset({"create_connection", "socket"}),
}
# Modules whose import alone counts, in every form, because they exist to open connections.
# `huggingface_hub` downloads models, and ai-service downloads nothing when it runs (ADR-0018,
# Egress, statement 2). The scan reads only the code of ai-service, so a library that imports
# one of these itself, as transformers does, is not counted.
FORBIDDEN_MODULES = (
    "urllib.request",
    "http.client",
    "requests",
    "urllib3",
    "httpcore",
    "aiohttp",
    "huggingface_hub",
)


def test_the_packaged_allow_list_holds_only_the_gemini_host() -> None:
    assert packaged_egress_allow_list() == EgressAllowList("1", frozenset({GEMINI_HOST}))


def assert_refuses_other_hosts(client: httpx.Client) -> None:
    """Check that the client refuses each request outside the allow-list, without connecting.

    Args:
        client: The client of the replica.
    """
    assert client.trust_env is False
    assert client.follow_redirects is False
    for url in OTHER_HOST_URLS:
        with pytest.raises(EgressRefusedError):
            client.get(url)


@pytest.mark.anyio
async def test_the_client_of_a_replica_refuses_every_other_host_before_it_connects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    factory = RecordingEgressClientFactory()
    monkeypatch.setattr(cli, "create_egress_client", factory)
    settings = build_settings(write_release(tmp_path))

    app = cli.build_application(settings, RecordingEventRecorder())

    ((allow_list, client),) = factory.created
    assert allow_list == packaged_egress_allow_list()
    async with app.router.lifespan_context(app):
        assert_refuses_other_hosts(client)
        assert not client.is_closed
    assert client.is_closed


@dataclass(frozen=True, slots=True)
class Connection:
    """A place in the code that creates an HTTP client or opens a connection.

    Attributes:
        module: The path of the module, from the package root.
        line: The line.
        what: What it calls or imports.
    """

    module: str
    line: int
    what: str


@dataclass(slots=True)
class _ImportedNames:
    """The local names that a module binds to connecting modules and functions.

    Attributes:
        modules: Each local name of `httpx` or `socket`, with the module it names.
        functions: Each local name of a connecting function, with its full name.
    """

    modules: dict[str, str]
    functions: dict[str, str]


def _is_forbidden(module: str) -> bool:
    return any(module == name or module.startswith(f"{name}.") for name in FORBIDDEN_MODULES)


def _imported_names(tree: ast.Module) -> _ImportedNames:
    names = _ImportedNames({}, {})
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.modules.update(
                (alias.asname or alias.name, alias.name)
                for alias in node.names
                if alias.name in CONNECTING_NAMES
            )
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            connecting = CONNECTING_NAMES.get(node.module, frozenset[str]())
            names.functions.update(
                (alias.asname or alias.name, f"{node.module}.{alias.name}")
                for alias in node.names
                if alias.name in connecting
            )
    return names


def _forbidden_imports(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [f"import {alias.name}" for alias in node.names if _is_forbidden(alias.name)]
    if node.level != 0 or node.module is None:
        return []
    module = node.module
    return [
        f"from {module} import {alias.name}"
        for alias in node.names
        if _is_forbidden(module) or _is_forbidden(f"{module}.{alias.name}")
    ]


def _connecting_call(call: ast.Call, names: _ImportedNames) -> str | None:
    function = call.func
    if isinstance(function, ast.Name):
        full_name = names.functions.get(function.id)
        return None if full_name is None else f"{full_name}()"
    if not (isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name)):
        return None
    module = names.modules.get(function.value.id)
    if module is None or function.attr not in CONNECTING_NAMES[module]:
        return None
    return f"{module}.{function.attr}()"


def find_connections(module: Path, root: Path = SOURCE_ROOT) -> list[Connection]:
    """Find every call that creates an HTTP client or connects, and every forbidden import.

    Args:
        module: A Python module.
        root: The folder that the reported paths start from.

    Returns:
        The places, by line.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    names = _imported_names(tree)
    path = str(module.relative_to(root))
    found: list[Connection] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            found.extend(Connection(path, node.lineno, what) for what in _forbidden_imports(node))
        elif isinstance(node, ast.Call) and (what := _connecting_call(node, names)) is not None:
            found.append(Connection(path, node.lineno, what))
    return sorted(found, key=lambda connection: connection.line)


def source_modules() -> Iterator[Path]:
    """Yield every Python module of the real source tree of ai-service, generated code included."""
    yield from sorted(SOURCE_ROOT.rglob("*.py"))


def test_only_the_egress_module_creates_an_http_client_or_opens_a_connection() -> None:
    modules = list(source_modules())
    assert EGRESS_MODULE in modules

    connections = [
        connection
        for module in modules
        if module != EGRESS_MODULE
        for connection in find_connections(module)
    ]

    assert connections == []


def test_the_scan_finds_the_transport_and_the_client_of_the_egress_module() -> None:
    assert [connection.what for connection in find_connections(EGRESS_MODULE)] == [
        "httpx.HTTPTransport()",
        "httpx.Client()",
    ]


@pytest.mark.parametrize(
    ("code", "what"),
    [
        ("import httpx\nhttpx.Client()\n", "httpx.Client()"),
        ("import httpx as h\nh.AsyncClient()\n", "httpx.AsyncClient()"),
        ("import httpx\nhttpx.post('https://example.test')\n", "httpx.post()"),
        ("from httpx import Client as C\nC()\n", "httpx.Client()"),
        ("from httpx import stream\nstream('GET', 'u')\n", "httpx.stream()"),
        ("def f():\n    import httpx\n    return httpx.get('u')\n", "httpx.get()"),
        ("import httpx\nhttpx.HTTPTransport().handle_request(r)\n", "httpx.HTTPTransport()"),
        (
            "from httpx import AsyncHTTPTransport\nAsyncHTTPTransport()\n",
            "httpx.AsyncHTTPTransport()",
        ),
        ("import socket\nsocket.create_connection(('h', 1))\n", "socket.create_connection()"),
        (
            "from socket import create_connection\ncreate_connection(('h', 1))\n",
            "socket.create_connection()",
        ),
        ("import socket\nsocket.socket()\n", "socket.socket()"),
        ("from socket import socket as s\ns()\n", "socket.socket()"),
        ("import urllib.request\n", "import urllib.request"),
        ("from urllib import request\n", "from urllib import request"),
        ("from urllib.request import urlopen\n", "from urllib.request import urlopen"),
        ("import http.client\n", "import http.client"),
        ("from http import client\n", "from http import client"),
        ("import requests\n", "import requests"),
        ("import urllib3\n", "import urllib3"),
        ("from urllib3 import PoolManager\n", "from urllib3 import PoolManager"),
        ("import httpcore\n", "import httpcore"),
        ("from httpcore import ConnectionPool\n", "from httpcore import ConnectionPool"),
        ("import aiohttp\n", "import aiohttp"),
        ("from aiohttp import ClientSession\n", "from aiohttp import ClientSession"),
        ("import huggingface_hub\n", "import huggingface_hub"),
        (
            "from huggingface_hub import hf_hub_download\n",
            "from huggingface_hub import hf_hub_download",
        ),
        ("import huggingface_hub.file_download as d\n", "import huggingface_hub.file_download"),
    ],
)
def test_the_scan_finds_each_form_of_a_connection(tmp_path: Path, code: str, what: str) -> None:
    module = tmp_path / "module.py"
    module.write_text(code, encoding="utf-8")

    assert [connection.what for connection in find_connections(module, tmp_path)] == [what]


def test_the_scan_ignores_type_annotations(tmp_path: Path) -> None:
    module = tmp_path / "module.py"
    module.write_text(
        "import httpx\n\n"
        "def send(client: httpx.Client) -> httpx.Response:\n"
        "    return client.get('u')\n",
        encoding="utf-8",
    )

    assert find_connections(module, tmp_path) == []

"""The egress allow-list file is read strictly, and its client reaches only its hosts (SEC-40).

Every client here sends through `RecordingNetwork`, so a refused request is one that never
reached the network.
"""

import json
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from app.platform.adapters.egress import (
    ALLOW_LIST_FILE_NAME,
    EgressAllowList,
    EgressAllowListInvalidError,
    EgressRefusedError,
    create_egress_client,
    load_egress_allow_list,
)
from tests.unit.platform.fakes import RecordingNetwork

GEMINI_HOST = "generativelanguage.googleapis.com"
ALLOW_LIST = EgressAllowList(version="1", hosts=frozenset({GEMINI_HOST}))
ALLOWED_URL = f"https://{GEMINI_HOST}/v1beta/models/gemini-test:generateContent"


def write_allow_list(directory: Path, document: object) -> Path:
    path = directory / ALLOW_LIST_FILE_NAME
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_a_valid_file_gives_its_version_and_its_hosts(tmp_path: Path) -> None:
    path = write_allow_list(tmp_path, {"version": "1", "hosts": [GEMINI_HOST, "api.example.test"]})

    allow_list = load_egress_allow_list(path)

    assert allow_list == EgressAllowList("1", frozenset({GEMINI_HOST, "api.example.test"}))


@pytest.mark.parametrize(
    "document",
    [
        {"version": "1"},
        {"hosts": [GEMINI_HOST]},
        {"version": "2", "hosts": [GEMINI_HOST]},
        {"version": 1, "hosts": [GEMINI_HOST]},
        {"version": "1", "hosts": []},
        {"version": "1", "hosts": GEMINI_HOST},
        {"version": "1", "hosts": [GEMINI_HOST, GEMINI_HOST]},
        {"version": "1", "hosts": [GEMINI_HOST], "ports": [443]},
        [GEMINI_HOST],
    ],
)
def test_a_file_that_breaks_the_format_is_refused(tmp_path: Path, document: object) -> None:
    path = write_allow_list(tmp_path, document)

    with pytest.raises(EgressAllowListInvalidError) as raised:
        load_egress_allow_list(path)

    assert raised.value.file_name == ALLOW_LIST_FILE_NAME


@pytest.mark.parametrize(
    "host",
    [
        f"https://{GEMINI_HOST}",
        f"{GEMINI_HOST}:443",
        f"{GEMINI_HOST}/v1beta",
        f"{GEMINI_HOST}.",
        "*.googleapis.com",
        "GenerativeLanguage.googleapis.com",
        f" {GEMINI_HOST}",
        "203.0.113.10",
        "localhost",
        "-gemini.example.test",
        f"{'a' * 64}.example.test",
        f"{'a.' * 126}test",
        "",
    ],
)
def test_a_host_that_is_not_a_lowercase_dns_name_is_refused(tmp_path: Path, host: str) -> None:
    path = write_allow_list(tmp_path, {"version": "1", "hosts": [host]})

    with pytest.raises(EgressAllowListInvalidError):
        load_egress_allow_list(path)


@pytest.mark.parametrize("content", [b"{", b"\xff\xfe{}", b""])
def test_a_file_that_is_not_json_in_utf_8_is_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / ALLOW_LIST_FILE_NAME
    path.write_bytes(content)

    with pytest.raises(EgressAllowListInvalidError):
        load_egress_allow_list(path)


def test_a_missing_file_is_refused_and_the_error_names_only_the_file(tmp_path: Path) -> None:
    with pytest.raises(EgressAllowListInvalidError) as raised:
        load_egress_allow_list(tmp_path / ALLOW_LIST_FILE_NAME)

    assert (
        raised.value.detail
        == f"The egress allow-list {ALLOW_LIST_FILE_NAME} is missing or invalid."
    )


@pytest.mark.parametrize(
    "url",
    [
        ALLOWED_URL,
        f"https://{GEMINI_HOST}:443/v1beta/models",
        "https://GenerativeLanguage.GoogleAPIs.com/v1beta/models",
    ],
)
def test_https_on_the_default_port_to_an_allowed_host_reaches_the_network(url: str) -> None:
    network = RecordingNetwork()

    with create_egress_client(ALLOW_LIST, network) as client:
        response = client.post(url, json={})

    assert response.status_code == HTTPStatus.OK
    assert [request.url.host for request in network.requests] == [GEMINI_HOST]


@pytest.mark.parametrize(
    "url",
    [
        f"http://{GEMINI_HOST}/v1beta/models",
        f"https://{GEMINI_HOST}:8443/v1beta/models",
        f"https://evil.{GEMINI_HOST}/v1beta/models",
        f"https://{GEMINI_HOST}.evil.example.test/v1beta/models",
        "https://example.test/collect",
        "https://203.0.113.10/collect",
        "https://localhost/collect",
    ],
)
def test_every_other_request_is_refused_before_it_reaches_the_network(url: str) -> None:
    network = RecordingNetwork()

    with create_egress_client(ALLOW_LIST, network) as client, pytest.raises(EgressRefusedError):
        client.get(url)

    assert network.requests == []


def test_a_refusal_is_a_request_error_that_repeats_no_part_of_the_request() -> None:
    network = RecordingNetwork()

    with (
        create_egress_client(ALLOW_LIST, network) as client,
        pytest.raises(httpx.RequestError) as raised,
    ):
        client.get("https://example.test/collect?q=secret")

    assert isinstance(raised.value, EgressRefusedError)
    assert str(raised.value) == "The request is outside the egress allow-list."


def test_a_redirect_is_never_followed() -> None:
    network = RecordingNetwork(HTTPStatus.TEMPORARY_REDIRECT, {"Location": ALLOWED_URL})

    with create_egress_client(ALLOW_LIST, network) as client:
        response = client.post(ALLOWED_URL, json={})

    assert response.status_code == HTTPStatus.TEMPORARY_REDIRECT
    assert len(network.requests) == 1


def test_proxy_variables_of_the_environment_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(variable, "http://proxy.example.test:3128")
    network = RecordingNetwork()

    with create_egress_client(ALLOW_LIST, network) as client:
        client.post(ALLOWED_URL, json={})

    assert client.trust_env is False
    assert client.follow_redirects is False
    assert len(network.requests) == 1


def test_closing_the_client_closes_the_network() -> None:
    network = RecordingNetwork()

    create_egress_client(ALLOW_LIST, network).close()

    assert network.closed

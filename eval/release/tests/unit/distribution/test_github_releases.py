"""The GitHub client sends the token only to the first request, and maps every failure."""

import asyncio
import gzip
import secrets
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from supportiq_release.distribution.adapters import (
    REPOSITORY,
    GitHubAccess,
    GitHubUnreachableError,
    NetworkProblem,
    TokenRefusedError,
    download_asset,
    look_up_assets,
)
from supportiq_release.distribution.domain import (
    AssetState,
    ReleaseAsset,
    ReleaseProblem,
    ReleaseRefusedError,
)
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.distribution.fakes import (
    ARCHIVE_NAME,
    ASSET_ID,
    REDIRECT_ORIGIN,
    FakeGitHub,
    StreamedBody,
    github_url,
)

ARCHIVE = b"archive bytes"
ASSET = ReleaseAsset(ASSET_ID, ARCHIVE_NAME, AssetState.UPLOADED, len(ARCHIVE))


def _access(github: FakeGitHub, token: str | None = None) -> GitHubAccess:
    return GitHubAccess(
        token=None if token is None else SecretStr(token), transport=github.transport()
    )


def _download(github: FakeGitHub, destination: Path, token: str | None = None) -> None:
    asyncio.run(download_asset(_access(github, token), ASSET, destination))


def test_the_lookup_reads_every_asset_of_the_release_of_the_tag() -> None:
    github = FakeGitHub(archive=ARCHIVE)

    assets = asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert assets == (ASSET,)
    (request,) = github.requests
    assert str(request.url) == github_url(f"/repos/{REPOSITORY}/releases/tags/{RELEASE_ID}")
    assert request.headers["accept"] == "application/vnd.github+json"
    assert request.headers["user-agent"] == "supportiq-release"
    assert request.headers["x-github-api-version"] == "2026-03-10"
    assert request.headers["accept-encoding"] == "identity"


def test_a_tag_without_a_published_release_is_a_failed_check() -> None:
    github = FakeGitHub(tag_status=HTTPStatus.NOT_FOUND)

    with pytest.raises(ReleaseRefusedError) as refused:
        asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert refused.value.problem is ReleaseProblem.NOT_PUBLISHED


@pytest.mark.parametrize(
    ("status", "headers", "problem"),
    [
        (HTTPStatus.TOO_MANY_REQUESTS, {}, NetworkProblem.RATE_LIMITED),
        (HTTPStatus.FORBIDDEN, {"x-ratelimit-remaining": "0"}, NetworkProblem.RATE_LIMITED),
        (HTTPStatus.FORBIDDEN, {"x-ratelimit-remaining": "12"}, NetworkProblem.UNEXPECTED_STATUS),
        (HTTPStatus.NOT_ACCEPTABLE, {}, NetworkProblem.UNEXPECTED_STATUS),
        (HTTPStatus.INTERNAL_SERVER_ERROR, {}, NetworkProblem.SERVER_ERROR),
        (HTTPStatus.BAD_GATEWAY, {}, NetworkProblem.SERVER_ERROR),
    ],
)
def test_a_refused_or_failed_lookup_is_a_network_failure(
    status: int, headers: dict[str, str], problem: NetworkProblem
) -> None:
    github = FakeGitHub(tag_status=status, tag_headers=headers)

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert (failed.value.problem, failed.value.status) == (problem, status)


@pytest.mark.parametrize(
    ("failure", "problem"),
    [
        (httpx.ConnectError, NetworkProblem.CONNECTION_FAILED),
        (httpx.ReadTimeout, NetworkProblem.TIMED_OUT),
        (httpx.ConnectTimeout, NetworkProblem.TIMED_OUT),
    ],
)
def test_a_request_that_fails_in_transport_is_a_network_failure(
    failure: type[httpx.TransportError], problem: NetworkProblem
) -> None:
    github = FakeGitHub(failure=failure("failed"))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert failed.value.problem is problem


@pytest.mark.parametrize(
    "assets",
    [
        [{"id": "7", "name": ARCHIVE_NAME, "state": "uploaded", "size": 1}],
        [{"id": 7, "name": ARCHIVE_NAME, "state": "deleted", "size": 1}],
        [{"id": 7, "name": ARCHIVE_NAME, "state": "uploaded", "size": -1}],
        [{"id": 7, "name": ARCHIVE_NAME, "state": "uploaded", "size": True}],
        [{"id": 7, "name": None, "state": "uploaded", "size": 1}],
        ["not an object"],
    ],
)
def test_an_answer_that_is_not_a_release_is_a_network_failure(
    assets: list[dict[str, object]],
) -> None:
    github = FakeGitHub(assets=assets)

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert failed.value.problem is NetworkProblem.RESPONSE_INVALID


def test_the_download_follows_a_redirect_to_another_host_without_the_token(
    tmp_path: Path,
) -> None:
    github = FakeGitHub(archive=ARCHIVE)
    token = secrets.token_hex(16)

    _download(github, tmp_path / "archive", token)

    assert (tmp_path / "archive").read_bytes() == ARCHIVE
    first, redirected = github.requests
    assert first.headers["authorization"] == f"Bearer {token}"
    assert first.headers["accept"] == "application/octet-stream"
    assert redirected.url.host == httpx.URL(REDIRECT_ORIGIN).host
    assert "authorization" not in redirected.headers


def test_a_redirect_to_the_same_host_is_also_followed_without_the_token(tmp_path: Path) -> None:
    github = FakeGitHub(archive=ARCHIVE, redirects=[github_url("/archive/elsewhere")])

    _download(github, tmp_path / "archive", secrets.token_hex(16))

    assert "authorization" not in github.requests[1].headers


def test_a_download_answered_directly_needs_no_redirect(tmp_path: Path) -> None:
    github = FakeGitHub(archive=ARCHIVE, asset_status=HTTPStatus.OK)

    _download(github, tmp_path / "archive")

    assert (tmp_path / "archive").read_bytes() == ARCHIVE
    assert len(github.requests) == 1


def test_without_a_token_no_request_has_an_authorization_header(tmp_path: Path) -> None:
    github = FakeGitHub(archive=ARCHIVE)

    asyncio.run(look_up_assets(_access(github), RELEASE_ID))
    _download(github, tmp_path / "archive")

    assert github.requests
    assert all("authorization" not in request.headers for request in github.requests)


def test_a_redirect_to_plain_http_is_refused(tmp_path: Path) -> None:
    github = FakeGitHub(archive=ARCHIVE, redirects=["http://release-assets.example.test/archive"])

    with pytest.raises(GitHubUnreachableError) as failed:
        _download(github, tmp_path / "archive")

    assert failed.value.problem is NetworkProblem.REDIRECT_REFUSED
    assert len(github.requests) == 1


def test_three_redirects_are_followed_and_a_fourth_is_refused(tmp_path: Path) -> None:
    hops = [f"{REDIRECT_ORIGIN}/hop-{index}" for index in range(3)]
    github = FakeGitHub(archive=ARCHIVE, redirects=hops)

    _download(github, tmp_path / "three")

    longer = FakeGitHub(archive=ARCHIVE, redirects=[*hops, f"{REDIRECT_ORIGIN}/hop-3"])
    with pytest.raises(GitHubUnreachableError) as failed:
        _download(longer, tmp_path / "four")
    assert failed.value.problem is NetworkProblem.REDIRECT_REFUSED


@pytest.mark.parametrize("body", [ARCHIVE + b"more", ARCHIVE[:-1]], ids=["longer", "shorter"])
def test_a_body_of_another_length_than_the_asset_is_a_failed_check(
    tmp_path: Path, body: bytes
) -> None:
    github = FakeGitHub(archive=body)

    with pytest.raises(ReleaseRefusedError) as refused:
        _download(github, tmp_path / "archive")

    assert refused.value.problem is ReleaseProblem.DOWNLOAD_SIZE_DIFFERS


def test_a_failed_asset_request_is_a_network_failure(tmp_path: Path) -> None:
    github = FakeGitHub(archive=ARCHIVE, asset_status=HTTPStatus.SERVICE_UNAVAILABLE)

    with pytest.raises(GitHubUnreachableError) as failed:
        _download(github, tmp_path / "archive")

    assert failed.value.problem is NetworkProblem.SERVER_ERROR


@pytest.mark.parametrize(
    ("failure", "problem"),
    [
        (httpx.ReadError, NetworkProblem.CONNECTION_FAILED),
        (httpx.ReadTimeout, NetworkProblem.TIMED_OUT),
    ],
)
def test_a_body_that_breaks_off_is_a_network_failure(
    tmp_path: Path, failure: type[httpx.TransportError], problem: NetworkProblem
) -> None:
    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.OK, stream=StreamedBody(ARCHIVE, failure("dropped")))

    access = GitHubAccess(token=None, transport=httpx.MockTransport(answer))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(download_asset(access, ASSET, tmp_path / "archive"))

    assert failed.value.problem is problem


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b"\xff"], ids=["text", "list", "binary"])
def test_a_lookup_that_is_not_a_json_object_is_a_network_failure(body: bytes) -> None:
    def answer(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(HTTPStatus.OK, content=body)

    access = GitHubAccess(token=None, transport=httpx.MockTransport(answer))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(access, RELEASE_ID))

    assert failed.value.problem is NetworkProblem.RESPONSE_INVALID


def test_a_redirect_without_a_location_is_a_network_failure(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.github.com"
        return httpx.Response(HTTPStatus.FOUND)

    access = GitHubAccess(token=None, transport=httpx.MockTransport(answer))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(download_asset(access, ASSET, tmp_path / "archive"))

    assert failed.value.problem is NetworkProblem.RESPONSE_INVALID


def test_an_anonymous_401_does_not_blame_a_token() -> None:
    github = FakeGitHub(tag_status=HTTPStatus.UNAUTHORIZED)

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github), RELEASE_ID))

    assert (failed.value.problem, failed.value.status) == (
        NetworkProblem.UNEXPECTED_STATUS,
        HTTPStatus.UNAUTHORIZED,
    )


def test_a_401_after_a_redirect_does_not_blame_the_token(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        redirect = httpx.Response(HTTPStatus.FOUND, headers={"location": f"{REDIRECT_ORIGIN}/x"})
        refused = httpx.Response(HTTPStatus.UNAUTHORIZED)
        return {"api.github.com": redirect}.get(request.url.host, refused)

    access = GitHubAccess(token=SecretStr("synthetic"), transport=httpx.MockTransport(answer))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(download_asset(access, ASSET, tmp_path / "archive"))

    assert failed.value.problem is NetworkProblem.UNEXPECTED_STATUS


def test_a_refused_token_is_a_setting_to_fix_and_never_shows_the_token() -> None:
    token = secrets.token_hex(16)
    github = FakeGitHub(tag_status=HTTPStatus.UNAUTHORIZED)

    with pytest.raises(TokenRefusedError) as refused:
        asyncio.run(look_up_assets(_access(github, token), RELEASE_ID))

    assert "SUPPORTIQ_RELEASE_TOKEN" in str(refused.value)
    assert token not in str(refused.value)
    assert token not in repr(refused.value)


def test_a_refused_lookup_never_shows_the_token() -> None:
    token = secrets.token_hex(16)
    github = FakeGitHub(tag_status=HTTPStatus.FORBIDDEN)

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github, token), RELEASE_ID))

    assert token not in str(failed.value)
    assert token not in repr(failed.value)


def test_an_unreachable_github_never_shows_the_token() -> None:
    token = secrets.token_hex(16)
    github = FakeGitHub(failure=httpx.ConnectError("refused"))

    with pytest.raises(GitHubUnreachableError) as failed:
        asyncio.run(look_up_assets(_access(github, token), RELEASE_ID))

    assert token not in str(failed.value)
    assert token not in repr(failed.value)


def test_an_encoded_body_is_written_as_it_is_sent_and_counted_raw(tmp_path: Path) -> None:
    encoded = gzip.compress(ARCHIVE, mtime=0)
    asset = ReleaseAsset(ASSET_ID, ARCHIVE_NAME, AssetState.UPLOADED, len(encoded))

    def answer(_request: httpx.Request) -> httpx.Response:
        headers = {"content-encoding": "gzip"}
        return httpx.Response(HTTPStatus.OK, headers=headers, stream=StreamedBody(encoded))

    access = GitHubAccess(token=None, transport=httpx.MockTransport(answer))
    asyncio.run(download_asset(access, asset, tmp_path / "archive"))

    assert (tmp_path / "archive").read_bytes() == encoded


def test_a_failed_download_never_shows_the_token(tmp_path: Path) -> None:
    token = secrets.token_hex(16)
    github = FakeGitHub(archive=ARCHIVE + b"x")

    with pytest.raises(ReleaseRefusedError) as failed:
        _download(github, tmp_path / "archive", token)

    assert token not in str(failed.value)
    assert token not in repr(failed.value)


def test_the_access_never_shows_the_token() -> None:
    token = secrets.token_hex(16)

    assert token not in repr(_access(FakeGitHub(), token))

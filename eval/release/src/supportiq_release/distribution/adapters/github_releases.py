"""Read the GitHub Release of a release ID, and download its archive, over the GitHub REST API.

The release is `GET /repos/{owner}/{repo}/releases/tags/{tag}`, whose tag is the release ID, and
its archive is `GET /repos/{owner}/{repo}/releases/assets/{asset_id}` with
`Accept: application/octet-stream`, which answers `200` or redirects with `302` (GitHub:
Release assets). The client reads no proxy setting and no `.netrc` (`trust_env=False`) and
follows no redirect by itself. This module follows at most 3, only to `https://` URLs, and sends
the token, when there is one, only in the first request to `api.github.com`, never after a
redirect (ADR-0030, Download, statement 2). No request is retried (ERR-12): the caller runs the
command again. Every request asks for no content encoding, and the body of the archive is counted
as raw bytes, so its size is the size that GitHub states.
"""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import cast

import httpx
from pydantic import SecretStr

from supportiq_release.distribution.domain import (
    AssetState,
    ReleaseAsset,
    ReleaseProblem,
    ReleaseRefusedError,
)
from supportiq_release.errors import NetworkFailedError, ReleaseCommandError

GITHUB_API_ORIGIN = "https://api.github.com"
REPOSITORY = "ml-system-design-nhom-5/SupportIQ"
# The version of the releases page of the GitHub REST API, read on 2026-11-23.
_API_VERSION = "2026-03-10"
_USER_AGENT = "supportiq-release"
_JSON_MEDIA_TYPE = "application/vnd.github+json"
_ASSET_MEDIA_TYPE = "application/octet-stream"
_CONNECT_TIMEOUT_MS = 10_000
# Each read of the body, not the whole download, which takes minutes on a slow line.
_READ_TIMEOUT_MS = 60_000
_MILLISECONDS_PER_SECOND = 1000
_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = frozenset(
    {HTTPStatus.MOVED_PERMANENTLY, HTTPStatus.FOUND, HTTPStatus.TEMPORARY_REDIRECT}
)
_RATE_LIMIT_REMAINING = "x-ratelimit-remaining"


class NetworkProblem(StrEnum):
    """Why a request to GitHub did not give a usable answer."""

    CONNECTION_FAILED = "connection_failed"
    TIMED_OUT = "timed_out"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    UNEXPECTED_STATUS = "unexpected_status"
    RESPONSE_INVALID = "response_invalid"
    REDIRECT_REFUSED = "redirect_not_https_or_too_many"


class GitHubUnreachableError(NetworkFailedError):
    """A request to GitHub failed. The message names the problem and the status, never a header."""

    def __init__(self, problem: NetworkProblem, status: int | None = None) -> None:
        """Build the error with a message that names the problem and the HTTP status.

        Args:
            problem: Why the request failed.
            status: The HTTP status of the answer, when there was one.
        """
        where = "" if status is None else f" status={status}"
        super().__init__(f"The request to GitHub failed: {problem}.{where}")
        self.problem = problem
        self.status = status


class TokenRefusedError(ReleaseCommandError):
    """GitHub refused the token (`401`): a setting to fix, not a failure to retry (status 2)."""

    def __init__(self) -> None:
        """Build the error with a message that names the setting, never its value."""
        super().__init__(
            "GitHub refused the token: token_refused. Fix SUPPORTIQ_RELEASE_TOKEN, or unset it"
            " to download anonymously."
        )


@dataclass(frozen=True, slots=True)
class GitHubAccess:
    """How the command reaches GitHub.

    Attributes:
        token: The token of `SUPPORTIQ_RELEASE_TOKEN`, or None for an anonymous request.
        transport: The transport of the client; None for the network. Tests pass a fake.
    """

    token: SecretStr | None
    transport: httpx.AsyncBaseTransport | None = None


async def look_up_assets(access: GitHubAccess, release_id: str) -> tuple[ReleaseAsset, ...]:
    """Read the assets of the published GitHub Release whose tag is the release ID.

    Args:
        access: The token and the transport.
        release_id: The release ID, already checked against its pattern.

    Returns:
        Every asset of the release.

    Raises:
        ReleaseRefusedError: No published release has that tag (`404`).
        GitHubUnreachableError: The request failed, was rate-limited, or the answer is not a
            release.
    """
    url = f"{GITHUB_API_ORIGIN}/repos/{REPOSITORY}/releases/tags/{release_id}"
    async with _client(access) as client:
        response = await _send(client, _first_request(client, access, url, _JSON_MEDIA_TYPE))
        try:
            if response.status_code == HTTPStatus.NOT_FOUND:
                raise ReleaseRefusedError(ReleaseProblem.NOT_PUBLISHED)
            _check_ok(response)
            body = await response.aread()
        finally:
            await response.aclose()
    return _assets(body)


async def download_asset(access: GitHubAccess, asset: ReleaseAsset, destination: Path) -> None:
    """Download the content of an asset into a new file, following at most 3 redirects.

    Args:
        access: The token and the transport.
        asset: The asset, whose size bounds the download.
        destination: The new file. An existing file is never overwritten.

    Raises:
        GitHubUnreachableError: A request failed, was rate-limited, or redirected to a URL that
            is not `https://`, or more than 3 times.
        ReleaseRefusedError: The body has another length than the asset states.
        OSError: The file cannot be written.
    """
    url = f"{GITHUB_API_ORIGIN}/repos/{REPOSITORY}/releases/assets/{asset.asset_id}"
    async with _client(access) as client:
        request = _first_request(client, access, url, _ASSET_MEDIA_TYPE)
        for _hop in range(_MAX_REDIRECTS + 1):
            response = await _send(client, request)
            try:
                location = _redirect_location(response)
                if location is None:
                    _check_ok(response)
                    await _write_body(response, destination, asset.size_bytes)
                    return
            finally:
                await response.aclose()
            # Never the token after a redirect, whatever the host (ADR-0030, Download, 2).
            request = client.build_request("GET", location, headers=_headers(_ASSET_MEDIA_TYPE))
    raise GitHubUnreachableError(NetworkProblem.REDIRECT_REFUSED)


def _client(access: GitHubAccess) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        _READ_TIMEOUT_MS / _MILLISECONDS_PER_SECOND,
        connect=_CONNECT_TIMEOUT_MS / _MILLISECONDS_PER_SECOND,
    )
    return httpx.AsyncClient(
        transport=access.transport, timeout=timeout, trust_env=False, follow_redirects=False
    )


def _headers(media_type: str) -> dict[str, str]:
    # No content encoding, so the bytes received are the bytes that GitHub states the size of.
    return {
        "Accept": media_type,
        "Accept-Encoding": "identity",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": _API_VERSION,
    }


def _first_request(
    client: httpx.AsyncClient, access: GitHubAccess, url: str, media_type: str
) -> httpx.Request:
    headers = _headers(media_type)
    if access.token is not None:
        headers["Authorization"] = f"Bearer {access.token.get_secret_value()}"
    return client.build_request("GET", url, headers=headers)


async def _send(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    try:
        return await client.send(request, stream=True)
    except httpx.TimeoutException as error:
        raise GitHubUnreachableError(NetworkProblem.TIMED_OUT) from error
    except httpx.TransportError as error:
        raise GitHubUnreachableError(NetworkProblem.CONNECTION_FAILED) from error


def _redirect_location(response: httpx.Response) -> str | None:
    if response.status_code not in _REDIRECT_STATUSES:
        return None
    location = response.headers.get("location")
    if location is None:
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID, response.status_code)
    target = response.url.join(location)
    if target.scheme != "https":
        raise GitHubUnreachableError(NetworkProblem.REDIRECT_REFUSED, response.status_code)
    return str(target)


def _check_ok(response: httpx.Response) -> None:
    status = response.status_code
    if status == HTTPStatus.OK:
        return
    # Only a request that sent the token can blame it: an anonymous request, or one after a
    # redirect, which never carries the token, gets an unexpected status instead.
    if status == HTTPStatus.UNAUTHORIZED and "Authorization" in response.request.headers:
        raise TokenRefusedError
    is_rate_limited = status == HTTPStatus.TOO_MANY_REQUESTS or (
        status == HTTPStatus.FORBIDDEN and response.headers.get(_RATE_LIMIT_REMAINING) == "0"
    )
    if is_rate_limited:
        raise GitHubUnreachableError(NetworkProblem.RATE_LIMITED, status)
    if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        raise GitHubUnreachableError(NetworkProblem.SERVER_ERROR, status)
    raise GitHubUnreachableError(NetworkProblem.UNEXPECTED_STATUS, status)


async def _write_body(response: httpx.Response, destination: Path, size_bytes: int) -> None:
    written = 0
    with destination.open("xb") as file:
        try:
            # The raw bytes, never decoded, so a content encoding cannot change the size.
            async for chunk in response.aiter_raw():
                written += len(chunk)
                if written > size_bytes:
                    break
                await asyncio.to_thread(file.write, chunk)
        except httpx.TimeoutException as error:
            raise GitHubUnreachableError(NetworkProblem.TIMED_OUT) from error
        except httpx.TransportError as error:
            raise GitHubUnreachableError(NetworkProblem.CONNECTION_FAILED) from error
    if written != size_bytes:
        raise ReleaseRefusedError(ReleaseProblem.DOWNLOAD_SIZE_DIFFERS)


def _assets(body: bytes) -> tuple[ReleaseAsset, ...]:
    # The answer of GitHub is untrusted until it has the shape of a release (CODE-32). Each cast
    # below follows the isinstance check that proves it (PY-12).
    try:
        release: object = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID) from error
    if not isinstance(release, dict):
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID)
    assets = cast("Mapping[str, object]", release).get("assets")
    if not isinstance(assets, list):
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID)
    return tuple(_asset(entry) for entry in cast("list[object]", assets))


def _asset(entry: object) -> ReleaseAsset:
    if not isinstance(entry, dict):
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID)
    fields = cast("Mapping[str, object]", entry)
    asset_id, name, state, size = (fields.get(key) for key in ("id", "name", "state", "size"))
    is_valid = (
        _is_count(asset_id)
        and isinstance(name, str)
        and state in tuple(AssetState)
        and _is_count(size)
    )
    if not is_valid:
        raise GitHubUnreachableError(NetworkProblem.RESPONSE_INVALID)
    return ReleaseAsset(
        asset_id=cast("int", asset_id),
        name=cast("str", name),
        state=AssetState(cast("str", state)),
        size_bytes=cast("int", size),
    )


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

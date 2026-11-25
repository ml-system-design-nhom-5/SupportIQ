"""A published fake release, archives built at run time, and a fake GitHub that records requests.

The published release is the fake candidate of `tests/unit/candidate/fakes.py`, with a passing
gate run, published as `publish-candidate` publishes it: the release folder, and its manifest
next to the record in `releases/`. The records are named relative to the folder of the test, as
the manifest links them, so every test that uses it runs in that folder.
"""

import hashlib
import io
import json
import tarfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import httpx

from supportiq_release.distribution.adapters import (
    GITHUB_API_ORIGIN,
    REPOSITORY,
    read_published_manifest,
    write_archive,
)
from supportiq_release.gate.adapters import (
    GateRunIdentity,
    link_release,
    prepare_release,
    write_gate_record,
)
from supportiq_release.gate.domain import (
    CandidateCheck,
    CaseKind,
    CaseResult,
    CheckResult,
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
)
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.gate.fakes import SET_NAME, build_fake_candidate

RECORDS = Path("releases")
ARCHIVE_NAME = f"{RELEASE_ID}.tar.gz"
ASSET_ID = 4242
REDIRECT_ORIGIN = "https://release-assets.example.test"
TAG_PATH = f"/repos/{REPOSITORY}/releases/tags/{RELEASE_ID}"
ASSET_PATH = f"/repos/{REPOSITORY}/releases/assets/{ASSET_ID}"
_PASSED = GateOutcome(
    cases=(CaseResult("real", "ESC-04", CaseKind.REAL_MODEL, None, ()),),
    checks=tuple(CheckResult(check) for check in CandidateCheck),
    guardrails=tuple(GuardrailResult(suite, 3, 0, 0, 0) for suite in GuardrailSuite),
    llm_calls=0,
)


def publish_fake_release(base: Path) -> Path:
    """Publish the fake candidate in a folder of a test, with a passing gate run.

    Args:
        base: An empty folder, which is also the working folder of the test.

    Returns:
        The published release folder, `base/release`. The manifest of the release in git is
        `releases/fake-release-1/release-manifest.json` below `base`.
    """
    candidate = build_fake_candidate(base)
    manifest = candidate / "release-manifest.json"
    identity = GateRunIdentity(
        release_id=RELEASE_ID,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        git_commit="c" * 40,
        case_set=SET_NAME,
        cases_sha256="d" * 64,
    )
    write_gate_record(RECORDS, identity, _PASSED)
    release = base / "release"
    release.mkdir()
    link_release(RECORDS, prepare_release(candidate, RECORDS, "d" * 64, release))
    return release


def archive_of(release: Path, base: Path) -> bytes:
    """Return the archive that `pack-release` writes for the published fake release.

    Args:
        release: The published release folder.
        base: A folder of the test, for the archive file.

    Returns:
        The bytes of the archive.
    """
    published = read_published_manifest(RECORDS, RELEASE_ID)
    archive = base / ARCHIVE_NAME
    write_archive(release, ("release-manifest.json", *published.size_bytes_by_path), archive)
    return archive.read_bytes()


def tar_of(members: list[tuple[tarfile.TarInfo, bytes]]) -> bytes:
    """Return a gzip-compressed tar archive of the given members, in their order.

    Args:
        members: Each header with its content; the content of a header without data is empty.

    Returns:
        The bytes of the archive.
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        for info, content in members:
            tar.addfile(info, io.BytesIO(content) if info.isreg() else None)
    return buffer.getvalue()


def members_of(release: Path) -> list[tuple[tarfile.TarInfo, bytes]]:
    """Return every file of a release folder as a member of an archive, sorted by path.

    Args:
        release: The release folder.

    Returns:
        Each header, a regular file named by its path in the folder, with its content.
    """
    members: list[tuple[tarfile.TarInfo, bytes]] = []
    for path in sorted(item for item in release.rglob("*") if item.is_file()):
        content = path.read_bytes()
        info = tarfile.TarInfo(path.relative_to(release).as_posix())
        info.size = len(content)
        members.append((info, content))
    return members


def special_member(name: str, kind: bytes, link: str = "") -> tuple[tarfile.TarInfo, bytes]:
    """Return a member that is not a regular file: a link, a folder, or a FIFO.

    Args:
        name: The name of the member.
        kind: Its tar type, such as `tarfile.SYMTYPE`.
        link: The target of a link.

    Returns:
        The header, with empty content.
    """
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = link
    return info, b""


@dataclass
class FakeGitHub:
    """GitHub as the release download sees it, recording every request.

    Attributes:
        archive: The bytes that the asset serves.
        asset_size: The size that the release states; the length of the archive when None.
        assets: The assets of the release in place of the one archive, when not None.
        tag_status: The status of the release lookup.
        tag_headers: The headers of a lookup that does not answer `200`.
        asset_status: The status of the asset request: `302` follows `redirects`.
        redirects: The redirects of the asset, each a URL the next request goes to.
        failure: An error that every request raises, when not None.
        body_failure: An error that the body of the archive raises after its first chunk.
        requests: Every request, in order.
    """

    archive: bytes = b""
    asset_size: int | None = None
    assets: list[dict[str, object]] | None = None
    tag_status: int = HTTPStatus.OK
    asset_status: int = HTTPStatus.FOUND
    redirects: list[str] = field(default_factory=lambda: [f"{REDIRECT_ORIGIN}/archive"])
    failure: BaseException | None = None
    body_failure: type[BaseException] | None = None
    tag_headers: dict[str, str] = field(default_factory=dict[str, str])
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])

    def transport(self) -> httpx.MockTransport:
        """Return a transport that answers every request with this fake.

        Returns:
            A transport that opens no socket.
        """
        return httpx.MockTransport(self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        if request.url.path == TAG_PATH:
            return self._release()
        if request.url.path != ASSET_PATH:
            return self._hop(self.redirects.index(str(request.url)) + 1)
        if self.asset_status != HTTPStatus.FOUND:
            return httpx.Response(self.asset_status, stream=StreamedBody(self.archive))
        return self._hop(0)

    def _hop(self, index: int) -> httpx.Response:
        # The next redirect, or the archive after the last one, as a stream, as on the network.
        if index < len(self.redirects):
            return httpx.Response(HTTPStatus.FOUND, headers={"location": self.redirects[index]})
        return httpx.Response(HTTPStatus.OK, stream=StreamedBody(self.archive, self.body_failure))

    def _release(self) -> httpx.Response:
        if self.tag_status != HTTPStatus.OK:
            return httpx.Response(self.tag_status, headers=self.tag_headers)
        size = len(self.archive) if self.asset_size is None else self.asset_size
        archive = {"id": ASSET_ID, "name": ARCHIVE_NAME, "state": "uploaded", "size": size}
        assets = [archive] if self.assets is None else self.assets
        body = {"tag_name": RELEASE_ID, "draft": False, "assets": assets}
        return httpx.Response(HTTPStatus.OK, content=json.dumps(body).encode())


class StreamedBody(httpx.AsyncByteStream):
    """A body sent as a stream, as the network sends it, which can break off after its start.

    httpx reads a body given as `content` when the response is built, so its raw stream is
    consumed already; a stream keeps the raw bytes for `aiter_raw`, as a real transport does.
    """

    def __init__(
        self, content: bytes, failure: BaseException | type[BaseException] | None = None
    ) -> None:
        """Keep the content and the error that breaks it off, if any.

        Args:
            content: The bytes of the body.
            failure: An error, or its class, raised after the first chunk, such as Ctrl+C or a
                transport error; None for a whole body.
        """
        self._content = content
        self._failure = failure

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Send the body in two chunks, or the first chunk and then the error.

        Yields:
            The first eight bytes, then the rest.

        Raises:
            BaseException: The error given, after the first chunk.
        """
        yield self._content[:8]
        if self._failure is not None:
            raise self._failure
        yield self._content[8:]


def github_url(path: str) -> str:
    """Return the URL of a path of the GitHub REST API.

    Args:
        path: The path, starting with `/`.

    Returns:
        The URL on `api.github.com`.
    """
    return f"{GITHUB_API_ORIGIN}{path}"

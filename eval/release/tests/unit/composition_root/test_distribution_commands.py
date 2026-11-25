"""The release download end to end: pack, download, and check, with every exit status.

Each test runs in its own folder with the published fake release, a cache inside it, and a fake
GitHub that serves the archive that `pack-release` wrote, so no test opens a socket (TEST-16).
"""

import io
import secrets
import shutil
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path

import httpx
import pytest

from supportiq_release.composition_root import cli, distribution_commands
from supportiq_release.composition_root.exit_statuses import (
    EXIT_CHECK_FAILED,
    EXIT_DECLINED,
    EXIT_INPUT_INVALID,
    EXIT_NETWORK_FAILED,
    EXIT_SUCCESS,
)
from supportiq_release.distribution.adapters import read_published_manifest, release_cache
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.distribution.fakes import (
    ARCHIVE_NAME,
    RECORDS,
    REDIRECT_ORIGIN,
    FakeGitHub,
    members_of,
    publish_fake_release,
    special_member,
    tar_of,
)

PINNED = RECORDS / "pinned-release.txt"
MANIFEST = "release-manifest.json"


class FakeStandardInput(io.StringIO):
    """Standard input with answers, and whether it is a terminal."""

    def __init__(self, answers: str = "", *, is_terminal: bool = False) -> None:
        """Keep the answers and whether the stream is a terminal.

        Args:
            answers: The lines that the stream holds.
            is_terminal: What `isatty` answers.
        """
        super().__init__(answers)
        self.is_terminal = is_terminal

    def isatty(self) -> bool:
        """Tell whether the stream is a terminal.

        Returns:
            The value given.
        """
        return self.is_terminal


@dataclass
class Workspace:
    """The folder of one test, with its release, archive, cache, and fake GitHub."""

    root: Path
    release: Path
    archive: bytes
    cache: Path
    github: FakeGitHub

    def cache_entries(self) -> list[str]:
        """Return every entry of the cache, hidden ones too.

        Returns:
            The names, sorted.
        """
        return sorted(entry.name for entry in self.cache.iterdir())

    def serve(self, archive: bytes) -> None:
        """Serve another archive, with its own size, so the check that fails is its content.

        Args:
            archive: The bytes of the archive.
        """
        self.github.archive = archive
        self.github.asset_size = len(archive)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Workspace:
    monkeypatch.chdir(tmp_path)
    release = publish_fake_release(tmp_path)
    assert _pack(release, tmp_path / "packed", "--pin") == EXIT_SUCCESS
    archive = (tmp_path / "packed" / ARCHIVE_NAME).read_bytes()
    github = FakeGitHub(archive=archive)
    monkeypatch.setattr(distribution_commands, "github_transport", github.transport)
    cache = tmp_path / "cache"
    monkeypatch.setenv("SUPPORTIQ_RELEASE_CACHE", str(cache))
    monkeypatch.delenv("SUPPORTIQ_RELEASE_TOKEN", raising=False)
    monkeypatch.setattr("sys.stdin", FakeStandardInput())
    return Workspace(tmp_path, release, archive, cache, github)


def _pack(release: Path, output: Path, *options: str) -> int:
    arguments = ["--release-folder", str(release), "--release-records", str(RECORDS)]
    return cli.main(["pack-release", *arguments, "--output", str(output), *options])


def _download(*options: str) -> int:
    return cli.main(["download-release", "--release-records", str(RECORDS), *options])


def _check(*options: str) -> int:
    return cli.main(["check-pinned-release", "--release-records", str(RECORDS), *options])


def _members_with(
    workspace: Workspace, change: Callable[[list[tuple[tarfile.TarInfo, bytes]]], object]
) -> bytes:
    # The members of the published release, changed in place, as an archive.
    members = members_of(workspace.release)
    change(members)
    return tar_of(members)


def _index_of_a_file(members: list[tuple[tarfile.TarInfo, bytes]]) -> int:
    return next(index for index, (info, _) in enumerate(members) if info.name != MANIFEST)


def _no_free_space(_cache: Path) -> int:
    return 0


def _listing(root: Path) -> list[str]:
    # Every entry below a folder, files and folders, by its path relative to it.
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


# ----- pack-release -----


def test_pack_writes_the_archive_and_with_pin_the_pinned_file(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    status = _pack(workspace.release, workspace.root / "again", "--pin")

    size = len(workspace.archive)
    assert status == EXIT_SUCCESS
    assert (workspace.root / "again" / ARCHIVE_NAME).read_bytes() == workspace.archive
    assert PINNED.read_text() == f"release_id={RELEASE_ID}\narchive_size_bytes={size}\n"
    archive = workspace.root / "again" / ARCHIVE_NAME
    assert capsys.readouterr().out == (
        f"release_id={RELEASE_ID} archive={archive} archive_size_bytes={size}\n"
    )


def test_pack_without_pin_leaves_the_pinned_file_as_it_is(workspace: Workspace) -> None:
    PINNED.write_text("release_id=older-release\narchive_size_bytes=7\n")

    status = _pack(workspace.release, workspace.root / "again")

    assert status == EXIT_SUCCESS
    assert PINNED.read_text() == "release_id=older-release\narchive_size_bytes=7\n"


def test_pack_refuses_a_candidate_that_has_no_gate_run(workspace: Workspace) -> None:
    status = _pack(workspace.root / "candidate", workspace.root / "out")

    assert status == EXIT_INPUT_INVALID
    assert not (workspace.root / "out").exists()


def test_pack_refuses_a_folder_whose_manifest_differs_from_git(workspace: Workspace) -> None:
    in_git = RECORDS / RELEASE_ID / MANIFEST
    in_git.write_bytes(in_git.read_bytes() + b"\n")

    status = _pack(workspace.release, workspace.root / "out")

    assert status == EXIT_INPUT_INVALID
    assert not (workspace.root / "out").exists()


# ----- download-release: success -----


def test_a_download_with_yes_puts_the_pinned_release_into_the_cache_and_prints_only_its_path(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    status = _download("--yes")

    captured = capsys.readouterr()
    folder = workspace.cache / RELEASE_ID
    assert status == EXIT_SUCCESS
    assert captured.out == f"{folder}\n"
    assert f"Release {RELEASE_ID}: archive of {len(workspace.archive)} bytes" in captured.err
    assert workspace.cache_entries() == [RELEASE_ID]


def test_a_downloaded_release_holds_the_files_of_the_published_one(workspace: Workspace) -> None:
    _download("--yes")

    folder = workspace.cache / RELEASE_ID
    paths = (MANIFEST, *read_published_manifest(RECORDS, RELEASE_ID).size_bytes_by_path)
    assert _listing(folder) == _listing(workspace.release)
    assert [(folder / path).read_bytes() for path in paths] == [
        (workspace.release / path).read_bytes() for path in paths
    ]


def test_a_second_download_is_a_cache_hit_without_any_request(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    _download("--yes")
    requests = len(workspace.github.requests)
    capsys.readouterr()

    status = _download()

    assert status == EXIT_SUCCESS
    assert len(workspace.github.requests) == requests
    assert capsys.readouterr().out == f"{workspace.cache / RELEASE_ID}\n"


def test_the_answer_y_on_a_terminal_downloads_the_release(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", FakeStandardInput("y\n", is_terminal=True))

    status = _download()

    assert status == EXIT_SUCCESS
    assert "Proceed? [y/N] " in capsys.readouterr().err
    assert workspace.cache_entries() == [RELEASE_ID]


def test_without_a_cache_setting_the_cache_is_below_home(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUPPORTIQ_RELEASE_CACHE")
    monkeypatch.setenv("HOME", str(workspace.root / "home"))
    capsys.readouterr()

    status = _download("--yes")

    expected = workspace.root / "home" / ".cache" / "supportiq" / "releases" / RELEASE_ID
    assert status == EXIT_SUCCESS
    assert capsys.readouterr().out == f"{expected}\n"


def test_an_empty_token_is_no_token(workspace: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPPORTIQ_RELEASE_TOKEN", "")

    status = _download("--yes")

    assert status == EXIT_SUCCESS
    assert all("authorization" not in request.headers for request in workspace.github.requests)


def test_the_token_reaches_only_the_requests_to_github(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = secrets.token_hex(16)
    monkeypatch.setenv("SUPPORTIQ_RELEASE_TOKEN", token)

    _download("--yes")

    lookup, asset, redirected = workspace.github.requests
    assert lookup.headers["authorization"] == asset.headers["authorization"] == f"Bearer {token}"
    assert "authorization" not in redirected.headers


# ----- download-release: declined, and nothing written -----


def test_without_a_terminal_and_without_yes_the_download_stops_before_any_request(
    workspace: Workspace,
) -> None:
    status = _download()

    assert status == EXIT_DECLINED
    assert workspace.github.requests == []
    assert not workspace.cache.exists()


@pytest.mark.parametrize("answer", ["n\n", "\n", "yes\n", ""])
def test_any_answer_but_y_declines_after_the_lookup_and_creates_nothing(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    monkeypatch.setattr("sys.stdin", FakeStandardInput(answer, is_terminal=True))

    status = _download()

    assert status == EXIT_DECLINED
    assert len(workspace.github.requests) == 1
    assert not workspace.cache.exists()


def test_too_little_free_space_exits_2_before_the_download_and_creates_nothing(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(distribution_commands, "free_bytes", _no_free_space)

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert len(workspace.github.requests) == 1
    assert not workspace.cache.exists()


# ----- download-release: failures -----


def test_a_network_failure_exits_5_and_creates_nothing(workspace: Workspace) -> None:
    workspace.github.failure = httpx.ConnectError("refused")

    status = _download("--yes")

    assert status == EXIT_NETWORK_FAILED
    assert not workspace.cache.exists()


def test_a_refused_token_exits_2_and_names_the_setting(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUPPORTIQ_RELEASE_TOKEN", secrets.token_hex(16))
    workspace.github.tag_status = HTTPStatus.UNAUTHORIZED
    capsys.readouterr()

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert "token_refused" in capsys.readouterr().err


def test_an_archive_with_one_wrong_checksum_exits_6_and_leaves_nothing_in_the_cache(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    def change_one_byte(members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
        index = _index_of_a_file(members)
        info, content = members[index]
        members[index] = (info, bytes([content[0] ^ 1]) + content[1:])

    workspace.serve(_members_with(workspace, change_one_byte))
    capsys.readouterr()

    status = _download("--release", RELEASE_ID, "--yes")

    assert status == EXIT_CHECK_FAILED
    assert "checksum_mismatch" in capsys.readouterr().err
    assert workspace.cache_entries() == []


def test_an_archive_of_another_size_than_the_pinned_file_exits_6_before_the_download(
    workspace: Workspace,
) -> None:
    workspace.github.asset_size = len(workspace.archive) + 1

    status = _download("--yes")

    assert status == EXIT_CHECK_FAILED
    assert len(workspace.github.requests) == 1


def test_a_cached_folder_that_was_edited_exits_6_and_is_left_as_it_is(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copytree(workspace.release, workspace.cache / RELEASE_ID)
    extra = workspace.cache / RELEASE_ID / ".DS_Store"
    extra.write_bytes(b"x")
    capsys.readouterr()

    status = _download("--yes")

    assert status == EXIT_CHECK_FAILED
    assert "Remove that folder to download the release again" in capsys.readouterr().err
    assert extra.exists()


@pytest.mark.parametrize("release_id", ["../x", "a/b", ".x", "a" * 65])
def test_a_release_id_outside_the_pattern_exits_2_without_a_request(
    workspace: Workspace, release_id: str
) -> None:
    status = _download("--release", release_id, "--yes")

    assert status == EXIT_INPUT_INVALID
    assert workspace.github.requests == []


def test_a_release_without_a_manifest_in_git_exits_2_without_a_request(
    workspace: Workspace,
) -> None:
    status = _download("--release", "unknown-release", "--yes")

    assert status == EXIT_INPUT_INVALID
    assert workspace.github.requests == []


@pytest.mark.parametrize("cache", ["cache", "./cache", "~/cache"])
def test_a_cache_that_is_not_an_absolute_path_exits_2(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cache: str,
) -> None:
    monkeypatch.setenv("SUPPORTIQ_RELEASE_CACHE", cache)
    capsys.readouterr()

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert "SUPPORTIQ_RELEASE_CACHE" in capsys.readouterr().err
    assert workspace.github.requests == []


def test_without_a_cache_setting_and_without_home_the_download_exits_2(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUPPORTIQ_RELEASE_CACHE")
    monkeypatch.delenv("HOME", raising=False)
    capsys.readouterr()

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert "SUPPORTIQ_RELEASE_CACHE, HOME" in capsys.readouterr().err
    assert workspace.github.requests == []


def test_without_a_cache_setting_and_with_a_relative_home_the_download_exits_2(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUPPORTIQ_RELEASE_CACHE")
    monkeypatch.setenv("HOME", "relative-home")
    capsys.readouterr()

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert "SUPPORTIQ_RELEASE_CACHE, HOME" in capsys.readouterr().err
    assert workspace.github.requests == []


def test_an_archive_that_breaks_off_on_ctrl_c_leaves_no_partial_archive(
    workspace: Workspace,
) -> None:
    workspace.github.body_failure = KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _download("--yes")

    assert workspace.cache_entries() == []


def test_a_ctrl_c_while_unpacking_leaves_no_staging_folder_and_no_partial_archive(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unpack_then_interrupt(_archive: Path, _contents: object, staging: Path) -> None:
        (staging / "half-written").write_bytes(b"x")
        raise KeyboardInterrupt

    monkeypatch.setattr(release_cache, "unpack_archive", unpack_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        _download("--yes")

    assert workspace.cache_entries() == []


# ----- The token never shows, in every failure path -----


def _rate_limited_with_403(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.tag_status = HTTPStatus.FORBIDDEN
    workspace.github.tag_headers = {"x-ratelimit-remaining": "0"}


def _rate_limited_with_429(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.tag_status = HTTPStatus.TOO_MANY_REQUESTS


def _server_error(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.tag_status = HTTPStatus.INTERNAL_SERVER_ERROR


def _timeout(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.failure = httpx.ReadTimeout("slow")


def _token_refused(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.tag_status = HTTPStatus.UNAUTHORIZED


def _redirect_to_http(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.redirects = ["http://release-assets.example.test/archive"]


def _fourth_redirect(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.redirects = [f"{REDIRECT_ORIGIN}/hop-{index}" for index in range(4)]


def _longer_body(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.archive = workspace.archive + b"x"
    workspace.github.asset_size = len(workspace.archive)


def _extra_member(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    extra = tarfile.TarInfo("extra.bin")
    extra.size = 1
    workspace.serve(_members_with(workspace, lambda members: members.append((extra, b"x"))))


def _link_member(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    def replace_with_a_link(members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
        index = _index_of_a_file(members)
        members[index] = special_member(members[index][0].name, tarfile.SYMTYPE, "/etc/passwd")

    workspace.serve(_members_with(workspace, replace_with_a_link))


def _repeated_member(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.serve(_members_with(workspace, lambda members: members.append(members[0])))


def _missing_member(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.serve(_members_with(workspace, lambda members: members.pop()))


def _member_of_another_size(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    def grow(members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
        index = _index_of_a_file(members)
        info, content = members[index]
        info.size = len(content) + 1
        members[index] = (info, content + b"x")

    workspace.serve(_members_with(workspace, grow))


def _unreadable_archive(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.serve(b"not a gzip stream")


def _wrong_checksum(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    def change_one_byte(members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
        index = _index_of_a_file(members)
        info, content = members[index]
        members[index] = (info, bytes([content[0] ^ 1]) + content[1:])

    workspace.serve(_members_with(workspace, change_one_byte))


def _edited_cache(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    shutil.copytree(workspace.release, workspace.cache / RELEASE_ID)
    (workspace.cache / RELEASE_ID / ".DS_Store").write_bytes(b"x")


def _declined(_workspace: Workspace, patch: pytest.MonkeyPatch) -> None:
    patch.setattr("sys.stdin", FakeStandardInput("n\n", is_terminal=True))


def _too_little_space(_workspace: Workspace, patch: pytest.MonkeyPatch) -> None:
    patch.setattr(distribution_commands, "free_bytes", _no_free_space)


@dataclass(frozen=True)
class FailurePath:
    """One way for a download to fail, the options of the run, and the status it ends with."""

    make: Callable[[Workspace, pytest.MonkeyPatch], None]
    options: tuple[str, ...]
    status: int


YES = ("--yes",)


def _connection_error(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.failure = httpx.ConnectError("refused")


def _no_github_release(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.tag_status = HTTPStatus.NOT_FOUND


def _asset_still_uploading(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    size = len(workspace.archive)
    workspace.github.assets = [{"id": 1, "name": ARCHIVE_NAME, "state": "open", "size": size}]


def _two_assets(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    size = len(workspace.archive)
    archive: dict[str, object] = {"id": 1, "name": ARCHIVE_NAME, "state": "uploaded", "size": size}
    workspace.github.assets = [archive, {**archive, "id": 2}]


def _shorter_body(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.archive = workspace.archive[:-1]
    workspace.github.asset_size = len(workspace.archive)


def _manifest_that_differs_from_git(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    def change_one_byte_of_the_manifest(members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
        index = next(i for i, (info, _) in enumerate(members) if info.name == MANIFEST)
        info, content = members[index]
        members[index] = (info, content.replace(b"\n", b" ", 1))

    workspace.serve(_members_with(workspace, change_one_byte_of_the_manifest))


def _pinned_size_differs(workspace: Workspace, _patch: pytest.MonkeyPatch) -> None:
    workspace.github.asset_size = len(workspace.archive) + 1


# Every path names its release with --release, except the one of the size of the pinned file.
CHOSEN = ("--release", RELEASE_ID)
FAILURE_PATHS = [
    FailurePath(_rate_limited_with_403, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_rate_limited_with_429, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_server_error, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_timeout, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_connection_error, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_token_refused, (*CHOSEN, *YES), EXIT_INPUT_INVALID),
    FailurePath(_no_github_release, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_asset_still_uploading, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_two_assets, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_redirect_to_http, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_fourth_redirect, (*CHOSEN, *YES), EXIT_NETWORK_FAILED),
    FailurePath(_longer_body, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_shorter_body, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_extra_member, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_link_member, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_repeated_member, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_missing_member, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_member_of_another_size, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_unreadable_archive, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_wrong_checksum, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_manifest_that_differs_from_git, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_edited_cache, (*CHOSEN, *YES), EXIT_CHECK_FAILED),
    FailurePath(_declined, CHOSEN, EXIT_DECLINED),
    FailurePath(_too_little_space, (*CHOSEN, *YES), EXIT_INPUT_INVALID),
    FailurePath(_pinned_size_differs, YES, EXIT_CHECK_FAILED),
]


@pytest.mark.parametrize(
    "failure", FAILURE_PATHS, ids=[path.make.__name__.lstrip("_") for path in FAILURE_PATHS]
)
def test_no_failure_path_shows_the_token(
    workspace: Workspace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    failure: FailurePath,
) -> None:
    token = secrets.token_hex(16)
    monkeypatch.setenv("SUPPORTIQ_RELEASE_TOKEN", token)
    failure.make(workspace, monkeypatch)
    capsys.readouterr()

    status = _download(*failure.options)

    captured = capsys.readouterr()
    assert status == failure.status
    assert token not in captured.out + captured.err + caplog.text


# ----- check-pinned-release -----


def test_the_check_of_the_pinned_file_passes_without_a_request(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    status = _check()

    assert status == EXIT_SUCCESS
    assert "github=not checked" in capsys.readouterr().out
    assert workspace.github.requests == []


def test_the_remote_check_of_the_pinned_file_passes_against_github(
    workspace: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()

    status = _check("--remote")

    assert status == EXIT_SUCCESS
    assert "github=checked" in capsys.readouterr().out
    assert len(workspace.github.requests) == 1


def test_the_remote_check_ignores_a_cache_setting_that_it_never_uses(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUPPORTIQ_RELEASE_CACHE", "relative-cache")

    status = _check("--remote")

    assert status == EXIT_SUCCESS
    assert len(workspace.github.requests) == 1


def test_the_remote_check_needs_no_home(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPPORTIQ_RELEASE_CACHE")
    monkeypatch.setenv("HOME", "relative-home")

    status = _check("--remote")

    assert status == EXIT_SUCCESS
    assert len(workspace.github.requests) == 1


@pytest.mark.parametrize(
    "assets",
    [
        [],
        [
            {"id": 1, "name": ARCHIVE_NAME, "state": "uploaded", "size": 1},
            {"id": 2, "name": ARCHIVE_NAME, "state": "uploaded", "size": 1},
        ],
        [{"id": 1, "name": "other.zip", "state": "uploaded", "size": 1}],
    ],
    ids=["no-asset", "two-assets", "another-asset"],
)
def test_the_remote_check_fails_without_exactly_the_one_archive(
    workspace: Workspace, assets: list[dict[str, object]]
) -> None:
    workspace.github.assets = assets

    status = _check("--remote")

    assert status == EXIT_CHECK_FAILED


def test_the_remote_check_fails_on_another_size(workspace: Workspace) -> None:
    workspace.github.asset_size = len(workspace.archive) - 1

    status = _check("--remote")

    assert status == EXIT_CHECK_FAILED


def test_the_remote_check_fails_without_a_github_release(workspace: Workspace) -> None:
    workspace.github.tag_status = HTTPStatus.NOT_FOUND

    status = _check("--remote")

    assert status == EXIT_CHECK_FAILED


def test_the_remote_check_exits_5_when_github_cannot_be_reached(workspace: Workspace) -> None:
    workspace.github.failure = httpx.ConnectError("refused")

    status = _check("--remote")

    assert status == EXIT_NETWORK_FAILED


BROKEN_PINNED_FILES = [
    "release_id=fake-release-1\r\narchive_size_bytes=1\r\n",
    "release_id=unknown\narchive_size_bytes=1\n",
    "release_id=fake-release-1\narchive_size_bytes=" + "9" * 4300 + "\n",
]
BROKEN_IDS = ["crlf", "no-manifest-in-git", "4300-digits"]


@pytest.mark.parametrize("text", BROKEN_PINNED_FILES, ids=BROKEN_IDS)
def test_a_pinned_file_that_breaks_its_rules_fails_the_check_without_a_request(
    workspace: Workspace, text: str
) -> None:
    PINNED.write_text(text)

    status = _check("--remote")

    assert status == EXIT_CHECK_FAILED
    assert workspace.github.requests == []


@pytest.mark.parametrize("text", BROKEN_PINNED_FILES, ids=BROKEN_IDS)
def test_a_pinned_file_that_breaks_its_rules_stops_the_download_with_status_2(
    workspace: Workspace, text: str
) -> None:
    PINNED.write_text(text)

    status = _download("--yes")

    assert status == EXIT_INPUT_INVALID
    assert workspace.github.requests == []

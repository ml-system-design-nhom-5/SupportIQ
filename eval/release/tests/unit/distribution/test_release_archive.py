"""An archive of a release has the same bytes every time, and unpacking refuses bad members."""

import io
import os
import tarfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest

from supportiq_release.distribution.adapters import (
    FILE_MODE,
    FOLDER_MODE,
    PackRefusedError,
    read_published_manifest,
    unpack_archive,
    write_archive,
)
from supportiq_release.distribution.domain import ArchiveProblem, ArchiveRefusedError
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.distribution.fakes import (
    RECORDS,
    archive_of,
    members_of,
    publish_fake_release,
    special_member,
    tar_of,
)

_GZIP_FLAG_FILE_NAME = 0x08


@pytest.fixture
def release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return publish_fake_release(tmp_path)


@pytest.fixture
def staging(tmp_path: Path) -> Path:
    folder = tmp_path / "staging"
    folder.mkdir()
    return folder


@pytest.fixture
def strict_umask() -> Iterator[None]:
    # The umask of a user who shares nothing, restored after the test.
    previous = os.umask(0o077)
    yield
    os.umask(previous)


def _unpack(tmp_path: Path, archive: bytes, staging: Path) -> None:
    path = tmp_path / "archive.tar.gz"
    path.write_bytes(archive)
    unpack_archive(path, read_published_manifest(RECORDS, RELEASE_ID).contents(), staging)


def _files(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in folder.rglob("*")
        if path.is_file()
    }


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_two_archives_of_one_release_have_the_same_bytes(release: Path, tmp_path: Path) -> None:
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    second.mkdir()

    assert archive_of(release, first) == archive_of(release, second)


def test_the_archive_holds_sorted_regular_files_without_owner_or_time(
    release: Path, tmp_path: Path
) -> None:
    archive = archive_of(release, tmp_path)

    # The gzip header (RFC 1952): no file name in FLG, and MTIME 0.
    assert archive[3] & _GZIP_FLAG_FILE_NAME == 0
    assert archive[4:8] == bytes(4)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = tar.getmembers()
    assert [member.name for member in members] == sorted(_files(release))
    assert {
        (member.isreg(), member.mode, member.mtime, member.uid, member.gid, member.uname)
        for member in members
    } == {(True, FILE_MODE, 0, 0, 0, "")}
    assert {member.gname for member in members} == {""}


def test_a_path_longer_than_ustar_allows_stops_the_archive(tmp_path: Path) -> None:
    long_path = "/".join(["a" * 90] * 3)
    source = tmp_path / long_path
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x")

    with pytest.raises(PackRefusedError):
        write_archive(tmp_path, (long_path,), tmp_path / "archive.tar.gz")


@pytest.mark.usefixtures("strict_umask")
def test_a_full_and_correct_archive_unpacks_to_the_same_files_with_fixed_modes(
    release: Path, tmp_path: Path, staging: Path
) -> None:
    _unpack(tmp_path, archive_of(release, tmp_path), staging)

    files = _files(release)
    folders = {PurePosixPath(path).parent for path in files} - {PurePosixPath()}
    assert _files(staging) == files
    assert {_mode(staging / path) for path in files} == {FILE_MODE}
    assert {_mode(staging / folder) for folder in folders} | {_mode(staging)} == {FOLDER_MODE}


@pytest.mark.parametrize(
    "name", ["../escape.txt", "/etc/escape.txt", "./release-manifest.json", "extra.bin"]
)
def test_a_member_that_the_manifest_does_not_name_is_refused(
    release: Path, tmp_path: Path, staging: Path, name: str
) -> None:
    extra = tarfile.TarInfo(name)
    extra.size = 1
    members = [*members_of(release), (extra, b"x")]

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, tar_of(members), staging)

    assert refused.value.problem is ArchiveProblem.MEMBER_NOT_ALLOWED
    assert not (tmp_path / "escape.txt").exists()
    assert not Path("/etc/escape.txt").exists()


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE]
)
def test_a_member_that_is_not_a_regular_file_is_refused(
    release: Path, tmp_path: Path, staging: Path, kind: bytes
) -> None:
    members = members_of(release)
    name = members[0][0].name
    members[0] = special_member(name, kind, link="/etc/passwd")

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, tar_of(members), staging)

    assert refused.value.problem is ArchiveProblem.MEMBER_NOT_A_REGULAR_FILE
    assert not (staging / name).exists()


def test_a_member_twice_is_refused(release: Path, tmp_path: Path, staging: Path) -> None:
    members = members_of(release)

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, tar_of([*members, members[0]]), staging)

    assert refused.value.problem is ArchiveProblem.MEMBER_REPEATED


def test_a_missing_member_is_refused(release: Path, tmp_path: Path, staging: Path) -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, tar_of(members_of(release)[1:]), staging)

    assert refused.value.problem is ArchiveProblem.MEMBER_MISSING


def test_a_member_larger_than_the_manifest_is_refused_before_it_is_written(
    release: Path, tmp_path: Path, staging: Path
) -> None:
    members = members_of(release)
    info, content = members[0]
    info.size = len(content) + 1
    members[0] = (info, content + b"x")

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, tar_of(members), staging)

    assert refused.value.problem is ArchiveProblem.MEMBER_SIZE_DIFFERS
    assert not (staging / info.name).exists()


@pytest.mark.parametrize("archive", [b"not a gzip stream", b""], ids=["garbage", "empty"])
def test_an_archive_that_cannot_be_read_is_refused(
    tmp_path: Path, staging: Path, release: Path, archive: bytes
) -> None:
    assert release.is_dir()

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, archive, staging)

    assert refused.value.problem is ArchiveProblem.UNREADABLE


def test_a_truncated_archive_is_refused(release: Path, tmp_path: Path, staging: Path) -> None:
    archive = archive_of(release, tmp_path)

    with pytest.raises(ArchiveRefusedError) as refused:
        _unpack(tmp_path, archive[: len(archive) // 2], staging)

    assert refused.value.problem in {ArchiveProblem.UNREADABLE, ArchiveProblem.MEMBER_MISSING}

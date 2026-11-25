"""A cached release is the published one exactly, and only a whole check installs one."""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from supportiq_release.distribution.adapters import (
    FILE_MODE,
    CachedReleaseInvalidError,
    CachedReleaseProblem,
    PublishedProblem,
    ReleaseFilesRefusedError,
    ReleaseNotPublishedError,
    check_cached_release,
    free_bytes,
    install_release,
    is_cached,
    new_partial_archive,
    read_pinned_release,
    read_published_manifest,
    write_pinned_release,
)
from supportiq_release.distribution.domain import (
    ArchiveProblem,
    ArchiveRefusedError,
    PinnedRelease,
    PinnedReleaseInvalidError,
    PinnedReleaseProblem,
)
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.distribution.fakes import (
    RECORDS,
    archive_of,
    members_of,
    publish_fake_release,
    tar_of,
)


@pytest.fixture
def release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return publish_fake_release(tmp_path)


def test_the_published_release_passes_as_a_cached_folder(release: Path) -> None:
    check_cached_release(release, read_published_manifest(RECORDS, RELEASE_ID))


def test_a_cached_folder_with_an_extra_file_is_refused_and_left_as_it_is(release: Path) -> None:
    (release / ".DS_Store").write_bytes(b"x")

    with pytest.raises(CachedReleaseInvalidError) as refused:
        check_cached_release(release, read_published_manifest(RECORDS, RELEASE_ID))

    assert refused.value.problem is CachedReleaseProblem.REFUSED_BY_VERIFY_RELEASE
    assert "file_unlisted" in str(refused.value)
    assert str(release) in str(refused.value)
    assert (release / ".DS_Store").exists()


def test_a_cached_file_with_one_byte_changed_is_refused(release: Path) -> None:
    published = read_published_manifest(RECORDS, RELEASE_ID)
    changed = release / next(iter(published.size_bytes_by_path))
    content = changed.read_bytes()
    changed.write_bytes(bytes([content[0] ^ 1]) + content[1:])

    with pytest.raises(CachedReleaseInvalidError) as refused:
        check_cached_release(release, published)

    assert "checksum_mismatch" in str(refused.value)


def test_a_cached_manifest_that_differs_from_git_is_refused(release: Path) -> None:
    published = read_published_manifest(RECORDS, RELEASE_ID)
    manifest = release / "release-manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")

    with pytest.raises(CachedReleaseInvalidError) as refused:
        check_cached_release(release, published)

    assert refused.value.problem is CachedReleaseProblem.MANIFEST_DIFFERS_FROM_GIT


def _a_file(cached: Path, _release: Path) -> None:
    cached.write_bytes(b"x")


def _a_link(cached: Path, release: Path) -> None:
    cached.symlink_to(release, target_is_directory=True)


def _an_empty_folder(cached: Path, _release: Path) -> None:
    cached.mkdir()


@pytest.mark.parametrize(
    ("make_entry", "problem"),
    [
        (_a_file, CachedReleaseProblem.NOT_A_FOLDER),
        (_a_link, CachedReleaseProblem.NOT_A_FOLDER),
        (_an_empty_folder, CachedReleaseProblem.MANIFEST_UNREADABLE),
    ],
    ids=["file", "link", "empty-folder"],
)
def test_a_cache_entry_that_is_not_a_release_folder_is_refused(
    release: Path,
    tmp_path: Path,
    make_entry: Callable[[Path, Path], None],
    problem: CachedReleaseProblem,
) -> None:
    cached = tmp_path / "cached"
    make_entry(cached, release)

    with pytest.raises(CachedReleaseInvalidError) as refused:
        check_cached_release(cached, read_published_manifest(RECORDS, RELEASE_ID))

    assert refused.value.problem is problem
    assert is_cached(cached)


def test_an_archive_that_passes_every_check_is_renamed_into_the_cache(
    release: Path, tmp_path: Path
) -> None:
    packed = tmp_path / "packed"
    packed.mkdir()
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(archive_of(release, packed))
    cached = tmp_path / "cache" / RELEASE_ID
    cached.parent.mkdir()

    install_release(archive, read_published_manifest(RECORDS, RELEASE_ID), cached)

    check_cached_release(cached, read_published_manifest(RECORDS, RELEASE_ID))
    assert [entry.name for entry in cached.parent.iterdir()] == [RELEASE_ID]


def test_an_archive_with_another_manifest_leaves_nothing_in_the_cache(
    release: Path, tmp_path: Path
) -> None:
    members = members_of(release)
    index = next(i for i, (info, _) in enumerate(members) if info.name == "release-manifest.json")
    info, content = members[index]
    members[index] = (info, content.replace(b"\n", b" ", 1))
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(tar_of(members))
    cache = tmp_path / "cache"
    cache.mkdir()

    with pytest.raises(ArchiveRefusedError) as refused:
        install_release(archive, read_published_manifest(RECORDS, RELEASE_ID), cache / RELEASE_ID)

    assert refused.value.problem is ArchiveProblem.MANIFEST_DIFFERS_FROM_GIT
    assert list(cache.iterdir()) == []


def test_an_archive_with_one_wrong_checksum_leaves_nothing_in_the_cache(
    release: Path, tmp_path: Path
) -> None:
    members = members_of(release)
    index = next(i for i, (info, _) in enumerate(members) if info.name != "release-manifest.json")
    info, content = members[index]
    members[index] = (info, bytes([content[0] ^ 1]) + content[1:])
    archive = tmp_path / "archive.tar.gz"
    archive.write_bytes(tar_of(members))
    cache = tmp_path / "cache"
    cache.mkdir()

    with pytest.raises(ReleaseFilesRefusedError) as refused:
        install_release(archive, read_published_manifest(RECORDS, RELEASE_ID), cache / RELEASE_ID)

    assert "checksum_mismatch" in str(refused.value)
    assert list(cache.iterdir()) == []


def test_a_partial_archive_is_a_hidden_new_entry_of_the_cache(tmp_path: Path) -> None:
    first = new_partial_archive(tmp_path, RELEASE_ID)
    second = new_partial_archive(tmp_path, RELEASE_ID)

    assert first.parent == tmp_path
    assert first.name.startswith(f".{RELEASE_ID}.tar.gz.partial-")
    assert first != second
    assert not first.exists()


def test_a_release_without_a_published_manifest_is_named_as_such(release: Path) -> None:
    assert release.is_dir()

    with pytest.raises(ReleaseNotPublishedError) as refused:
        read_published_manifest(RECORDS, "other-release")

    assert refused.value.problem is PublishedProblem.MISSING


def test_a_candidate_manifest_in_the_records_is_not_published(release: Path) -> None:
    candidate = (Path("candidate") / "release-manifest.json").read_bytes()
    (RECORDS / RELEASE_ID / "release-manifest.json").write_bytes(candidate)
    assert release.is_dir()

    with pytest.raises(ReleaseNotPublishedError) as refused:
        read_published_manifest(RECORDS, RELEASE_ID)

    assert refused.value.problem is PublishedProblem.NOT_PUBLISHED


def test_a_manifest_of_another_release_id_is_refused(release: Path) -> None:
    other = RECORDS / "other-release"
    other.mkdir()
    (other / "release-manifest.json").write_bytes((release / "release-manifest.json").read_bytes())

    with pytest.raises(ReleaseNotPublishedError) as refused:
        read_published_manifest(RECORDS, "other-release")

    assert refused.value.problem is PublishedProblem.OTHER_RELEASE


def test_a_manifest_that_breaks_its_format_is_refused(release: Path) -> None:
    (RECORDS / RELEASE_ID / "release-manifest.json").write_text("{}")
    assert release.is_dir()

    with pytest.raises(ReleaseNotPublishedError) as refused:
        read_published_manifest(RECORDS, RELEASE_ID)

    assert refused.value.problem is PublishedProblem.INVALID


def test_the_pinned_file_is_written_and_read_back(tmp_path: Path) -> None:
    pinned = PinnedRelease(RELEASE_ID, 1234)

    path = write_pinned_release(tmp_path, pinned)

    assert path.read_text() == f"release_id={RELEASE_ID}\narchive_size_bytes=1234\n"
    assert read_pinned_release(tmp_path) == pinned
    assert path.stat().st_mode & 0o777 == FILE_MODE
    assert [entry.name for entry in tmp_path.iterdir()] == ["pinned-release.txt"]


def test_a_failed_write_of_the_pinned_file_keeps_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_pinned_release(tmp_path, PinnedRelease(RELEASE_ID, 1234))

    def fail(_self: Path, _target: Path) -> Path:
        raise OSError

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match=r"^$"):
        write_pinned_release(tmp_path, PinnedRelease("other-release", 99))

    monkeypatch.undo()
    assert read_pinned_release(tmp_path) == PinnedRelease(RELEASE_ID, 1234)
    assert [entry.name for entry in tmp_path.iterdir()] == ["pinned-release.txt"]


def test_a_missing_pinned_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PinnedReleaseInvalidError) as refused:
        read_pinned_release(tmp_path)

    assert refused.value.problem is PinnedReleaseProblem.UNREADABLE


def test_a_pinned_file_that_is_not_ascii_is_refused(tmp_path: Path) -> None:
    (tmp_path / "pinned-release.txt").write_bytes(b"\xff\xfe")

    with pytest.raises(PinnedReleaseInvalidError) as refused:
        read_pinned_release(tmp_path)

    assert refused.value.problem is PinnedReleaseProblem.NOT_TWO_LINES


@dataclass(frozen=True, slots=True)
class _Usage:
    # The one field of the result of `shutil.disk_usage` that `free_bytes` reads.
    free: int


FREE = 123_456_789


@pytest.mark.parametrize(
    ("cache", "existing", "measured"),
    [
        (("cache",), ("cache",), ("cache",)),
        (("not", "yet", "cache"), (), ()),
        (("not", "yet", "cache"), ("not",), ("not",)),
    ],
    ids=["the-cache-exists", "no-folder-of-the-cache-exists", "a-parent-of-the-cache-exists"],
)
def test_the_free_space_is_that_of_the_cache_or_its_nearest_existing_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cache: tuple[str, ...],
    existing: tuple[str, ...],
    measured: tuple[str, ...],
) -> None:
    # A fake disk usage: the free space of the real file system changes while other tests, in
    # other workers, write to it, so two readings of it may differ (TEST-14).
    asked: list[Path] = []

    def disk_usage(path: Path) -> _Usage:
        asked.append(path)
        return _Usage(free=FREE)

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    tmp_path.joinpath(*existing).mkdir(parents=True, exist_ok=True)

    space = free_bytes(tmp_path.joinpath(*cache))

    assert space == FREE
    assert asked == [tmp_path.joinpath(*measured)]
    # Measuring creates nothing: only the folders that the test made exist.
    assert {path.relative_to(tmp_path).parts for path in tmp_path.rglob("*")} == (
        {existing} if existing else set()
    )

"""An archive holds the manifest and every file it names, each once, as a file of its size."""

import pytest

from supportiq_release.distribution.domain import (
    ArchiveContents,
    ArchiveProblem,
    ArchiveRefusedError,
    MemberType,
    NotEnoughSpaceError,
    archive_contents,
    archive_name,
    mebibytes,
)

CONTENTS = archive_contents(100, {"model/config.json": 7, "kb/kb.json": 3})
REGULAR = MemberType.REGULAR_FILE


def test_the_allowed_members_are_the_manifest_and_every_file_it_names() -> None:
    expected = {"model/config.json": 7, "kb/kb.json": 3, "release-manifest.json": 100}

    assert ArchiveContents(expected) == CONTENTS


def test_a_member_named_by_the_manifest_with_its_size_passes() -> None:
    CONTENTS.check_member("kb/kb.json", REGULAR, 3, frozenset())


@pytest.mark.parametrize(
    "name",
    ["../kb/kb.json", "/kb/kb.json", "./kb/kb.json", "kb//kb.json", "kb/KB.json", "other.bin"],
)
def test_a_member_that_the_manifest_does_not_name_is_refused_without_its_name(name: str) -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        CONTENTS.check_member(name, REGULAR, 3, frozenset())

    assert refused.value.problem is ArchiveProblem.MEMBER_NOT_ALLOWED
    assert refused.value.member is None
    assert name not in str(refused.value)


def test_a_member_that_is_not_a_regular_file_is_refused() -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        CONTENTS.check_member("kb/kb.json", MemberType.OTHER, 0, frozenset())

    assert refused.value.problem is ArchiveProblem.MEMBER_NOT_A_REGULAR_FILE


def test_a_member_read_twice_is_refused() -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        CONTENTS.check_member("kb/kb.json", REGULAR, 3, frozenset({"kb/kb.json"}))

    assert refused.value.problem is ArchiveProblem.MEMBER_REPEATED


@pytest.mark.parametrize("size", [2, 4])
def test_a_member_of_another_size_than_the_manifest_is_refused(size: int) -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        CONTENTS.check_member("kb/kb.json", REGULAR, size, frozenset())

    assert refused.value.problem is ArchiveProblem.MEMBER_SIZE_DIFFERS
    assert refused.value.member == "kb/kb.json"


def test_an_archive_with_every_member_is_complete() -> None:
    CONTENTS.check_complete(frozenset(CONTENTS.size_bytes_by_path))


def test_a_missing_member_is_named_in_the_refusal() -> None:
    with pytest.raises(ArchiveRefusedError) as refused:
        CONTENTS.check_complete(frozenset({"release-manifest.json", "kb/kb.json"}))

    assert refused.value.problem is ArchiveProblem.MEMBER_MISSING
    assert refused.value.member == "model/config.json"


def test_the_cache_needs_room_for_the_archive_and_every_file_at_once() -> None:
    CONTENTS.check_free_space(50, 160)

    with pytest.raises(NotEnoughSpaceError) as refused:
        CONTENTS.check_free_space(51, 160)

    assert (refused.value.needed_bytes, refused.value.free_bytes) == (161, 160)


def test_the_archive_is_named_after_the_release_id() -> None:
    assert archive_name("release-2026-11-18-02") == "release-2026-11-18-02.tar.gz"


@pytest.mark.parametrize(("size", "mib"), [(0, 0), (1, 1), (1024 * 1024, 1), (1024 * 1024 + 1, 2)])
def test_a_size_in_mebibytes_is_rounded_up(size: int, mib: int) -> None:
    assert mebibytes(size) == mib

"""A release ID is given only once, even to a candidate that fails the gate (ARCH-40)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from supportiq_release.candidate.adapters.release_records import (
    ReleaseIdNotFreeError,
    ReleaseIdProblem,
    check_release_id_free,
)

RELEASE_ID = "fake-release-1"


def test_an_id_without_a_record_is_free(tmp_path: Path) -> None:
    (tmp_path / "fake-release-0").mkdir()

    check_release_id_free(tmp_path, RELEASE_ID)


def _record_folder(path: Path) -> None:
    path.mkdir()


def _record_file(path: Path) -> None:
    path.write_text("a record")


def _record_link(path: Path) -> None:
    path.symlink_to(path.parent / "elsewhere")


@pytest.mark.parametrize("make_record", [_record_folder, _record_file, _record_link])
def test_an_id_with_any_entry_of_its_name_is_used(
    tmp_path: Path, make_record: Callable[[Path], None]
) -> None:
    make_record(tmp_path / RELEASE_ID)

    with pytest.raises(ReleaseIdNotFreeError) as refused:
        check_release_id_free(tmp_path, RELEASE_ID)

    assert refused.value.problem is ReleaseIdProblem.ALREADY_USED


def _nothing(path: Path) -> None:
    del path


@pytest.mark.parametrize("make_records", [_nothing, _record_file, _record_link])
def test_a_missing_folder_of_records_never_lets_an_id_through(
    tmp_path: Path, make_records: Callable[[Path], None]
) -> None:
    records = tmp_path / "records"
    make_records(records)

    with pytest.raises(ReleaseIdNotFreeError) as refused:
        check_release_id_free(records, RELEASE_ID)

    assert refused.value.problem is ReleaseIdProblem.RECORDS_MISSING

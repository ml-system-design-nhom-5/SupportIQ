"""The GitHub Release of a release ID has exactly one uploaded asset, its archive."""

import pytest

from supportiq_release.distribution.domain import (
    AssetState,
    ReleaseAsset,
    ReleaseIdInvalidError,
    ReleaseProblem,
    ReleaseRefusedError,
    archive_asset,
    check_pinned_size,
    checked_release_id,
)

ARCHIVE = ReleaseAsset(7, "fake-release-1.tar.gz", AssetState.UPLOADED, 1234)


def test_a_release_id_of_the_contract_pattern_is_kept() -> None:
    assert checked_release_id("release-2026-11-18-02") == "release-2026-11-18-02"


@pytest.mark.parametrize("text", ["../x", "a/b", ".x", "a" * 65, "", "a b", "-x"])
def test_a_release_id_outside_the_contract_pattern_is_refused(text: str) -> None:
    with pytest.raises(ReleaseIdInvalidError) as refused:
        checked_release_id(text)

    # The message names the pattern, never the value.
    assert str(refused.value) == str(ReleaseIdInvalidError())


def test_the_one_uploaded_archive_is_the_asset_of_the_release() -> None:
    assert archive_asset("fake-release-1", (ARCHIVE,)) == ARCHIVE


@pytest.mark.parametrize("count", [0, 2])
def test_a_release_without_exactly_one_asset_is_refused(count: int) -> None:
    with pytest.raises(ReleaseRefusedError) as refused:
        archive_asset("fake-release-1", (ARCHIVE,) * count)

    assert refused.value.problem is ReleaseProblem.NOT_ONE_ASSET


def test_an_asset_of_another_name_is_refused() -> None:
    other = ReleaseAsset(7, "fake-release-1.zip", AssetState.UPLOADED, 1234)

    with pytest.raises(ReleaseRefusedError) as refused:
        archive_asset("fake-release-1", (other,))

    assert refused.value.problem is ReleaseProblem.NOT_THE_ARCHIVE


def test_an_asset_whose_upload_is_not_finished_is_refused() -> None:
    open_asset = ReleaseAsset(7, "fake-release-1.tar.gz", AssetState.OPEN, 1234)

    with pytest.raises(ReleaseRefusedError) as refused:
        archive_asset("fake-release-1", (open_asset,))

    assert refused.value.problem is ReleaseProblem.NOT_UPLOADED


def test_the_archive_must_have_the_size_of_the_pinned_file() -> None:
    check_pinned_size(ARCHIVE, 1234)

    with pytest.raises(ReleaseRefusedError) as refused:
        check_pinned_size(ARCHIVE, 1235)

    assert refused.value.problem is ReleaseProblem.SIZE_DIFFERS_FROM_THE_PINNED_FILE

"""The asset versions and readiness come from the loaded release only (DATA-56, ERR-18)."""

import pytest

from app.platform import CheckReadiness
from app.release import (
    GetAssetVersions,
    ReleaseNotLoadedError,
    ReleaseReadinessProbe,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS, StaticReleaseSource


def test_the_asset_versions_are_those_of_the_loaded_release() -> None:
    assert GetAssetVersions(StaticReleaseSource()).execute() == EXAMPLE_VERSIONS


def test_without_a_loaded_release_there_are_no_asset_versions() -> None:
    with pytest.raises(ReleaseNotLoadedError):
        GetAssetVersions(StaticReleaseSource(release=None)).execute()


def test_an_instance_with_a_loaded_release_is_ready() -> None:
    CheckReadiness((ReleaseReadinessProbe(StaticReleaseSource()),)).execute()


def test_an_instance_without_a_loaded_release_is_not_ready() -> None:
    probe = ReleaseReadinessProbe(StaticReleaseSource(release=None))

    with pytest.raises(ReleaseNotLoadedError):
        CheckReadiness((probe,)).execute()

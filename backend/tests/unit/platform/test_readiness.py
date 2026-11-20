"""Tests of the readiness use case behind `GET /health/ready` (ERR-18)."""

import pytest

from app.platform import CheckReadiness, DatabaseUnavailableError
from tests.unit.platform.fakes import FakeReadinessProbe

pytestmark = pytest.mark.anyio


async def test_check_readiness_checks_every_probe_once() -> None:
    database_probe, other_probe = FakeReadinessProbe(), FakeReadinessProbe()

    await CheckReadiness((database_probe, other_probe)).execute()

    assert (database_probe.check_count, other_probe.check_count) == (1, 1)


async def test_check_readiness_fails_when_the_database_does_not_answer() -> None:
    use_case = CheckReadiness((FakeReadinessProbe(DatabaseUnavailableError()),))

    with pytest.raises(DatabaseUnavailableError):
        await use_case.execute()

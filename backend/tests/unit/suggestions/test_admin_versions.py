"""Tests of `GetAdminVersions` with a fake ai-service (TEST-01, ERR-21, SEC-41).

Only an admin reads the versions in use, and the role check comes before the read of
ai-service. When ai-service cannot answer, the build version of backend is still returned, and
the failure is recorded once, at the level that tells a defect from degradation (LOG-15). The
call runs in its own span (LOG-20).
"""

import pytest

from supportiq_backend.accounts import (
    AccountId,
    Authorizer,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    Principal,
)
from supportiq_backend.platform import (
    EVENT_DESCRIPTIONS,
    BackendError,
    EventLevel,
    EventName,
    SpanName,
)
from supportiq_backend.suggestions import (
    AiServiceContractError,
    AiServiceReadPorts,
    AiServiceUnavailableError,
    GetAdminVersions,
    VersionsInUse,
)
from tests.unit.platform.fakes import RecordingEventRecorder, RecordingStepTracer
from tests.unit.suggestions.builders import STAFF_ACCOUNT_ID, build_versions
from tests.unit.suggestions.fakes import FakeAiService

pytestmark = pytest.mark.anyio

BUILD_VERSION = "880b33a"
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)
CUSTOMER = CustomerPrincipal(
    AccountId("00000000-0000-4000-8000-0000000000cc"),
    CustomerId("00000000-0000-4000-8000-0000000000c1"),
)
STAFF = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)
MANAGER = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.MANAGER)


def build_read(
    ai_service: FakeAiService, steps: RecordingStepTracer | None = None
) -> tuple[GetAdminVersions, RecordingEventRecorder]:
    events = RecordingEventRecorder()
    ports = AiServiceReadPorts(
        authorizer=Authorizer(events),
        ai_service=ai_service,
        events=events,
        steps=steps or RecordingStepTracer(),
    )
    return GetAdminVersions(ports, BUILD_VERSION), events


async def test_an_admin_gets_the_build_version_and_the_versions_of_ai_service() -> None:
    read, events = build_read(FakeAiService())

    versions = await read.execute(ADMIN)

    assert versions == VersionsInUse(BUILD_VERSION, build_versions())
    assert events.names() == ()


async def test_the_read_of_ai_service_runs_in_a_span_that_names_the_operation() -> None:
    steps = RecordingStepTracer()
    read, _ = build_read(FakeAiService(), steps)

    await read.execute(ADMIN)

    assert steps.steps == [SpanName.CALL_AI_SERVICE]
    assert steps.ai_service_endpoints == ["getAssetVersions"]


@pytest.mark.parametrize(
    ("principal", "role"), [(CUSTOMER, "customer"), (STAFF, "staff"), (MANAGER, "manager")]
)
async def test_other_roles_may_not_read_the_versions_and_ai_service_is_not_read(
    principal: Principal, role: str
) -> None:
    ai_service = FakeAiService()
    read, events = build_read(ai_service)

    with pytest.raises(ForbiddenRoleError):
        await read.execute(principal)

    (denied,) = events.events
    assert denied.name is EventName.PERMISSION_DENIED
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "getAdminVersions",
    }
    assert ai_service.version_reads == 0


@pytest.mark.parametrize(
    ("failure", "event", "level"),
    [
        (AiServiceUnavailableError(), EventName.AI_SERVICE_CALL_FAILED, EventLevel.WARNING),
        (AiServiceContractError(), EventName.AI_SERVICE_CONTRACT_VIOLATED, EventLevel.ERROR),
    ],
    ids=["unavailable", "contract-violated"],
)
async def test_a_failed_read_returns_only_the_build_version_and_is_recorded_once(
    failure: BackendError, event: EventName, level: EventLevel
) -> None:
    ai_service = FakeAiService(versions=failure)
    read, events = build_read(ai_service)

    versions = await read.execute(ADMIN)

    (recorded,) = events.events
    assert versions == VersionsInUse(BUILD_VERSION, None)
    assert ai_service.version_reads == 1
    assert recorded.name is event
    assert recorded.attributes == {"ai_service_operation": "getAssetVersions"}
    assert EVENT_DESCRIPTIONS[recorded.name].level is level

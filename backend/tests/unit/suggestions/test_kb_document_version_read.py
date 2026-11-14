"""Tests of `GetConsoleKbDocumentVersion` with a fake ai-service (TEST-01, ERR-21, SEC-41).

Only staff and managers read a KB document version. A `404` of ai-service is a refusal, so
it records nothing; a failure of ai-service is recorded once, by the side that handles it
(ERR-05).
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
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.platform import (
    EVENT_DESCRIPTIONS,
    EventLevel,
    EventName,
    UnexpectedFailureError,
)
from supportiq_backend.suggestions import (
    AiServiceContractError,
    AiServiceReadPorts,
    AiServiceUnavailableError,
    GetConsoleKbDocumentVersion,
    KbDocumentVersionNotFoundError,
)
from tests.unit.platform.fakes import RecordingEventRecorder
from tests.unit.suggestions.builders import (
    DOCUMENT_ID,
    DOCUMENT_VERSION,
    STAFF_ACCOUNT_ID,
    build_kb_document_version,
)
from tests.unit.suggestions.fakes import FakeAiService

pytestmark = pytest.mark.anyio

SUPPORT = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
CUSTOMER = CustomerPrincipal(
    AccountId("00000000-0000-4000-8000-0000000000cc"),
    CustomerId("00000000-0000-4000-8000-0000000000c1"),
)
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)


def build_read(
    ai_service: FakeAiService,
) -> tuple[GetConsoleKbDocumentVersion, RecordingEventRecorder]:
    events = RecordingEventRecorder()
    ports = AiServiceReadPorts(authorizer=Authorizer(events), ai_service=ai_service, events=events)
    return GetConsoleKbDocumentVersion(ports), events


@pytest.mark.parametrize("role", [InternalRole.STAFF, InternalRole.MANAGER])
async def test_staff_and_managers_may_read_a_kb_document_version(role: InternalRole) -> None:
    read, events = build_read(FakeAiService())

    support = read.authorize(InternalPrincipal(STAFF_ACCOUNT_ID, role))

    assert support == SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole(role.value))
    assert events.names() == ()


@pytest.mark.parametrize(("principal", "role"), [(CUSTOMER, "customer"), (ADMIN, "admin")])
async def test_customers_and_admins_may_not_read_a_kb_document_version(
    principal: Principal, role: str
) -> None:
    read, events = build_read(FakeAiService())

    with pytest.raises(ForbiddenRoleError):
        read.authorize(principal)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "getConsoleKbDocumentVersion",
    }


async def test_read_returns_the_version_that_ai_service_serves_without_an_event() -> None:
    document = build_kb_document_version()
    ai_service = FakeAiService(kb_document_version=document)
    read, events = build_read(ai_service)

    received = await read.execute(SUPPORT, DOCUMENT_ID, DOCUMENT_VERSION)

    assert received == document
    assert ai_service.kb_document_reads == [(DOCUMENT_ID, DOCUMENT_VERSION)]
    assert events.names() == ()


async def test_a_version_that_ai_service_does_not_know_is_not_found_without_an_event() -> None:
    read, events = build_read(FakeAiService(kb_document_version=None))

    with pytest.raises(KbDocumentVersionNotFoundError):
        await read.execute(SUPPORT, DOCUMENT_ID, DOCUMENT_VERSION)

    assert events.names() == ()


async def test_an_unavailable_ai_service_is_recorded_once_at_warning_and_raised() -> None:
    failure = AiServiceUnavailableError()
    read, events = build_read(FakeAiService(kb_document_version=failure))

    with pytest.raises(AiServiceUnavailableError) as caught:
        await read.execute(SUPPORT, DOCUMENT_ID, DOCUMENT_VERSION)

    (recorded,) = events.events
    assert caught.value is failure
    assert recorded.name is EventName.AI_SERVICE_CALL_FAILED
    assert recorded.attributes == {"ai_service_operation": "getKbDocumentVersion"}
    assert EVENT_DESCRIPTIONS[recorded.name].level is EventLevel.WARNING


async def test_a_contract_error_becomes_an_unexpected_failure_that_the_handler_records() -> None:
    violation = AiServiceContractError()
    read, events = build_read(FakeAiService(kb_document_version=violation))

    with pytest.raises(UnexpectedFailureError) as caught:
        await read.execute(SUPPORT, DOCUMENT_ID, DOCUMENT_VERSION)

    assert caught.value.__cause__ is violation
    assert events.names() == ()

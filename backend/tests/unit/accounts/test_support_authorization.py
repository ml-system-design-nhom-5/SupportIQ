"""Tests of the role checks of the console: `require_support` and `require_manager` (SEC-41).

Only staff and managers reach a console operation, and only managers reach the queues and the
reports that are theirs alone (ADR-0012). Every refusal is one `permission.denied` event.
"""

import pytest

from supportiq_backend.accounts import (
    AccountId,
    Authorizer,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    OperationId,
    Principal,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.platform import EventName
from tests.unit.accounts.fakes import CUSTOMER_ACCOUNT_ID, CUSTOMER_ID, STAFF_ACCOUNT_ID
from tests.unit.platform.fakes import RecordingEventRecorder

ADMIN_ACCOUNT_ID = AccountId("00000000-0000-0000-0000-0000000000ad")
CUSTOMER = CustomerPrincipal(CUSTOMER_ACCOUNT_ID, CUSTOMER_ID)
STAFF = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.STAFF)
MANAGER = InternalPrincipal(STAFF_ACCOUNT_ID, InternalRole.MANAGER)
ADMIN = InternalPrincipal(ADMIN_ACCOUNT_ID, InternalRole.ADMIN)


@pytest.mark.parametrize(
    ("principal", "role"), [(STAFF, SupportRole.STAFF), (MANAGER, SupportRole.MANAGER)]
)
def test_require_support_returns_staff_and_managers_without_an_event(
    principal: Principal, role: SupportRole
) -> None:
    events = RecordingEventRecorder()

    support = Authorizer(events).require_support(principal, OperationId.GET_CONSOLE_TICKET)

    assert support == SupportPrincipal(STAFF_ACCOUNT_ID, role)
    assert events.names() == ()


@pytest.mark.parametrize(("principal", "role"), [(CUSTOMER, "customer"), (ADMIN, "admin")])
def test_require_support_refuses_customers_and_admins_and_records_the_refusal(
    principal: Principal, role: str
) -> None:
    events = RecordingEventRecorder()

    with pytest.raises(ForbiddenRoleError):
        Authorizer(events).require_support(principal, OperationId.SEND_REPLY)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "sendReply",
    }


def test_require_manager_returns_a_manager_without_an_event() -> None:
    events = RecordingEventRecorder()

    manager = Authorizer(events).require_manager(MANAGER, OperationId.LIST_CONSOLE_TICKETS)

    assert manager == SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.MANAGER)
    assert events.names() == ()


@pytest.mark.parametrize(
    ("principal", "role"), [(CUSTOMER, "customer"), (STAFF, "staff"), (ADMIN, "admin")]
)
def test_require_manager_refuses_every_other_role_with_one_event(
    principal: Principal, role: str
) -> None:
    events = RecordingEventRecorder()

    with pytest.raises(ForbiddenRoleError):
        Authorizer(events).require_manager(principal, OperationId.LIST_CONSOLE_TICKETS)

    (denied,) = events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "listConsoleTickets",
    }

"""Authorization of a use case: deny by default, in the application layer (SEC-16, ADR-0012)."""

from typing import assert_never

from supportiq_backend.accounts.domain.errors import ForbiddenRoleError
from supportiq_backend.accounts.domain.identity import (
    AdminPrincipal,
    CustomerPrincipal,
    InternalPrincipal,
    InternalRole,
    Principal,
    Role,
)
from supportiq_backend.platform import EventName, EventRecorder, OperationId


class Authorizer:
    """Check the role of a principal; every refusal is logged as `permission.denied`."""

    def __init__(self, events: EventRecorder) -> None:
        """Keep the event recorder.

        Args:
            events: Where refusals are recorded.
        """
        self._events = events

    def require_customer(self, principal: Principal, operation: OperationId) -> CustomerPrincipal:
        """Allow only a customer, for the operations of `/v1/shop/`.

        Args:
            principal: The caller.
            operation: The operation, for the event.

        Returns:
            The caller as a customer, with the `customer_id` that filters every query.

        Raises:
            ForbiddenRoleError: The caller is not a customer.
        """
        if isinstance(principal, CustomerPrincipal):
            return principal
        raise self._denied(principal, operation)

    def require_admin(self, principal: Principal, operation: OperationId) -> AdminPrincipal:
        """Allow only an admin, for the operations of `/v1/admin/`.

        Args:
            principal: The caller.
            operation: The operation, for the event.

        Returns:
            The caller as an admin.

        Raises:
            ForbiddenRoleError: The caller is not an admin.
        """
        if isinstance(principal, InternalPrincipal) and principal.role is InternalRole.ADMIN:
            return AdminPrincipal(principal.account_id)
        raise self._denied(principal, operation)

    def _denied(self, principal: Principal, operation: OperationId) -> ForbiddenRoleError:
        self._events.record(
            EventName.PERMISSION_DENIED,
            account_id=principal.account_id,
            role=_role_of(principal),
            operation_id=operation.value,
        )
        return ForbiddenRoleError()


def _role_of(principal: Principal) -> str:
    match principal:
        case CustomerPrincipal():
            return Role.CUSTOMER.value
        case InternalPrincipal():
            return principal.role.value
        case _:
            assert_never(principal)

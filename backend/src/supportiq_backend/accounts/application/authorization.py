"""Authorization of a use case: deny by default, in the application layer (SEC-16, ADR-0012)."""

from typing import assert_never

from supportiq_backend.accounts.domain.errors import ForbiddenRoleError, SessionRequiredError
from supportiq_backend.accounts.domain.identity import (
    AdminPrincipal,
    CustomerPrincipal,
    InternalPrincipal,
    InternalRole,
    Principal,
    Role,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.accounts.domain.ports import InternalAccountStore
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

    def require_support(self, principal: Principal, operation: OperationId) -> SupportPrincipal:
        """Allow only staff and managers, for the operations of `/v1/console/` (SEC-41).

        Args:
            principal: The caller.
            operation: The operation, for the event.

        Returns:
            The caller as a member of support.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
        """
        if isinstance(principal, InternalPrincipal) and principal.role is not InternalRole.ADMIN:
            return SupportPrincipal(principal.account_id, SupportRole(principal.role.value))
        raise self._denied(principal, operation)

    def require_manager(
        self, principal: Principal | SupportPrincipal, operation: OperationId
    ) -> SupportPrincipal:
        """Allow only managers, for the reports and the queues that only they see (ADR-0012).

        Args:
            principal: The caller; a console use case passes it as the member of support
                that `require_support` returned.
            operation: The operation, for the event.

        Returns:
            The caller as a manager.

        Raises:
            ForbiddenRoleError: The caller is not a manager.
        """
        support = (
            principal
            if isinstance(principal, SupportPrincipal)
            else self.require_support(principal, operation)
        )
        if support.role is SupportRole.MANAGER:
            return support
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

    def _denied(
        self, principal: Principal | SupportPrincipal, operation: OperationId
    ) -> ForbiddenRoleError:
        self._events.record(
            EventName.PERMISSION_DENIED,
            account_id=principal.account_id,
            role=_role_of(principal),
            operation_id=operation.value,
        )
        return ForbiddenRoleError()


async def require_active_admin(accounts: InternalAccountStore, admin: AdminPrincipal) -> None:
    """Reload the caller of an admin change after the advisory lock of account changes.

    A change that committed while this request waited for the lock may have deactivated the
    caller, whose session it deleted, so an admin deactivated by another cannot still act.

    Args:
        accounts: The store bound to the transaction that holds the lock.
        admin: The caller, whose role check passed before the lock.

    Raises:
        SessionRequiredError: The caller is no longer an active admin.
    """
    caller = await accounts.load_internal(admin.account_id)
    if caller is None or not caller.is_active or caller.role is not InternalRole.ADMIN:
        raise SessionRequiredError


def _role_of(principal: Principal | SupportPrincipal) -> str:
    match principal:
        case CustomerPrincipal():
            return Role.CUSTOMER.value
        case InternalPrincipal() | SupportPrincipal():
            return principal.role.value
        case _:
            assert_never(principal)

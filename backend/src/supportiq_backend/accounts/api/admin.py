"""The admin operations: `listAdminAccounts`, `changeAccountRole`, `changeAccountStatus`."""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from supportiq_backend.accounts.api.dependencies import CurrentSession, OriginCheck
from supportiq_backend.accounts.application import ChangeAccount, ListAdminAccounts
from supportiq_backend.accounts.domain import (
    AccountId,
    AccountPage,
    AssignableRole,
    AuthenticatedSession,
    InternalAccount,
    OperationId,
    RoleChange,
    StatusChange,
)
from supportiq_backend.generated import (
    AdminAccountPage,
    AdminAccountView,
    ChangeAccountRoleRequest,
    ChangeAccountStatusRequest,
    Cursor,
    InternalAccountRole,
)
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform.web import (
    IDEMPOTENCY_KEY_HEADER,
    decode_cursor,
    encode_cursor,
    json_response,
    parse_json_body,
    parse_limit,
    provide,
    render_json,
    stored_json_response,
)

LIST_OPERATION = OperationId.LIST_ADMIN_ACCOUNTS.value
CURSOR_ACCOUNT_FIELD = "account_id"


@dataclass(frozen=True, slots=True)
class AdminRoutes:
    """What the admin routes need from the composition root.

    Attributes:
        list_accounts: The list use case.
        change_account: The change use case.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
    """

    list_accounts: ListAdminAccounts
    change_account: ChangeAccount
    check_origin: OriginCheck
    current_session: CurrentSession


def to_admin_account_view(account: InternalAccount) -> AdminAccountView:
    """Map an internal account to the contract: no email, hash, or session data (ADR-0012).

    Args:
        account: The account.

    Returns:
        The contract model.
    """
    return AdminAccountView(
        account_id=account.account_id,
        display_name=account.display_name,
        role=InternalAccountRole(account.role.value),
        is_active=account.is_active,
    )


def render_changed_account(account: InternalAccount) -> StoredResponse:
    """Write the `201` response of a change, the one that every repeat returns.

    Args:
        account: The account after the change.

    Returns:
        The status and the exact body text.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_admin_account_view(account)))


def to_account_page(page: AccountPage) -> AdminAccountPage:
    """Map a page of accounts to the contract.

    Args:
        page: The page.

    Returns:
        The contract model; `next_cursor` is absent on the last page.
    """
    next_cursor = None
    if page.next_after is not None:
        next_cursor = Cursor(encode_cursor(LIST_OPERATION, {CURSOR_ACCOUNT_FIELD: page.next_after}))
    return AdminAccountPage(
        items=[to_admin_account_view(account) for account in page.items],
        next_cursor=next_cursor,
    )


def parse_account_cursor(raw: str | None) -> AccountId | None:
    """Read the cursor of `listAdminAccounts`: the last account of the previous page.

    Args:
        raw: The `cursor` query parameter, or None when absent.

    Returns:
        The account, or None for the first page.

    Raises:
        InvalidCursorError: The cursor is malformed or from another operation.
    """
    fields = decode_cursor(raw, LIST_OPERATION, frozenset({CURSOR_ACCOUNT_FIELD}))
    return None if fields is None else AccountId(fields.text(CURSOR_ACCOUNT_FIELD))


def build_admin_router(routes: AdminRoutes) -> APIRouter:
    """Build the router of the admin operations.

    The role check runs before the request is parsed, so a caller with another role gets
    `403` whatever it sent (contract, Authentication and roles).

    Args:
        routes: The use cases and dependencies.

    Returns:
        The router.
    """
    router = APIRouter()
    _add_list_route(router, routes)
    _add_change_routes(router, routes)
    return router


def _add_list_route(router: APIRouter, routes: AdminRoutes) -> None:
    current_session = Depends(routes.current_session)
    list_accounts = Depends(provide(routes.list_accounts))

    @router.get("/v1/admin/accounts", status_code=HTTPStatus.OK)
    async def handle_list_admin_accounts(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ListAdminAccounts, list_accounts],
        limit: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
    ) -> Response:
        admin = use_case.require_admin(session.principal)
        page = await use_case.execute(admin, parse_account_cursor(cursor), parse_limit(limit))
        return json_response(to_account_page(page))


def _add_change_routes(router: APIRouter, routes: AdminRoutes) -> None:
    check_origin = Depends(routes.check_origin)
    current_session = Depends(routes.current_session)
    change_account = Depends(provide(routes.change_account))

    @router.post(
        "/v1/admin/accounts/{account_id}/role-changes",
        status_code=HTTPStatus.CREATED,
        dependencies=[check_origin],
    )
    async def handle_change_account_role(
        account_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ChangeAccount, change_account],
    ) -> Response:
        admin = use_case.require_admin(session.principal, OperationId.CHANGE_ACCOUNT_ROLE)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, ChangeAccountRoleRequest)
        change = RoleChange(AccountId(account_id), AssignableRole(body.role.value))
        stored = await use_case.execute(admin, change, key)
        return stored_json_response(stored.status_code, stored.body)

    @router.post(
        "/v1/admin/accounts/{account_id}/status-changes",
        status_code=HTTPStatus.CREATED,
        dependencies=[check_origin],
    )
    async def handle_change_account_status(
        account_id: str,
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ChangeAccount, change_account],
    ) -> Response:
        admin = use_case.require_admin(session.principal, OperationId.CHANGE_ACCOUNT_STATUS)
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, ChangeAccountStatusRequest)
        change = StatusChange(AccountId(account_id), body.is_active)
        stored = await use_case.execute(admin, change, key)
        return stored_json_response(stored.status_code, stored.body)

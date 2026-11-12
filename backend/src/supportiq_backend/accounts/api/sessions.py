"""The session operations of every role (ADR-0009, ADR-0015).

They are `createSession`, `getCurrentSession`, `changeOwnPassword`, and `deleteCurrentSession`.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from supportiq_backend.accounts.api.dependencies import (
    SESSION_COOKIE_NAME,
    CurrentSession,
    OriginCheck,
)
from supportiq_backend.accounts.application import ChangeOwnPassword, SignIn, SignOut
from supportiq_backend.accounts.domain import (
    AuthenticatedSession,
    Credentials,
    OwnPasswordChange,
    Password,
    SessionAccount,
)
from supportiq_backend.generated import (
    AccountRole,
    ChangeOwnPasswordRequest,
    CreateSessionRequest,
    SessionView,
)
from supportiq_backend.generated import Password as PasswordField
from supportiq_backend.idempotency import StoredResponse, parse_idempotency_key
from supportiq_backend.platform.web import (
    IDEMPOTENCY_KEY_HEADER,
    json_response,
    parse_json_body,
    provide,
    render_json,
    stored_json_response,
)


@dataclass(frozen=True, slots=True)
class SessionRoutes:
    """What the session routes need from the composition root.

    Attributes:
        sign_in: The sign-in use case.
        sign_out: The sign-out use case.
        change_own_password: The own password change.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
        is_cookie_secure: The `session_cookie_secure` setting.
    """

    sign_in: SignIn
    sign_out: SignOut
    change_own_password: ChangeOwnPassword
    check_origin: OriginCheck
    current_session: CurrentSession
    is_cookie_secure: bool


def to_session_view(account: SessionAccount) -> SessionView:
    """Map the account of a session to the contract.

    Args:
        account: The account.

    Returns:
        The contract model.
    """
    return SessionView(
        account_id=account.account_id,
        display_name=account.display_name,
        role=AccountRole(account.role.value),
    )


def render_changed_password(account: SessionAccount) -> StoredResponse:
    """Write the `201` response of an own password change, the one that every repeat returns.

    Args:
        account: The caller's account.

    Returns:
        The status and the exact body text, which holds no password.
    """
    return StoredResponse(HTTPStatus.CREATED.value, render_json(to_session_view(account)))


def to_password(field: PasswordField) -> Password:
    """Map a password field of the contract to the domain, exactly as it was sent.

    Args:
        field: The field of a request body.

    Returns:
        The password.
    """
    return Password(field.root.get_secret_value())


def build_session_router(routes: SessionRoutes) -> APIRouter:
    """Build the router of the session operations.

    Args:
        routes: The use cases and dependencies.

    Returns:
        The router.
    """
    router = APIRouter()
    check_origin = Depends(routes.check_origin)
    current_session = Depends(routes.current_session)
    sign_in = Depends(provide(routes.sign_in))
    sign_out = Depends(provide(routes.sign_out))

    @router.post("/v1/sessions", status_code=HTTPStatus.CREATED, dependencies=[check_origin])
    async def handle_create_session(
        request: Request, use_case: Annotated[SignIn, sign_in]
    ) -> Response:
        body = await parse_json_body(request, CreateSessionRequest)
        signed_in = await use_case.execute(
            Credentials(body.login_name, Password(body.password.get_secret_value()))
        )
        response = json_response(to_session_view(signed_in.account), status=HTTPStatus.CREATED)
        # No Max-Age and no Expires: backend enforces the lifetime (contract `SessionCookie`).
        response.set_cookie(
            SESSION_COOKIE_NAME,
            signed_in.token.value,
            httponly=True,
            samesite="strict",
            secure=routes.is_cookie_secure,
            path="/",
        )
        return response

    @router.get("/v1/sessions/current", status_code=HTTPStatus.OK)
    async def handle_get_current_session(
        session: Annotated[AuthenticatedSession, current_session],
    ) -> Response:
        return json_response(to_session_view(session.account))

    @router.delete(
        "/v1/sessions/current", status_code=HTTPStatus.NO_CONTENT, dependencies=[check_origin]
    )
    async def handle_delete_current_session(
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[SignOut, sign_out],
    ) -> Response:
        await use_case.execute(session)
        return Response(status_code=HTTPStatus.NO_CONTENT)

    _add_password_change_route(router, routes)
    return router


def _add_password_change_route(router: APIRouter, routes: SessionRoutes) -> None:
    check_origin = Depends(routes.check_origin)
    current_session = Depends(routes.current_session)
    change_own_password = Depends(provide(routes.change_own_password))

    # Every role may call it, so the route checks no role (ADR-0015, Own password).
    @router.post(
        "/v1/sessions/current/password-changes",
        status_code=HTTPStatus.CREATED,
        dependencies=[check_origin],
    )
    async def handle_change_own_password(
        request: Request,
        session: Annotated[AuthenticatedSession, current_session],
        use_case: Annotated[ChangeOwnPassword, change_own_password],
    ) -> Response:
        key = parse_idempotency_key(request.headers.get(IDEMPOTENCY_KEY_HEADER))
        body = await parse_json_body(request, ChangeOwnPasswordRequest)
        change = OwnPasswordChange(
            current_password=to_password(body.current_password),
            new_password=to_password(body.new_password),
            is_signed_out_elsewhere=body.is_signed_out_elsewhere,
        )
        stored = await use_case.execute(session, change, key)
        return stored_json_response(stored.status_code, stored.body)

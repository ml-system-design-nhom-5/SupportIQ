"""The wiring of accounts: adapters, use cases, and routers (ARCH-21)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounts import (
    AccountChangePorts,
    AuthenticateSession,
    Authorizer,
    ChangeAccount,
    ChangeOwnPassword,
    CreateAccount,
    ListAdminAccounts,
    OriginPolicy,
    OwnPasswordChangePorts,
    ResetAccountPassword,
    SessionPolicy,
    SignIn,
    SignInPorts,
    SignInRules,
    SignOut,
    ThrottlePolicy,
)
from app.accounts.adapters.credentials import (
    Argon2Passwords,
    RandomSessionTokens,
    create_dummy_password_hash,
)
from app.accounts.adapters.internal_accounts import PostgresInternalAccountStore
from app.accounts.adapters.session_store import PostgresSessionStore
from app.accounts.api.admin import (
    AdminRoutes,
    build_admin_router,
    render_changed_account,
)
from app.accounts.api.dependencies import (
    CurrentSession,
    OriginCheck,
    build_current_session,
    build_origin_check,
)
from app.accounts.api.sessions import (
    SessionRoutes,
    build_session_router,
    render_changed_password,
)
from app.composition_root.accounts_stores import (
    build_account_change_stores,
    build_account_creation_stores,
    build_own_password_change_stores,
    build_password_reset_stores,
    build_sign_in_stores,
)
from app.composition_root.shared_ports import SharedPorts
from app.platform.adapters.database import SqlAlchemyTransactionRunner
from app.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class AccountsWiring:
    """What the other features and the application need from accounts.

    Attributes:
        routers: The routers of accounts.
        authorizer: The role checks of the use cases.
        check_origin: The `Origin` check of state-changing routes.
        current_session: The session of a request.
    """

    routers: tuple[APIRouter, ...]
    authorizer: Authorizer
    check_origin: OriginCheck
    current_session: CurrentSession


@dataclass(frozen=True, slots=True)
class _AccountsResources:
    # What every use case of accounts is built from. One Argon2id adapter serves sign-in and
    # every write that sets a password.
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    shared: SharedPorts
    passwords: Argon2Passwords
    authorizer: Authorizer

    def runner[StoresT](
        self, build_stores: Callable[[AsyncSession], StoresT]
    ) -> SqlAlchemyTransactionRunner[StoresT]:
        return SqlAlchemyTransactionRunner(self.session_factory, build_stores)


def build_session_policy(settings: Settings) -> SessionPolicy:
    """Collect the session settings (ADR-0009, statement 6).

    Args:
        settings: The validated settings.

    Returns:
        The session policy.
    """
    return SessionPolicy(
        idle_timeout=timedelta(milliseconds=settings.session_idle_timeout_ms),
        absolute_lifetime=timedelta(milliseconds=settings.session_absolute_lifetime_ms),
        touch_interval=timedelta(milliseconds=settings.session_touch_interval_ms),
    )


def build_throttle_policy(settings: Settings) -> ThrottlePolicy:
    """Collect the sign-in throttle settings (ADR-0009, statement 8).

    Args:
        settings: The validated settings.

    Returns:
        The throttle policy.
    """
    return ThrottlePolicy(
        failure_limit=settings.sign_in_failure_limit,
        failure_window=timedelta(milliseconds=settings.sign_in_failure_window_ms),
        delay_ms=settings.sign_in_failure_delay_ms,
    )


def wire_accounts(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
) -> AccountsWiring:
    """Create the adapters and the use cases of accounts.

    Args:
        settings: The validated settings.
        session_factory: The session factory of the replicas.
        shared: The ports that every feature uses.

    Returns:
        The routers and the dependencies that other features need.
    """
    resources = _AccountsResources(
        settings, session_factory, shared, Argon2Passwords(), Authorizer(shared.events)
    )
    session_transactions = resources.runner(PostgresSessionStore)
    current_session = build_current_session(
        AuthenticateSession(session_transactions, shared.clock, build_session_policy(settings))
    )
    check_origin = build_origin_check(OriginPolicy(frozenset(settings.allowed_origins)))
    session_router = build_session_router(
        SessionRoutes(
            sign_in=_build_sign_in(resources),
            sign_out=SignOut(session_transactions),
            change_own_password=_build_change_own_password(resources),
            check_origin=check_origin,
            current_session=current_session,
            is_cookie_secure=settings.session_cookie_secure,
        )
    )
    admin_router = build_admin_router(_build_admin_routes(resources, check_origin, current_session))
    return AccountsWiring(
        routers=(session_router, admin_router),
        authorizer=resources.authorizer,
        check_origin=check_origin,
        current_session=current_session,
    )


def _build_sign_in(resources: _AccountsResources) -> SignIn:
    return SignIn(
        resources.runner(build_sign_in_stores),
        SignInPorts(
            resources.passwords,
            RandomSessionTokens(),
            resources.shared.clock,
            resources.shared.events,
        ),
        SignInRules(
            sessions=build_session_policy(resources.settings),
            throttle=build_throttle_policy(resources.settings),
            dummy_password_hash=create_dummy_password_hash(resources.passwords),
        ),
    )


def _build_change_own_password(resources: _AccountsResources) -> ChangeOwnPassword:
    shared = resources.shared
    return ChangeOwnPassword(
        resources.runner(build_own_password_change_stores),
        OwnPasswordChangePorts(
            hasher=resources.passwords,
            verifier=resources.passwords,
            guard=shared.guard,
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
        ),
        build_throttle_policy(resources.settings),
        render_changed_password,
    )


def _build_admin_routes(
    resources: _AccountsResources, check_origin: OriginCheck, current_session: CurrentSession
) -> AdminRoutes:
    ports = _build_account_change_ports(resources)
    return AdminRoutes(
        list_accounts=ListAdminAccounts(
            resources.runner(PostgresInternalAccountStore), resources.authorizer
        ),
        change_account=ChangeAccount(
            resources.runner(build_account_change_stores), ports, render_changed_account
        ),
        create_account=CreateAccount(
            resources.runner(build_account_creation_stores),
            ports,
            resources.passwords,
            render_changed_account,
        ),
        reset_password=ResetAccountPassword(
            resources.runner(build_password_reset_stores),
            ports,
            resources.passwords,
            render_changed_account,
        ),
        check_origin=check_origin,
        current_session=current_session,
    )


def _build_account_change_ports(resources: _AccountsResources) -> AccountChangePorts:
    shared = resources.shared
    return AccountChangePorts(
        guard=shared.guard,
        authorizer=resources.authorizer,
        clock=shared.clock,
        ids=shared.ids,
        traces=shared.traces,
        events=shared.events,
    )

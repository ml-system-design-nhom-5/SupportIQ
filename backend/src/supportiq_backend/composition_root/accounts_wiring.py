"""The wiring of accounts: adapters, use cases, and routers (ARCH-21)."""

from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from supportiq_backend.accounts import (
    AccountChangePorts,
    AccountChangeStores,
    AuthenticateSession,
    Authorizer,
    ChangeAccount,
    ListAdminAccounts,
    OriginPolicy,
    SessionPolicy,
    SignIn,
    SignInPorts,
    SignInRules,
    SignInStores,
    SignOut,
    ThrottlePolicy,
)
from supportiq_backend.accounts.adapters.account_store import PostgresAccountStore
from supportiq_backend.accounts.adapters.credentials import (
    Argon2Passwords,
    RandomSessionTokens,
    create_dummy_password_hash,
)
from supportiq_backend.accounts.adapters.internal_accounts import (
    PostgresAccountChangeLock,
    PostgresInternalAccountStore,
)
from supportiq_backend.accounts.adapters.session_store import PostgresSessionStore
from supportiq_backend.accounts.adapters.sign_in_failure_store import PostgresSignInFailureStore
from supportiq_backend.accounts.api.admin import (
    AdminRoutes,
    build_admin_router,
    render_changed_account,
)
from supportiq_backend.accounts.api.dependencies import (
    CurrentSession,
    OriginCheck,
    build_current_session,
    build_origin_check,
)
from supportiq_backend.accounts.api.sessions import SessionRoutes, build_session_router
from supportiq_backend.audit.adapters.audit_log import PostgresAuditLog
from supportiq_backend.composition_root.shared_ports import SharedPorts
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from supportiq_backend.platform.adapters.database import SqlAlchemyTransactionRunner
from supportiq_backend.platform.settings import Settings


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


def build_sign_in_stores(session: AsyncSession) -> SignInStores:
    """Build the stores of sign-in on one session.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return SignInStores(
        accounts=PostgresAccountStore(session),
        sessions=PostgresSessionStore(session),
        failures=PostgresSignInFailureStore(session),
    )


def build_account_change_stores(session: AsyncSession) -> AccountChangeStores:
    """Build the stores of an account change on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return AccountChangeStores(
        lock=PostgresAccountChangeLock(session),
        accounts=PostgresInternalAccountStore(session),
        sessions=PostgresSessionStore(session),
        audit_log=PostgresAuditLog(session),
        idempotency=PostgresIdempotencyStore(session),
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
    session_transactions = SqlAlchemyTransactionRunner(session_factory, PostgresSessionStore)
    authorizer = Authorizer(shared.events)
    current_session = build_current_session(
        AuthenticateSession(session_transactions, shared.clock, build_session_policy(settings))
    )
    check_origin = build_origin_check(OriginPolicy(frozenset(settings.allowed_origins)))
    session_router = build_session_router(
        SessionRoutes(
            sign_in=_build_sign_in(settings, session_factory, shared),
            sign_out=SignOut(session_transactions),
            check_origin=check_origin,
            current_session=current_session,
            is_cookie_secure=settings.session_cookie_secure,
        )
    )
    admin_router = build_admin_router(
        AdminRoutes(
            list_accounts=ListAdminAccounts(
                SqlAlchemyTransactionRunner(session_factory, PostgresInternalAccountStore),
                authorizer,
            ),
            change_account=_build_change_account(session_factory, shared, authorizer),
            check_origin=check_origin,
            current_session=current_session,
        )
    )
    return AccountsWiring(
        routers=(session_router, admin_router),
        authorizer=authorizer,
        check_origin=check_origin,
        current_session=current_session,
    )


def _build_sign_in(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
) -> SignIn:
    passwords = Argon2Passwords()
    return SignIn(
        SqlAlchemyTransactionRunner(session_factory, build_sign_in_stores),
        SignInPorts(passwords, RandomSessionTokens(), shared.clock, shared.events),
        SignInRules(
            sessions=build_session_policy(settings),
            throttle=build_throttle_policy(settings),
            dummy_password_hash=create_dummy_password_hash(passwords),
        ),
    )


def _build_change_account(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    authorizer: Authorizer,
) -> ChangeAccount:
    return ChangeAccount(
        SqlAlchemyTransactionRunner(session_factory, build_account_change_stores),
        AccountChangePorts(
            guard=shared.guard,
            authorizer=authorizer,
            clock=shared.clock,
            ids=shared.ids,
            traces=shared.traces,
            events=shared.events,
        ),
        render_changed_account,
    )

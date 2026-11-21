"""In-memory fakes of the ports of accounts, and test data builders (ARCH-27, TEST-05)."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.accounts import (
    AccountId,
    AuthenticatedSession,
    CustomerId,
    DisplayName,
    InternalAccount,
    InternalRole,
    LoginName,
    LoginNameHash,
    NewSession,
    Password,
    PasswordHash,
    Role,
    SessionAccount,
    SessionIdHash,
    SessionRequiredError,
    SessionToken,
    SignInAccount,
    StoredSession,
)
from app.platform import BackendError
from tests.unit.platform.fakes import FAKE_CLOCK_START

STAFF_ACCOUNT_ID = AccountId("00000000-0000-0000-0000-00000000000a")
CUSTOMER_ACCOUNT_ID = AccountId("00000000-0000-0000-0000-00000000000b")
CUSTOMER_ID = CustomerId("00000000-0000-0000-0000-00000000000c")
DISPLAY_NAME = DisplayName("Mai Nguyen")
KNOWN_PASSWORD = "correct-test-password"
HASH_OF_KNOWN_PASSWORD = PasswordHash("hash-of-the-known-password")
DUMMY_HASH = PasswordHash("hash-of-nothing")
TOKEN_VALUE = "fixed-session-identifier"
DEFAULT_SESSION_ID_HASH = SessionIdHash(b"hash")
LOGIN_NAME = LoginName("staff-1")


def build_internal_account(
    account_id: AccountId,
    role: InternalRole,
    *,
    is_active: bool = True,
    name: str = "Mai Nguyen",
    login_name: LoginName = LOGIN_NAME,
) -> InternalAccount:
    """Build an internal account as the admin area sees it."""
    return InternalAccount(account_id, login_name, DisplayName(name), role, is_active)


def build_session_account(
    *, role: Role = Role.STAFF, customer_id: CustomerId | None = None
) -> SessionAccount:
    """Build the account of a session, a member of staff by default."""
    account_id = STAFF_ACCOUNT_ID if customer_id is None else CUSTOMER_ACCOUNT_ID
    return SessionAccount(account_id, role, DISPLAY_NAME, customer_id)


def build_sign_in_account(*, is_active: bool = True) -> SignInAccount:
    """Build an account that the known password opens."""
    return SignInAccount(build_session_account(), is_active, HASH_OF_KNOWN_PASSWORD)


def build_stored_session(
    *,
    session_id_hash: SessionIdHash = DEFAULT_SESSION_ID_HASH,
    last_seen_at: datetime = FAKE_CLOCK_START,
    expires_at: datetime = FAKE_CLOCK_START + timedelta(hours=8),
    is_account_active: bool = True,
    role_at_creation: Role = Role.STAFF,
) -> StoredSession:
    """Build a stored session of a member of staff."""
    return StoredSession(
        session_id_hash=session_id_hash,
        account=build_session_account(),
        role_at_creation=role_at_creation,
        is_account_active=is_account_active,
        last_seen_at=last_seen_at,
        expires_at=expires_at,
    )


@dataclass(slots=True)
class FakeAccountStore:
    """Accounts by login name."""

    accounts: dict[LoginName, SignInAccount] = field(default_factory=dict[LoginName, SignInAccount])

    async def load_for_sign_in(self, login_name: LoginName) -> SignInAccount | None:
        """Return the account of the name, if any."""
        return self.accounts.get(login_name)


@dataclass(slots=True)
class FakeSessionStore:
    """Sessions by hash, with a log of what was written."""

    sessions: dict[SessionIdHash, StoredSession] = field(
        default_factory=dict[SessionIdHash, StoredSession]
    )
    saved: list[NewSession] = field(default_factory=list[NewSession])
    deleted: list[SessionIdHash] = field(default_factory=list[SessionIdHash])
    touches: list[datetime] = field(default_factory=list[datetime])
    expired_deletions: list[tuple[datetime, datetime]] = field(
        default_factory=list[tuple[datetime, datetime]]
    )

    async def save(self, session: NewSession) -> None:
        """Keep the new session."""
        self.saved.append(session)

    async def load(self, session_id_hash: SessionIdHash) -> StoredSession | None:
        """Return the session of the hash, if any."""
        return self.sessions.get(session_id_hash)

    async def touch(self, session_id_hash: SessionIdHash, last_seen_at: datetime) -> None:
        """Remember the touch; the session keeps its fields."""
        del session_id_hash
        self.touches.append(last_seen_at)

    async def delete(self, session_id_hash: SessionIdHash) -> None:
        """Remove the session of the hash."""
        self.deleted.append(session_id_hash)
        self.sessions.pop(session_id_hash, None)

    async def delete_expired(self, *, now: datetime, idle_since: datetime) -> None:
        """Remember the bounds of the deletion."""
        self.expired_deletions.append((now, idle_since))


@dataclass(slots=True)
class FakeSignInFailureStore:
    """Failure times by name hash."""

    failures: dict[LoginNameHash, list[datetime]] = field(
        default_factory=dict[LoginNameHash, list[datetime]]
    )
    expired_since_of_saves: list[datetime] = field(default_factory=list[datetime])

    async def count_since(self, login_name_hash: LoginNameHash, since: datetime) -> int:
        """Count the failures of the name after the time."""
        return sum(moment > since for moment in self.failures.get(login_name_hash, ()))

    async def save_failure(
        self, login_name_hash: LoginNameHash, *, failed_at: datetime, expired_since: datetime
    ) -> None:
        """Keep the failure."""
        self.expired_since_of_saves.append(expired_since)
        self.failures.setdefault(login_name_hash, []).append(failed_at)

    async def delete_failures(self, login_name_hash: LoginNameHash) -> None:
        """Forget the failures of the name."""
        self.failures.pop(login_name_hash, None)


@dataclass(slots=True)
class FakePasswordVerifier:
    """A verifier that knows one password, and logs every hash it was asked about."""

    verified_hashes: list[PasswordHash] = field(default_factory=list[PasswordHash])

    async def verify(self, password_hash: PasswordHash, password: Password) -> bool:
        """Match only the known password against the known hash."""
        self.verified_hashes.append(password_hash)
        return password_hash == HASH_OF_KNOWN_PASSWORD and password.value == KNOWN_PASSWORD


@dataclass(slots=True)
class FakeInternalAccountStore:
    """Internal accounts by ID, sorted as the contract sorts them."""

    accounts: dict[AccountId, InternalAccount] = field(
        default_factory=dict[AccountId, InternalAccount]
    )
    calls: list[str] = field(default_factory=list[str])
    page_failure: BackendError | None = None

    async def load_internal(self, account_id: AccountId) -> InternalAccount | None:
        """Return the account, if any."""
        self.calls.append("load_internal")
        return self.accounts.get(account_id)

    async def count_active_managers(self) -> int:
        """Count the active managers."""
        return sum(
            account.is_active and account.role is InternalRole.MANAGER
            for account in self.accounts.values()
        )

    async def save_change(self, account: InternalAccount) -> None:
        """Replace the account."""
        self.calls.append("save_change")
        self.accounts[account.account_id] = account

    async def load_page(
        self, after: InternalAccount | None, limit: int
    ) -> tuple[InternalAccount, ...]:
        """Return the accounts after the position, in the order of the contract."""
        if self.page_failure is not None:
            raise self.page_failure
        ordered = sorted(
            self.accounts.values(), key=lambda account: (account.display_name, account.account_id)
        )
        if after is not None:
            position = (after.display_name, after.account_id)
            ordered = [
                account
                for account in ordered
                if (account.display_name, account.account_id) > position
            ]
        return tuple(ordered[:limit])


@dataclass(slots=True)
class FakeAccountChangeLock:
    """A lock that remembers it was taken, and before which store call."""

    calls: list[str]
    failure: BackendError | None = None

    async def acquire(self) -> None:
        """Remember the acquisition, or raise the chosen failure."""
        if self.failure is not None:
            raise self.failure
        self.calls.append("acquire_lock")


@dataclass(slots=True)
class FakeSessionRevoker:
    """Remember the accounts whose sessions were deleted, and the session that each kept."""

    revoked: list[AccountId] = field(default_factory=list[AccountId])
    revoked_except: list[tuple[AccountId, SessionIdHash]] = field(
        default_factory=list[tuple[AccountId, SessionIdHash]]
    )

    async def delete_sessions_of(self, account_id: AccountId) -> None:
        """Remember the account."""
        self.revoked.append(account_id)

    async def delete_other_sessions_of(self, account_id: AccountId, kept: SessionIdHash) -> None:
        """Remember the account and the session that stays."""
        self.revoked_except.append((account_id, kept))


@dataclass(slots=True)
class FakeAuthenticator:
    """Return one session, or raise the chosen failure, and keep the tokens it received."""

    session: AuthenticatedSession | None = None
    failure: BackendError | None = None
    tokens: list[SessionToken | None] = field(default_factory=list[SessionToken | None])

    async def authenticate(self, token: SessionToken | None) -> AuthenticatedSession:
        """Keep the token, then answer as the test chose."""
        self.tokens.append(token)
        if self.session is None:
            raise self.failure or SessionRequiredError
        return self.session


class FixedSessionTokens:
    """A session token generator that always returns one token."""

    def generate(self) -> SessionToken:
        """Return the fixed token."""
        return SessionToken(TOKEN_VALUE)

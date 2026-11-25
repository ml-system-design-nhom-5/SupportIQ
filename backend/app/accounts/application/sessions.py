"""The use cases of sessions: sign-in, authentication of a request, and sign-out (ADR-0009)."""

from dataclasses import dataclass, field

from app.accounts.application.throttle import SignInThrottle
from app.accounts.domain.errors import InvalidCredentialsError, SessionRequiredError
from app.accounts.domain.identity import PasswordHash, SessionToken
from app.accounts.domain.ports import (
    AccountStore,
    PasswordVerifier,
    SessionStore,
    SessionTokenGenerator,
    SignInFailureStore,
)
from app.accounts.domain.sessions import (
    AuthenticatedSession,
    SessionAccount,
    SessionPolicy,
    build_new_session,
    hash_session_token,
    is_session_valid,
    is_touch_due,
    to_principal,
)
from app.accounts.domain.sign_in import (
    Credentials,
    LoginNameHash,
    SignInAccount,
    ThrottlePolicy,
    hash_login_name,
    normalize_login_name,
)
from app.platform import (
    Clock,
    EventName,
    EventRecorder,
    Transaction,
    TransactionRunner,
)


@dataclass(frozen=True, slots=True)
class SignInStores:
    """The stores that sign-in uses in one transaction.

    Attributes:
        accounts: The accounts.
        sessions: The sessions.
        failures: The sign-in failures.
    """

    accounts: AccountStore
    sessions: SessionStore
    failures: SignInFailureStore


@dataclass(frozen=True, slots=True)
class SignInPorts:
    """The ports of sign-in besides its stores.

    Attributes:
        passwords: Verifies passwords.
        tokens: Generates session identifiers.
        clock: The clock.
        events: Where events are recorded.
    """

    passwords: PasswordVerifier
    tokens: SessionTokenGenerator
    clock: Clock
    events: EventRecorder


@dataclass(frozen=True, slots=True)
class SignInRules:
    """The rules of sign-in.

    Attributes:
        sessions: The session policy.
        throttle: The sign-in throttle.
        dummy_password_hash: A hash that unknown names verify against, so the response time
            does not reveal whether a name exists.
    """

    sessions: SessionPolicy
    throttle: ThrottlePolicy
    dummy_password_hash: PasswordHash = field(repr=False)


@dataclass(frozen=True, slots=True)
class SignedIn:
    """The result of a successful sign-in.

    Attributes:
        token: The raw session identifier, for the cookie only.
        account: The signed-in account.
    """

    token: SessionToken
    account: SessionAccount


class SignIn:
    """Verify credentials and create a session (`createSession`)."""

    def __init__(
        self,
        transactions: TransactionRunner[SignInStores],
        ports: SignInPorts,
        rules: SignInRules,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of a sign-in.
            ports: The ports besides the stores.
            rules: The rules of sign-in.
        """
        self._transactions = transactions
        self._ports = ports
        self._rules = rules
        self._throttle = SignInThrottle(ports.clock, rules.throttle)

    async def execute(self, credentials: Credentials) -> SignedIn:
        """Sign in.

        The transaction ends before the throttle waits, so a waiting attempt holds no
        connection of the pool.

        Args:
            credentials: What the person typed.

        Returns:
            The session identifier and the account.

        Raises:
            InvalidCredentialsError: The same error for an unknown name, a wrong password, a
                deactivated account, and a throttled attempt.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        login_name = normalize_login_name(credentials.login_name)
        name_hash = hash_login_name(login_name)
        async with self._transactions.begin() as transaction:
            failures = transaction.stores.failures
            failure_count = await self._throttle.load_recent_failure_count(failures, name_hash)
            if not self._throttle.is_at_limit(failure_count):
                account = await transaction.stores.accounts.load_for_sign_in(login_name)
                verified = await self._verify(account, credentials)
                if verified is not None:
                    return await self._create_session(transaction, verified, name_hash)
                await self._save_failure(transaction, name_hash)
                raise InvalidCredentialsError
        self._ports.events.record(EventName.SIGN_IN_THROTTLED)
        await self._throttle.wait()
        raise InvalidCredentialsError

    async def _verify(
        self, account: SignInAccount | None, credentials: Credentials
    ) -> SignInAccount | None:
        # The password is verified in every case, so all failures take the same time.
        password_hash = (
            self._rules.dummy_password_hash if account is None else account.password_hash
        )
        is_password_valid = await self._ports.passwords.verify(password_hash, credentials.password)
        if is_password_valid and account is not None and account.is_active:
            return account
        return None

    async def _create_session(
        self,
        transaction: Transaction[SignInStores],
        account: SignInAccount,
        name_hash: LoginNameHash,
    ) -> SignedIn:
        now = self._ports.clock.now()
        token = self._ports.tokens.generate()
        session = build_new_session(
            hash_session_token(token), account.account, now, self._rules.sessions
        )
        await transaction.stores.sessions.save(session)
        await transaction.stores.sessions.delete_expired(
            now=now, idle_since=now - self._rules.sessions.idle_timeout
        )
        await transaction.stores.failures.delete_failures(name_hash)
        await transaction.commit()
        self._ports.events.record(
            EventName.SESSION_CREATED,
            account_id=account.account.account_id,
            role=account.account.role.value,
        )
        return SignedIn(token, account.account)

    async def _save_failure(
        self, transaction: Transaction[SignInStores], name_hash: LoginNameHash
    ) -> None:
        await self._throttle.save_failure(transaction.stores.failures, name_hash)
        await transaction.commit()
        self._ports.events.record(EventName.SIGN_IN_FAILED)


class AuthenticateSession:
    """Implement the `Authenticator` port with the sessions of this database (ADR-0009)."""

    def __init__(
        self,
        transactions: TransactionRunner[SessionStore],
        clock: Clock,
        policy: SessionPolicy,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the transaction of the check.
            clock: The clock.
            policy: The session policy.
        """
        self._transactions = transactions
        self._clock = clock
        self._policy = policy

    async def authenticate(self, token: SessionToken | None) -> AuthenticatedSession:
        """Load the session of a request, deleting it when it has ended.

        Args:
            token: The value of the session cookie, or None when absent.

        Returns:
            The valid session with its principal.

        Raises:
            SessionRequiredError: The session is missing, unknown, expired, or idle.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        if token is None:
            raise SessionRequiredError
        session_id_hash = hash_session_token(token)
        now = self._clock.now()
        async with self._transactions.begin() as transaction:
            session = await transaction.stores.load(session_id_hash)
            if session is None:
                raise SessionRequiredError
            if not is_session_valid(session, now, self._policy):
                await transaction.stores.delete(session_id_hash)
                await transaction.commit()
                raise SessionRequiredError
            if is_touch_due(session, now, self._policy):
                await transaction.stores.touch(session_id_hash, now)
                await transaction.commit()
        return AuthenticatedSession(session_id_hash, to_principal(session.account), session.account)


class SignOut:
    """Delete the current session (`deleteCurrentSession`)."""

    def __init__(self, transactions: TransactionRunner[SessionStore]) -> None:
        """Keep the transaction runner.

        Args:
            transactions: Opens the transaction of the sign-out.
        """
        self._transactions = transactions

    async def execute(self, session: AuthenticatedSession) -> None:
        """Delete the session, so its cookie names nothing anymore.

        Args:
            session: The session of the request.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        async with self._transactions.begin() as transaction:
            await transaction.stores.delete(session.session_id_hash)
            await transaction.commit()

"""Replacing a password: the effects that an own change and a reset share (ADR-0015).

They live in one application service, so both use cases store the hash, end the sessions,
forget the sign-in failures, and write the audit log entry the same way (account management
design, Components and responsibilities).
"""

from dataclasses import dataclass
from typing import assert_never

from supportiq_backend.accounts.domain.identity import AccountId
from supportiq_backend.accounts.domain.password_ports import PasswordStore
from supportiq_backend.accounts.domain.passwords import (
    AdminPasswordReplacement,
    OwnPasswordReplacement,
    PasswordReplacement,
)
from supportiq_backend.accounts.domain.ports import (
    SessionRevoker,
    SignInFailureStore,
)
from supportiq_backend.accounts.domain.sign_in import hash_login_name
from supportiq_backend.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditValue,
)
from supportiq_backend.platform import Clock, IdGenerator, TraceContext


@dataclass(frozen=True, slots=True)
class PasswordReplacementStores:
    """The stores that replacing a password writes, in the transaction of its change.

    Attributes:
        passwords: The password hashes of accounts.
        sessions: Deletes the sessions that end.
        failures: The sign-in failures of login names.
        audit_log: The audit log.
    """

    passwords: PasswordStore
    sessions: SessionRevoker
    failures: SignInFailureStore
    audit_log: AuditLog


class ReplacePassword:
    """Store a new password hash, end sessions as chosen, and record it (SEC-42, SEC-39).

    Every step runs in the caller's transaction, after the caller locked the account's row,
    so the sessions are deleted after that lock, as every change of an account does.
    """

    def __init__(self, clock: Clock, ids: IdGenerator, traces: TraceContext) -> None:
        """Keep the ports of the audit log entry.

        Args:
            clock: The clock.
            ids: Generates the IDs of audit log entries.
            traces: Tells the trace of the request.
        """
        self._clock = clock
        self._ids = ids
        self._traces = traces

    async def apply(
        self, stores: PasswordReplacementStores, replacement: PasswordReplacement
    ) -> None:
        """Replace the password of an account, without committing.

        The sign-in failures of the login name are forgotten, as after a successful sign-in,
        so the owner can sign in at once with the new password.

        Args:
            stores: The stores bound to the caller's transaction.
            replacement: The replacement.
        """
        await stores.passwords.save_password_hash(replacement.account_id, replacement.password_hash)
        await _end_sessions(stores.sessions, replacement)
        await stores.failures.delete_failures(hash_login_name(replacement.login_name))
        await stores.audit_log.append(self._build_audit_entry(replacement))

    def _build_audit_entry(self, replacement: PasswordReplacement) -> AuditEntry:
        event_type, actor_id, data = _audit_record_of(replacement)
        return AuditEntry(
            entry_id=AuditEntryId(self._ids.generate()),
            occurred_at=self._clock.now(),
            event_type=event_type,
            actor_account_id=ActorAccountId(actor_id),
            ticket_id=None,
            trace_id=self._traces.current_trace_id(),
            data=data,
        )


async def _end_sessions(sessions: SessionRevoker, replacement: PasswordReplacement) -> None:
    match replacement:
        case OwnPasswordReplacement():
            if replacement.is_signed_out_elsewhere:
                await sessions.delete_other_sessions_of(
                    replacement.account_id, replacement.current_session
                )
        case AdminPasswordReplacement():
            if replacement.is_signed_out_everywhere:
                await sessions.delete_sessions_of(replacement.account_id)
        case _:
            assert_never(replacement)


def _audit_record_of(
    replacement: PasswordReplacement,
) -> tuple[AuditEventType, AccountId, dict[str, AuditValue]]:
    # No entry holds a password, a hash, a login name, or a display name (SEC-39).
    match replacement:
        case OwnPasswordReplacement():
            return (
                AuditEventType.ACCOUNT_PASSWORD_CHANGED,
                replacement.account_id,
                {
                    "target_account_id": replacement.account_id,
                    "is_signed_out_elsewhere": replacement.is_signed_out_elsewhere,
                },
            )
        case AdminPasswordReplacement():
            return (
                AuditEventType.ACCOUNT_PASSWORD_RESET,
                replacement.admin_id,
                {
                    "target_account_id": replacement.account_id,
                    "is_signed_out_everywhere": replacement.is_signed_out_everywhere,
                },
            )
        case _:
            assert_never(replacement)

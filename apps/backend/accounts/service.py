from datetime import timedelta
import hashlib
import secrets
import time
import uuid

from argon2.exceptions import VerificationError, InvalidHashError
from sqlalchemy import delete, func, select, text

from apps.backend.platform.database import Problem, audit, utcnow
from apps.backend.platform.models import Account, SessionRecord, SignInFailure

COOKIE = "supportiq_session"


def session_view(account):
    return {"account_id": account.account_id, "display_name": account.display_name, "role": account.role}


def create_session(database, settings, hasher, dummy_hash, login_name, password):
    normalized = login_name.strip().lower()
    name_hash = hashlib.sha256(normalized.encode()).hexdigest()
    now = utcnow()
    with database.transaction() as session:
        session.execute(delete(SignInFailure).where(SignInFailure.failed_at < now - timedelta(milliseconds=settings.sign_in_failure_window_ms)))
        count = session.scalar(select(func.count()).select_from(SignInFailure).where(SignInFailure.login_name_hash == name_hash))
        account = session.scalar(select(Account).where(Account.login_name == normalized))
        try:
            valid = hasher.verify(account.password_hash if account else dummy_hash, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if count >= settings.sign_in_failure_limit or not valid or not account or not account.is_active:
            session.add(SignInFailure(failure_id=str(uuid.uuid4()), login_name_hash=name_hash, failed_at=now))
            denied = True
        else:
            denied = False
            token = secrets.token_urlsafe(32)
            session.add(SessionRecord(session_id_hash=hashlib.sha256(token.encode()).hexdigest(), account_id=account.account_id,
                                      role=account.role, created_at=now, last_seen_at=now,
                                      expires_at=now + timedelta(milliseconds=settings.session_absolute_lifetime_ms)))
            session.execute(delete(SignInFailure).where(SignInFailure.login_name_hash == name_hash))
            session.execute(delete(SessionRecord).where(SessionRecord.expires_at < now))
            result = session_view(account)
    if denied:
        if count >= settings.sign_in_failure_limit:
            time.sleep(settings.sign_in_failure_delay_ms / 1000)
        raise Problem(401, "unauthenticated", "The login name or password is incorrect.")
    return token, result


def authenticate(session, token, settings, roles=None):
    record = session.get(SessionRecord, hashlib.sha256((token or "").encode()).hexdigest())
    now = utcnow()
    if not record or record.expires_at <= now or record.last_seen_at + timedelta(milliseconds=settings.session_idle_timeout_ms) <= now:
        raise Problem(401, "unauthenticated", "Your session has expired. Sign in to continue.")
    account = session.get(Account, record.account_id)
    if not account or not account.is_active or account.role != record.role:
        raise Problem(401, "unauthenticated", "Sign in again to continue.")
    if roles and account.role not in roles:
        raise Problem(403, "forbidden", "Your account cannot open this area.")
    if (now - record.last_seen_at).total_seconds() > 60:
        record.last_seen_at = now
    return account


def account_view(account):
    return {**session_view(account), "is_active": account.is_active}


def change_account(session, actor, target_id, field, value, trace_id):
    session.execute(text("SELECT pg_advisory_xact_lock(7349621)"))
    session.refresh(actor)
    if not actor.is_active or actor.role != "admin":
        raise Problem(401, "unauthenticated", "Your session has changed. Sign in again.")
    target = session.get(Account, target_id)
    if target is None or target.role == "customer":
        raise Problem(404, "not-found", "The account was not found.")
    if target.account_id == actor.account_id:
        raise Problem(422, "invalid-request", "You cannot change your own account.")
    if field == "role" and (target.role not in ("staff", "manager") or value not in ("staff", "manager")):
        raise Problem(422, "invalid-request", "Only staff and manager roles can be changed.")
    new_role = value if field == "role" else target.role
    new_active = value if field == "is_active" else target.is_active
    if target.is_active and target.role in ("manager", "admin") and (not new_active or new_role != target.role):
        remaining = session.scalar(select(func.count()).select_from(Account).where(Account.role == target.role, Account.is_active.is_(True), Account.account_id != target.account_id))
        if not remaining:
            raise Problem(422, "invalid-request", f"{target.display_name} is the last active {target.role}. Activate another {target.role} first.")
    old = getattr(target, field)
    setattr(target, field, value)
    session.execute(delete(SessionRecord).where(SessionRecord.account_id == target.account_id))
    audit(session, "account.role_changed" if field == "role" else "account.status_changed", actor.account_id, trace_id,
          target_account_id=target.account_id, previous=old, current=value)
    return account_view(target)

"""Tests of the rules of sessions and sign-in (ADR-0009, TEST-12)."""

import hashlib
from datetime import timedelta

import pytest

from supportiq_backend.accounts import (
    CustomerPrincipal,
    ForbiddenOriginError,
    InternalPrincipal,
    InternalRole,
    LoginName,
    OriginPolicy,
    Password,
    Role,
    SessionAccount,
    SessionPolicy,
    SessionToken,
    ThrottlePolicy,
    build_new_session,
    hash_login_name,
    hash_session_token,
    is_session_valid,
    is_throttled,
    is_touch_due,
    normalize_login_name,
    to_principal,
    validate_origin,
)
from tests.unit.accounts.fakes import (
    CUSTOMER_ID,
    DISPLAY_NAME,
    STAFF_ACCOUNT_ID,
    TOKEN_VALUE,
    build_session_account,
    build_stored_session,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START

POLICY = SessionPolicy(
    idle_timeout=timedelta(minutes=30),
    absolute_lifetime=timedelta(hours=8),
    touch_interval=timedelta(minutes=1),
)
THROTTLE = ThrottlePolicy(failure_limit=5, failure_window=timedelta(minutes=15), delay_ms=2_000)
ORIGINS = OriginPolicy(frozenset({"http://shop.test"}))
ONE_MICROSECOND = timedelta(microseconds=1)
NOW = FAKE_CLOCK_START


def test_session_hash_is_the_sha256_of_the_identifier() -> None:
    session_id_hash = hash_session_token(SessionToken(TOKEN_VALUE))

    assert session_id_hash == hashlib.sha256(TOKEN_VALUE.encode()).digest()


def test_new_session_ends_after_the_absolute_lifetime() -> None:
    session = build_new_session(
        hash_session_token(SessionToken(TOKEN_VALUE)), build_session_account(), NOW, POLICY
    )

    assert session.created_at == NOW
    assert session.expires_at == NOW + timedelta(hours=8)
    assert session.role is Role.STAFF


@pytest.mark.parametrize(
    ("idle_for", "is_valid"),
    [
        (timedelta(0), True),
        (POLICY.idle_timeout - ONE_MICROSECOND, True),
        (POLICY.idle_timeout, False),
        (POLICY.idle_timeout + ONE_MICROSECOND, False),
    ],
)
def test_session_ends_after_the_idle_timeout(idle_for: timedelta, is_valid: bool) -> None:
    session = build_stored_session(last_seen_at=NOW - idle_for)

    assert is_session_valid(session, NOW, POLICY) is is_valid


@pytest.mark.parametrize(
    ("time_left", "is_valid"),
    [(ONE_MICROSECOND, True), (timedelta(0), False), (-ONE_MICROSECOND, False)],
)
def test_session_ends_at_its_absolute_lifetime(time_left: timedelta, is_valid: bool) -> None:
    session = build_stored_session(last_seen_at=NOW, expires_at=NOW + time_left)

    assert is_session_valid(session, NOW, POLICY) is is_valid


def test_session_of_a_deactivated_account_is_not_valid() -> None:
    session = build_stored_session(is_account_active=False)

    assert not is_session_valid(session, NOW, POLICY)


def test_session_of_an_account_with_another_role_is_not_valid() -> None:
    session = build_stored_session(role_at_creation=Role.MANAGER)

    assert not is_session_valid(session, NOW, POLICY)


@pytest.mark.parametrize(
    ("since_touch", "is_due"),
    [
        (POLICY.touch_interval - ONE_MICROSECOND, False),
        (POLICY.touch_interval, True),
        (POLICY.touch_interval + ONE_MICROSECOND, True),
    ],
)
def test_touch_is_due_once_the_touch_interval_has_passed(
    since_touch: timedelta, is_due: bool
) -> None:
    session = build_stored_session(last_seen_at=NOW - since_touch)

    assert is_touch_due(session, NOW, POLICY) is is_due


def test_principal_of_a_customer_account_carries_its_customer() -> None:
    account = build_session_account(role=Role.CUSTOMER, customer_id=CUSTOMER_ID)

    principal = to_principal(account)

    assert principal == CustomerPrincipal(account.account_id, CUSTOMER_ID)


@pytest.mark.parametrize(
    ("role", "internal_role"),
    [
        (Role.STAFF, InternalRole.STAFF),
        (Role.MANAGER, InternalRole.MANAGER),
        (Role.ADMIN, InternalRole.ADMIN),
    ],
)
def test_principal_of_an_internal_account_carries_its_role(
    role: Role, internal_role: InternalRole
) -> None:
    principal = to_principal(SessionAccount(STAFF_ACCOUNT_ID, role, DISPLAY_NAME))

    assert principal == InternalPrincipal(STAFF_ACCOUNT_ID, internal_role)


@pytest.mark.parametrize(
    ("typed_name", "normalized"),
    [
        ("staff-1", "staff-1"),
        ("Staff-1", "staff-1"),
        ("  staff-1\t", "staff-1"),
        ("\uff33\uff34\uff21\uff26\uff26-\uff11", "staff-1"),
        ("Straße", "strasse"),
        ("   ", ""),
    ],
)
def test_login_names_are_normalized(typed_name: str, normalized: str) -> None:
    login_name = normalize_login_name(typed_name)

    assert login_name == normalized


def test_login_name_hash_is_the_sha256_of_the_normalized_name() -> None:
    name_hash = hash_login_name(LoginName("staff-1"))

    assert name_hash == hashlib.sha256(b"staff-1").digest()


@pytest.mark.parametrize(
    ("failure_count", "expected"), [(0, False), (4, False), (5, True), (6, True)]
)
def test_throttle_starts_at_the_failure_limit(failure_count: int, expected: bool) -> None:
    assert is_throttled(failure_count, THROTTLE) is expected


def test_allowed_origin_passes() -> None:
    validate_origin("http://shop.test", ORIGINS)

    assert "http://shop.test" in ORIGINS.allowed_origins


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "",
        "null",
        "http://evil.test",
        "http://shop.test/",
        "HTTP://SHOP.TEST",
        "http://shop.test:8080",
    ],
)
def test_any_other_origin_is_refused(origin: str | None) -> None:
    with pytest.raises(ForbiddenOriginError):
        validate_origin(origin, ORIGINS)


def test_secrets_and_names_never_appear_in_a_repr() -> None:
    text = repr(
        (
            Password("correct-test-password"),
            SessionToken(TOKEN_VALUE),
            build_session_account(),
            build_stored_session(),
        )
    )

    assert "correct-test-password" not in text
    assert TOKEN_VALUE not in text
    assert DISPLAY_NAME not in text

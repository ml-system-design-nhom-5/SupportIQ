"""Tests of the Argon2id adapter and of random session identifiers (ADR-0009)."""

import pytest

from app.accounts import Password, PasswordHash
from app.accounts.adapters.credentials import (
    Argon2Passwords,
    RandomSessionTokens,
    create_dummy_password_hash,
)
from tests.integration.builders import UNUSABLE_PASSWORD_HASH
from tests.unit.accounts.fakes import KNOWN_PASSWORD

pytestmark = pytest.mark.anyio

PASSWORD = Password(KNOWN_PASSWORD)
ARGON2ID_PREFIX = "$argon2id$"
MINIMUM_TOKEN_LENGTH = 43


async def test_a_password_matches_its_own_hash() -> None:
    passwords = Argon2Passwords()

    password_hash = await passwords.hash_password(PASSWORD)

    assert password_hash.startswith(ARGON2ID_PREFIX)
    assert await passwords.verify(password_hash, PASSWORD) is True


async def test_another_password_does_not_match(known_password_hash: PasswordHash) -> None:
    is_valid = await Argon2Passwords().verify(known_password_hash, Password("other"))

    assert is_valid is False


async def test_a_malformed_hash_matches_nothing() -> None:
    is_valid = await Argon2Passwords().verify(PasswordHash(UNUSABLE_PASSWORD_HASH), PASSWORD)

    assert is_valid is False


async def test_the_dummy_hash_is_a_real_hash_of_no_known_password() -> None:
    passwords = Argon2Passwords()

    dummy_hash = create_dummy_password_hash(passwords)

    assert dummy_hash.startswith(ARGON2ID_PREFIX)
    assert await passwords.verify(dummy_hash, PASSWORD) is False


async def test_session_tokens_are_long_and_different() -> None:
    tokens = RandomSessionTokens()

    first, second = tokens.generate(), tokens.generate()

    assert first != second
    assert len(first.value) >= MINIMUM_TOKEN_LENGTH

"""Argon2id password hashes and random session identifiers (ADR-0009, statements 3 and 4)."""

import asyncio
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.accounts.domain import Password, PasswordHash, SessionToken

# 256 bits of randomness; the raw value exists only in the cookie.
_SESSION_TOKEN_BYTES = 32


class Argon2Passwords:
    """Implement the `PasswordVerifier` and `PasswordHasher` ports with argon2-cffi.

    Every hash uses the default Argon2id profile of the library, the seed's as well as those
    of account creations, password changes, and resets (ADR-0015).

    Hashing takes tens of milliseconds of CPU, so it runs in a worker thread (PY-31).
    """

    def __init__(self) -> None:
        """Create the hasher with the library's default parameters."""
        self._hasher = PasswordHasher()

    async def verify(self, password_hash: PasswordHash, password: Password) -> bool:
        """Tell whether a password matches a hash.

        Args:
            password_hash: The Argon2id hash.
            password: The password as typed.

        Returns:
            True on a match. A malformed hash matches nothing.
        """
        return await asyncio.to_thread(self._matches, password_hash, password)

    async def hash_password(self, password: Password) -> PasswordHash:
        """Hash a password exactly as typed, with a new random salt.

        Args:
            password: The password.

        Returns:
            The Argon2id hash.
        """
        return await asyncio.to_thread(self.hash_blocking, password)

    def hash_blocking(self, password: Password) -> PasswordHash:
        """Hash a password on the current thread, for startup, before the event loop runs.

        Args:
            password: The password.

        Returns:
            The Argon2id hash.
        """
        return PasswordHash(self._hasher.hash(password.value))

    def _matches(self, password_hash: PasswordHash, password: Password) -> bool:
        try:
            return self._hasher.verify(password_hash, password.value)
        except VerificationError, InvalidHashError:
            return False


class RandomSessionTokens:
    """Implement the `SessionTokenGenerator` port with the system's secure random source."""

    def generate(self) -> SessionToken:
        """Return a new random session identifier."""
        return SessionToken(secrets.token_urlsafe(_SESSION_TOKEN_BYTES))


def create_dummy_password_hash(passwords: Argon2Passwords) -> PasswordHash:
    """Create the hash that unknown names verify against.

    The hash of a random value, made with the same parameters as every real hash, takes the
    same time to verify and matches no password (backend foundation design, step 2).

    Args:
        passwords: The password hasher.

    Returns:
        The dummy hash, fixed for the life of the process.
    """
    return passwords.hash_blocking(Password(secrets.token_urlsafe(_SESSION_TOKEN_BYTES)))

"""The sign-in throttle of a login name, shared by sign-in and the own password change.

Each wrong password counts as a failure of the login name, and at the limit every attempt
waits and is refused without a check (ADR-0009, statement 8; ADR-0015, Own password).
"""

from datetime import datetime

from supportiq_backend.accounts.domain.ports import SignInFailureStore
from supportiq_backend.accounts.domain.sign_in import LoginNameHash, ThrottlePolicy, is_throttled
from supportiq_backend.platform import Clock


class SignInThrottle:
    """Count, record, and wait out the sign-in failures of a login name."""

    def __init__(self, clock: Clock, policy: ThrottlePolicy) -> None:
        """Keep the clock and the policy.

        Args:
            clock: The clock, for the window and the wait.
            policy: The sign-in throttle, from the settings.
        """
        self._clock = clock
        self._policy = policy

    async def load_recent_failure_count(
        self, failures: SignInFailureStore, name_hash: LoginNameHash
    ) -> int:
        """Count the failures of a login name within the window.

        Args:
            failures: The store bound to the caller's transaction.
            name_hash: The hash of the normalized login name.

        Returns:
            The number of failures that still count.
        """
        return await failures.count_since(name_hash, self._window_start(self._clock.now()))

    def is_at_limit(self, failure_count: int) -> bool:
        """Tell whether a login name has reached the failure limit.

        Args:
            failure_count: The failures of the name within the window.

        Returns:
            True at the limit and above it.
        """
        return is_throttled(failure_count, self._policy)

    async def save_failure(self, failures: SignInFailureStore, name_hash: LoginNameHash) -> None:
        """Record a failure of a login name, and delete the failures that no longer count.

        Args:
            failures: The store bound to the caller's transaction, which the caller commits.
            name_hash: The hash of the normalized login name.
        """
        now = self._clock.now()
        await failures.save_failure(name_hash, failed_at=now, expired_since=self._window_start(now))

    async def wait(self) -> None:
        """Wait the delay of an attempt at the limit, after its transaction ended."""
        await self._clock.sleep(self._policy.delay_ms)

    def _window_start(self, now: datetime) -> datetime:
        # Failures at or before this time no longer count, and are deleted.
        return now - self._policy.failure_window

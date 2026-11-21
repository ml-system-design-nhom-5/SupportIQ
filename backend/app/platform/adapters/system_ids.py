"""Random identifiers for new records (ARCH-31)."""

from uuid import UUID, uuid4


class RandomIdGenerator:
    """Implement the `IdGenerator` port with random version 4 UUIDs."""

    def generate(self) -> UUID:
        """Return a new random UUID."""
        return uuid4()

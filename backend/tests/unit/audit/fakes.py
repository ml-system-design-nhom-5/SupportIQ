"""In-memory fake of the `AuditLog` port (ARCH-27)."""

from dataclasses import dataclass, field

from app.audit import AuditEntry
from app.platform import BackendError


@dataclass(slots=True)
class FakeAuditLog:
    """Keep the appended entries, or fail with a given error."""

    entries: list[AuditEntry] = field(default_factory=list[AuditEntry])
    failure: BackendError | None = None

    async def append(self, entry: AuditEntry) -> None:
        """Keep the entry, or raise the chosen failure."""
        if self.failure is not None:
            raise self.failure
        self.entries.append(entry)

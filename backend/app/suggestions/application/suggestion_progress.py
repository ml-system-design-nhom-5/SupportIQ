"""Follow the progress of a ticket's current suggestion as a stream (ADR-0022).

A stream sends the current state first, then one item whenever the current suggestion or the
status of one of its parts changes. It learns of a change as the claim loop does: from an
in-process wake-up after a use case of this replica commits, and from a re-read every
`suggestion_events_poll_ms` for a job that another replica finished. Each read is one short
transaction, so no connection is held between two reads.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from app.accounts import Authorizer, Principal, SupportPrincipal
from app.platform import (
    Clock,
    EventName,
    EventRecorder,
    OperationId,
    ResourceNotFoundError,
    TransactionRunner,
)
from app.suggestions.application.claim_loop import wait_for_wake_up
from app.suggestions.domain import (
    StreamEndReason,
    StreamSettings,
    SuggestionProgress,
    SuggestionStore,
    SuggestionTicketId,
    SuggestionTickets,
    TicketForSuggestion,
)

# A stream that sent nothing for this long sends a ping comment (ADR-0022, statement 3).
PING_AFTER_MS = 15_000


@dataclass(frozen=True, slots=True)
class ProgressStores:
    """The stores of the read transaction of a stream.

    Attributes:
        tickets: The ticket rows, read without a lock.
        suggestions: The part statuses.
    """

    tickets: SuggestionTickets
    suggestions: SuggestionStore


class ProgressSignals:
    """The wake-ups of the streams of this replica, by ticket.

    A wake-up holds no state: a lost one only delays an event until the next re-read.
    """

    def __init__(self) -> None:
        """Start without streams."""
        self._streams: defaultdict[SuggestionTicketId, set[asyncio.Event]] = defaultdict(set)

    def notify_progress(self, ticket_id: SuggestionTicketId) -> None:
        """Wake every stream of the ticket.

        Args:
            ticket_id: The ticket whose suggestion or part statuses changed, committed already.
        """
        for wake_up in self._streams.get(ticket_id, ()):
            wake_up.set()

    @contextmanager
    def subscribe(self, ticket_id: SuggestionTicketId) -> Generator[asyncio.Event]:
        """Register the wake-up of one stream while it lives.

        Args:
            ticket_id: The ticket of the stream.

        Yields:
            The event that `notify_progress` sets.
        """
        wake_up = asyncio.Event()
        streams = self._streams[ticket_id]
        streams.add(wake_up)
        try:
            yield wake_up
        finally:
            streams.discard(wake_up)
            if not streams:
                del self._streams[ticket_id]


@dataclass(frozen=True, slots=True)
class WatchProgressPorts:
    """The ports of the stream besides its transactions.

    Attributes:
        authorizer: The role checks.
        signals: The wake-ups of this replica.
        clock: The clock, for the waits and the time limit.
        events: Where the end of a stream is recorded.
    """

    authorizer: Authorizer
    signals: ProgressSignals
    clock: Clock
    events: EventRecorder


class WatchSuggestionProgress:
    """Follow the current suggestion of a ticket while a part is pending (`getSuggestionEvents`)."""

    def __init__(
        self,
        transactions: TransactionRunner[ProgressStores],
        ports: WatchProgressPorts,
        settings: StreamSettings,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the read transactions.
            ports: The ports besides the stores.
            settings: The poll interval and the time limit.
        """
        self._transactions = transactions
        self._ports = ports
        self._settings = settings

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only staff and managers, before the ticket is read.

        Args:
            principal: The caller.

        Returns:
            The caller as a member of support.

        Raises:
            ForbiddenRoleError: The caller is a customer or an admin.
        """
        return self._ports.authorizer.require_support(principal, OperationId.GET_SUGGESTION_EVENTS)

    async def open(
        self, ticket_id: SuggestionTicketId
    ) -> AsyncIterator[SuggestionProgress | None] | None:
        """Read the current state, after `authorize` allowed the caller.

        Args:
            ticket_id: The ticket, as the request sent it.

        Returns:
            The stream: the current state, then one item per change, and None when nothing
            changed for 15 s, for a ping. None instead of a stream when there is nothing to
            follow: the ticket is not `open`, is in `manual` mode, or has no `pending` part.

        Raises:
            ResourceNotFoundError: The ticket is unknown.
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        ticket, progress = await self._read(ticket_id)
        if ticket is None:
            raise ResourceNotFoundError
        if progress is None or not (ticket.is_open and ticket.is_assisted and progress.is_pending):
            return None
        return self._follow(ticket_id, progress)

    async def _follow(
        self, ticket_id: SuggestionTicketId, progress: SuggestionProgress
    ) -> AsyncIterator[SuggestionProgress | None]:
        clock = self._ports.clock
        deadline = clock.now() + timedelta(milliseconds=self._settings.max_ms)
        last_sent = clock.now()
        with self._ports.signals.subscribe(ticket_id) as wake_up:
            yield progress
            while True:
                await wait_for_wake_up(clock, self._settings.poll_ms, wake_up)
                if clock.now() >= deadline:
                    self._record_end(ticket_id, StreamEndReason.TIME_LIMIT)
                    return
                try:
                    ticket, current = await self._read(ticket_id)
                except Exception as error:
                    # The top-level runner of a stream: the stream ends, and the reconnect of
                    # `EventSource` gets the answer of the first read (PY-21).
                    self._ports.events.record(
                        EventName.SUGGESTION_STREAM_FAILED,
                        ticket_id=ticket_id,
                        error_type=type(error).__name__,
                    )
                    return
                if ticket is None or not ticket.is_open:
                    self._record_end(ticket_id, StreamEndReason.TICKET_NOT_OPEN)
                    return
                # A part is cancelled only when a newer suggestion became the current one
                # between the two reads; the next read finds it.
                if current is not None and not current.is_superseded and current != progress:
                    progress = current
                    yield progress
                    last_sent = clock.now()
                    if not progress.is_pending:
                        self._record_end(ticket_id, StreamEndReason.NO_PENDING_PART)
                        return
                elif clock.now() - last_sent >= timedelta(milliseconds=PING_AFTER_MS):
                    yield None
                    last_sent = clock.now()

    async def _read(
        self, ticket_id: SuggestionTicketId
    ) -> tuple[TicketForSuggestion | None, SuggestionProgress | None]:
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            ticket = await stores.tickets.read_ticket(ticket_id)
            if ticket is None or ticket.current_suggestion_id is None:
                return ticket, None
            return ticket, await stores.suggestions.load_progress(ticket.current_suggestion_id)

    def _record_end(self, ticket_id: SuggestionTicketId, reason: StreamEndReason) -> None:
        self._ports.events.record(
            EventName.SUGGESTION_STREAM_ENDED, ticket_id=ticket_id, stream_end_reason=reason.value
        )

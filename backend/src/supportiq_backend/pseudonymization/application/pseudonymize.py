"""Pseudonymize the message of a ticket before any text derived from it leaves backend.

This is the first of the two functions of the public API of pseudonymization (ADR-0010,
Storage and lifecycle, item 6). It runs as the first step of every suggestion job.
"""

from dataclasses import dataclass

from supportiq_backend.accounts import CustomerId
from supportiq_backend.audit import (
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditTicketId,
    AuditValue,
)
from supportiq_backend.commerce import (
    CustomerContact,
    CustomerRecords,
    OrderId,
    OrderReferences,
)
from supportiq_backend.platform import (
    Clock,
    EventName,
    EventRecorder,
    IdGenerator,
    SpanName,
    StepTracer,
    TraceContext,
    TransactionRunner,
)
from supportiq_backend.pseudonymization.domain import (
    Detector,
    DetectorError,
    KnownValue,
    MapTicketId,
    PseudonymEntry,
    PseudonymizationError,
    PseudonymizedMessage,
    PseudonymizedTextTooLongError,
    PseudonymMapStore,
    PseudonymType,
    StoredMapDiffersError,
    build_pseudonymized_message,
    resolve_overlaps,
)

OUTCOME_FIELD = "outcome"
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
FAILURE_REASON_FIELD = "failure_reason"
COUNT_FIELD_SUFFIX = "_count"
# A part of a display name becomes a known value of its own from this length on (ADR-0010,
# Detection, step 2), so "Lan" is found while "Le" is not.
NAME_PART_MIN_LENGTH = 3


@dataclass(frozen=True, slots=True, repr=False)
class MessageToPseudonymize:
    """The message of a ticket and the records that give its known values.

    Attributes:
        ticket_id: The ticket.
        message: The customer's message, as written. Confidential.
        customer_id: The customer who wrote it.
        order_id: The ticket's order; absent for an imported ticket without one.
    """

    ticket_id: MapTicketId
    message: str
    customer_id: CustomerId
    order_id: OrderId | None


@dataclass(frozen=True, slots=True)
class PseudonymizationStores:
    """The stores of one pseudonymization run, all in one transaction.

    Attributes:
        pseudonyms: The pseudonym map.
        records: The customer's commerce records, for the known values.
        audit: The audit log.
    """

    pseudonyms: PseudonymMapStore
    records: CustomerRecords
    audit: AuditLog


@dataclass(frozen=True, slots=True)
class PseudonymizationPorts:
    """The ports of a pseudonymization run besides its stores.

    Attributes:
        detectors: The detectors of ADR-0010, in the order of its steps.
        clock: The clock.
        ids: Generates the IDs of audit log entries.
        traces: Tells the trace of the job.
        events: Where events are recorded.
        steps: Runs the pseudonymization in its span (LOG-20).
    """

    detectors: tuple[Detector, ...]
    clock: Clock
    ids: IdGenerator
    traces: TraceContext
    events: EventRecorder
    steps: StepTracer


class PseudonymizeMessage:
    """Return the pseudonymized text of a ticket's message, or fail closed (SEC-36)."""

    def __init__(
        self,
        transactions: TransactionRunner[PseudonymizationStores],
        ports: PseudonymizationPorts,
    ) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the short transaction of one run.
            ports: The ports besides the stores.
        """
        self._transactions = transactions
        self._ports = ports

    async def pseudonymize(self, message: MessageToPseudonymize) -> str:
        """Pseudonymize the message, store its map on the first run, and audit the outcome.

        The map is inserted in its own short transaction, before any call to `ai-service`.
        Every later run computes the same map and reuses the stored one (ADR-0010, Storage
        and lifecycle, item 2).

        Args:
            message: The ticket's message and its records.

        Returns:
            The pseudonymized text, at most 4 000 characters.

        Raises:
            PseudonymizationError: A detector failed, the text is too long, or the stored map
                differs. The failure is in the audit log, and nothing may be sent.
            DatabaseUnavailableError: The database is not available: no failure of
                pseudonymization, and the job tries again after its lease.
        """
        with self._ports.steps.step(SpanName.PSEUDONYMIZE_MESSAGE):
            self._ports.steps.record_ticket(message.ticket_id)
            async with self._transactions.begin() as transaction:
                stores = transaction.stores
                try:
                    result = await self._pseudonymize(stores, message)
                except PseudonymizationError as error:
                    await stores.audit.append(self._failure_entry(message.ticket_id, error))
                    await transaction.commit()
                    self._record_failure(message.ticket_id, error)
                    raise
                await stores.audit.append(self._success_entry(message.ticket_id, result))
                await transaction.commit()
            self._ports.steps.record_pseudonym_count(len(result.entries))
        return result.text

    async def _pseudonymize(
        self, stores: PseudonymizationStores, message: MessageToPseudonymize
    ) -> PseudonymizedMessage:
        known_values = build_known_values(*await _load_records(stores.records, message))
        detections = tuple(
            detection
            for detector in self._ports.detectors
            for detection in detector.detect(message.message, known_values)
        )
        result = build_pseudonymized_message(message.message, resolve_overlaps(detections))
        await stores.pseudonyms.insert_missing(
            message.ticket_id, result.entries, self._ports.clock.now()
        )
        stored = await stores.pseudonyms.load_entries(message.ticket_id)
        if _entry_keys(stored) != _entry_keys(result.entries):
            raise StoredMapDiffersError
        return result

    def _success_entry(self, ticket_id: MapTicketId, result: PseudonymizedMessage) -> AuditEntry:
        data: dict[str, AuditValue] = {OUTCOME_FIELD: OUTCOME_SUCCEEDED}
        for pseudonym_type, count in result.count_by_type().items():
            data[pseudonym_type.value.lower() + COUNT_FIELD_SUFFIX] = count
        return self._entry(ticket_id, data)

    def _failure_entry(self, ticket_id: MapTicketId, error: PseudonymizationError) -> AuditEntry:
        return self._entry(
            ticket_id, {OUTCOME_FIELD: OUTCOME_FAILED, FAILURE_REASON_FIELD: error.reason.value}
        )

    def _entry(self, ticket_id: MapTicketId, data: dict[str, AuditValue]) -> AuditEntry:
        return AuditEntry(
            entry_id=AuditEntryId(self._ports.ids.generate()),
            occurred_at=self._ports.clock.now(),
            event_type=AuditEventType.MESSAGE_PSEUDONYMIZED,
            actor_account_id=None,
            ticket_id=AuditTicketId(ticket_id),
            trace_id=self._ports.traces.current_trace_id(),
            data=data,
        )

    def _record_failure(self, ticket_id: MapTicketId, error: PseudonymizationError) -> None:
        # A text that is too long is handled input; every other failure is a defect
        # (ADR-0010, Failure handling).
        event = (
            EventName.PSEUDONYMIZATION_REJECTED
            if isinstance(error, PseudonymizedTextTooLongError)
            else EventName.PSEUDONYMIZATION_FAILED
        )
        self._ports.events.record(event, ticket_id=ticket_id, reason_code=error.reason.value)


def build_known_values(
    contact: CustomerContact, references: OrderReferences | None
) -> tuple[KnownValue, ...]:
    """Collect the values that backend holds for a ticket (ADR-0010, Detection, step 2).

    Args:
        contact: The customer's personal values.
        references: The identifying values of the ticket's order, when it has one.

    Returns:
        The known values: the display name and each of its parts of at least three
        characters, the email, the phone, and the order's identifiers and address.
    """
    name_parts = tuple(
        part for part in contact.display_name.split() if len(part) >= NAME_PART_MIN_LENGTH
    )
    values = [
        KnownValue(PseudonymType.NAME, contact.display_name),
        *(KnownValue(PseudonymType.NAME, part) for part in name_parts),
        KnownValue(PseudonymType.EMAIL, contact.email),
        KnownValue(PseudonymType.PHONE, contact.phone),
    ]
    if references is not None:
        values.extend(
            (
                KnownValue(PseudonymType.ORDER_ID, references.order_id),
                KnownValue(PseudonymType.TRANSACTION_ID, references.transaction_id),
                KnownValue(PseudonymType.ADDRESS, references.shipping_address),
            )
        )
        if references.tracking_code is not None:
            values.append(KnownValue(PseudonymType.TRACKING_ID, references.tracking_code))
    return tuple(values)


async def _load_records(
    records: CustomerRecords, message: MessageToPseudonymize
) -> tuple[CustomerContact, OrderReferences | None]:
    # Without its known values the second step cannot run, so the run fails closed.
    contact = await records.load_contact(message.customer_id)
    if contact is None:
        raise DetectorError
    if message.order_id is None:
        return contact, None
    references = await records.load_order_references(message.customer_id, message.order_id)
    if references is None:
        raise DetectorError
    return contact, references


def _entry_keys(entries: tuple[PseudonymEntry, ...]) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (entry.pseudonym, entry.pseudonym_type.value, entry.original_value) for entry in entries
    )

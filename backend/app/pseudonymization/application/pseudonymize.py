"""Pseudonymize the message of a ticket before any text derived from it leaves backend.

This is the first of the two functions of the public API of pseudonymization (ADR-0010,
Storage and lifecycle, item 6). It runs as the first step of every suggestion job.
"""

from dataclasses import dataclass
from datetime import datetime

from app.accounts import CustomerId
from app.audit import (
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditLog,
    AuditTicketId,
    AuditValue,
)
from app.commerce import (
    CustomerContact,
    CustomerRecords,
    OrderId,
    OrderReferences,
)
from app.platform import (
    Clock,
    EventName,
    EventRecorder,
    IdGenerator,
    SpanName,
    StepTracer,
    TraceContext,
    TransactionRunner,
)
from app.pseudonymization.domain import (
    Detection,
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
    drop_product_names,
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
        """Pseudonymize the message, keep one map per ticket, and audit the outcome.

        The first successful run inserts the map; every later run reads it and must compute
        the same one (ADR-0010, Storage and lifecycle, item 2). A run that fails keeps no map
        row: its audit entry is written in a transaction of its own.

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
            try:
                result = await self._pseudonymize(message)
            except PseudonymizationError as error:
                await self._audit_failure(message.ticket_id, error)
                self._record_failure(message.ticket_id, error)
                raise
            self._ports.steps.record_pseudonym_count(len(result.entries))
        return result.text

    async def _pseudonymize(self, message: MessageToPseudonymize) -> PseudonymizedMessage:
        async with self._transactions.begin() as transaction:
            stores = transaction.stores
            known_values = build_known_values(*await _load_records(stores.records, message))
            product_names = await stores.records.load_product_names()
            result = build_pseudonymized_message(
                message.message, self._detect(message.message, known_values, product_names)
            )
            await _keep_one_map(
                stores.pseudonyms, message.ticket_id, result.entries, self._ports.clock.now()
            )
            await stores.audit.append(self._success_entry(message.ticket_id, result))
            await transaction.commit()
        return result

    def _detect(
        self, message: str, known_values: tuple[KnownValue, ...], product_names: tuple[str, ...]
    ) -> tuple[Detection, ...]:
        detections: list[Detection] = []
        for detector in self._ports.detectors:
            try:
                detections.extend(detector.detect(message, known_values))
            except Exception as error:
                # Any exception of any detector fails closed (backend ticket workflow
                # design, Pseudonymization, item 1).
                raise DetectorError from error
        return resolve_overlaps(drop_product_names(detections, message, product_names))

    async def _audit_failure(self, ticket_id: MapTicketId, error: PseudonymizationError) -> None:
        # The transaction of the failed run rolled back, so no row of its map is kept
        # (ADR-0010, Storage and lifecycle, items 3 and 4).
        async with self._transactions.begin() as transaction:
            await transaction.stores.audit.append(self._failure_entry(ticket_id, error))
            await transaction.commit()

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
        record = (
            self._ports.events.record_handled_input
            if isinstance(error, PseudonymizedTextTooLongError)
            else self._ports.events.record
        )
        record(
            EventName.PSEUDONYMIZATION_FAILED, ticket_id=ticket_id, reason_code=error.reason.value
        )


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


async def _keep_one_map(
    pseudonyms: PseudonymMapStore,
    ticket_id: MapTicketId,
    entries: tuple[PseudonymEntry, ...],
    created_at: datetime,
) -> None:
    # Only a ticket without a map gets one; a ticket with a map is only compared. Reading
    # back after the insert also finds a different map that a concurrent first run stored.
    stored = await pseudonyms.load_entries(ticket_id)
    if not stored:
        await pseudonyms.insert_map(ticket_id, entries, created_at)
        stored = await pseudonyms.load_entries(ticket_id)
    if _entry_keys(stored) != _entry_keys(entries):
        raise StoredMapDiffersError


def _entry_keys(entries: tuple[PseudonymEntry, ...]) -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (entry.pseudonym, entry.pseudonym_type.value, entry.original_value) for entry in entries
    )

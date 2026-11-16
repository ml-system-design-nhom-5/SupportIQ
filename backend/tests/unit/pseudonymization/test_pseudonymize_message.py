"""Tests of `PseudonymizeMessage` and `RestorePseudonyms` with fakes of every port (SEC-36)."""

from dataclasses import dataclass

import pytest

from supportiq_backend.audit import AuditEventType
from supportiq_backend.commerce import OrderId
from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.pseudonymization import (
    Detector,
    DetectorError,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    MapTicketId,
    MessageToPseudonymize,
    PatternDetector,
    PseudonymizationError,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
    RestorePseudonyms,
)
from supportiq_backend.pseudonymization.domain import (
    Detection,
    DetectionSource,
    KnownValue,
    PseudonymEntry,
    PseudonymType,
)
from tests.unit.audit.fakes import FakeAuditLog
from tests.unit.platform.fakes import (
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.pseudonymization.fakes import (
    CONTACT,
    CUSTOMER_ID,
    REFERENCES,
    FakeCustomerRecords,
    FakePseudonymMapStore,
)

TICKET_ID = MapTicketId("TCK-1042")
MESSAGE = (
    "Hi, I am Lan Tran (lan.tran@example.test, +84 90 111 0001). Order ORD-20901 was sent "
    "with TRK-0000020901 to 12 Example Street, Ba Dinh, Hanoi. My card is 4111 1111 1111 1111."
)
SEEDED_VALUES = (
    CONTACT.display_name,
    CONTACT.email,
    CONTACT.phone,
    REFERENCES.order_id,
    "TRK-0000020901",
    REFERENCES.shipping_address,
    "4111 1111 1111 1111",
)
DETECTORS: tuple[Detector, ...] = (
    LiteralPlaceholderDetector(),
    KnownValueDetector(),
    PatternDetector(),
)


@dataclass(slots=True)
class FailingDetector:
    """A detector that cannot run, as a named-entity model that failed would."""

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Raise the error of a detector that cannot run."""
        del message, known_values
        raise DetectorError


@dataclass(slots=True)
class NamedEntityOf:
    """A named-entity step that finds one phrase as a name, as the model can for a product."""

    phrase: str

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Find the phrase where it first appears."""
        del known_values
        start = message.find(self.phrase)
        if start < 0:
            return ()
        end = start + len(self.phrase)
        return (Detection(start, end, PseudonymType.NAME, DetectionSource.NAMED_ENTITY),)


@dataclass(slots=True)
class CrashingDetector:
    """A detector whose library raises an exception of its own, not a `DetectorError`."""

    error: Exception

    def detect(
        self, message: str, known_values: tuple[KnownValue, ...], /
    ) -> tuple[Detection, ...]:
        """Raise the library's exception."""
        del message, known_values
        raise self.error


@dataclass(slots=True)
class Harness:
    """The use case with its fakes."""

    pseudonymize: PseudonymizeMessage
    pseudonyms: FakePseudonymMapStore
    audit: FakeAuditLog
    events: RecordingEventRecorder
    transactions: FakeTransactionRunner[PseudonymizationStores]


def build_harness(
    detectors: tuple[Detector, ...] = DETECTORS,
    records: FakeCustomerRecords | None = None,
    pseudonyms: FakePseudonymMapStore | None = None,
) -> Harness:
    store = pseudonyms or FakePseudonymMapStore()
    audit = FakeAuditLog()
    events = RecordingEventRecorder()
    transactions = FakeTransactionRunner(
        PseudonymizationStores(store, records or FakeCustomerRecords(), audit)
    )
    use_case = PseudonymizeMessage(
        transactions,
        PseudonymizationPorts(
            detectors=detectors,
            clock=FakeClock(),
            ids=SequentialIdGenerator(),
            traces=FixedTraceContext(),
            events=events,
            steps=RecordingStepTracer(),
        ),
    )
    return Harness(use_case, store, audit, events, transactions)


def ticket_message(message: str = MESSAGE) -> MessageToPseudonymize:
    return MessageToPseudonymize(TICKET_ID, message, CUSTOMER_ID, OrderId(REFERENCES.order_id))


@pytest.mark.anyio
@pytest.mark.parametrize("seeded_value", SEEDED_VALUES)
async def test_no_seeded_personal_value_remains_in_the_pseudonymized_text(
    seeded_value: str,
) -> None:
    harness = build_harness()

    text = await harness.pseudonymize.pseudonymize(ticket_message())

    assert seeded_value not in text


@pytest.mark.anyio
async def test_a_product_name_of_the_catalog_stays_as_written() -> None:
    message = "The Jordan Runner shoes are great."
    harness = build_harness(
        (*DETECTORS, NamedEntityOf("Jordan Runner")),
        FakeCustomerRecords(product_names=("Jordan Runner",)),
    )

    assert await harness.pseudonymize.pseudonymize(ticket_message(message)) == message


@pytest.mark.anyio
async def test_the_first_run_stores_the_map_and_audits_the_counts_by_type() -> None:
    harness = build_harness()

    await harness.pseudonymize.pseudonymize(ticket_message())

    stored = harness.pseudonyms.entries_by_ticket[TICKET_ID]
    (entry,) = harness.audit.entries
    assert stored["[NAME_1]"].original_value == "Lan Tran"
    assert entry.event_type is AuditEventType.MESSAGE_PSEUDONYMIZED
    assert entry.data["outcome"] == "succeeded"
    assert entry.data["card_count"] == 1
    assert harness.transactions.commit_count == 1


@pytest.mark.anyio
async def test_a_later_run_reuses_the_stored_map_and_gives_the_same_text() -> None:
    harness = build_harness()
    first = await harness.pseudonymize.pseudonymize(ticket_message())

    second = await harness.pseudonymize.pseudonymize(ticket_message())

    assert second == first


@pytest.mark.anyio
async def test_a_later_run_only_compares_and_never_inserts() -> None:
    harness = build_harness()
    await harness.pseudonymize.pseudonymize(ticket_message())

    await harness.pseudonymize.pseudonymize(ticket_message())

    assert harness.pseudonyms.insert_count == 1


@pytest.mark.anyio
async def test_a_stored_map_that_differs_fails_closed_and_adds_no_row() -> None:
    stored = PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Minh Le")
    pseudonyms = FakePseudonymMapStore({TICKET_ID: {"[NAME_1]": stored}})
    harness = build_harness(pseudonyms=pseudonyms)

    with pytest.raises(PseudonymizationError):
        await harness.pseudonymize.pseudonymize(ticket_message())

    assert harness.pseudonyms.entries_by_ticket[TICKET_ID] == {"[NAME_1]": stored}
    assert harness.pseudonyms.insert_count == 0


@pytest.mark.anyio
async def test_a_failure_rolls_its_run_back_and_audits_in_a_transaction_of_its_own() -> None:
    harness = build_harness((*DETECTORS, FailingDetector()))

    with pytest.raises(DetectorError):
        await harness.pseudonymize.pseudonymize(ticket_message())

    assert harness.transactions.rollback_count == 1
    assert harness.transactions.commit_count == 1


@pytest.mark.anyio
async def test_a_failing_detector_fails_closed_and_audits_the_failure() -> None:
    harness = build_harness((*DETECTORS, FailingDetector()))

    with pytest.raises(DetectorError):
        await harness.pseudonymize.pseudonymize(ticket_message())

    (entry,) = harness.audit.entries
    assert entry.data == {"outcome": "failed", "failure_reason": "detector_error"}
    assert harness.pseudonyms.entries_by_ticket == {}
    (event,) = harness.events.of(EventName.PSEUDONYMIZATION_FAILED)
    assert not event.is_handled_input


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error", [RuntimeError("model crashed"), ValueError("bad span"), KeyError("label")]
)
async def test_any_exception_of_a_detector_is_a_detector_error(error: Exception) -> None:
    harness = build_harness((*DETECTORS, CrashingDetector(error)))

    with pytest.raises(DetectorError) as caught:
        await harness.pseudonymize.pseudonymize(ticket_message())

    (entry,) = harness.audit.entries
    assert caught.value.__cause__ is error
    assert entry.data == {"outcome": "failed", "failure_reason": "detector_error"}
    assert harness.events.names() == (EventName.PSEUDONYMIZATION_FAILED,)


@pytest.mark.anyio
async def test_a_text_over_the_limit_fails_closed_with_a_warning() -> None:
    harness = build_harness()

    with pytest.raises(PseudonymizationError):
        await harness.pseudonymize.pseudonymize(ticket_message("ORD-20901 " * 500))

    (event,) = harness.events.of(EventName.PSEUDONYMIZATION_FAILED)
    assert event.is_handled_input
    assert harness.events.names() == (EventName.PSEUDONYMIZATION_FAILED,)


@pytest.mark.anyio
async def test_missing_known_values_fail_closed() -> None:
    harness = build_harness(records=FakeCustomerRecords(contact=None))

    with pytest.raises(DetectorError):
        await harness.pseudonymize.pseudonymize(ticket_message())


@pytest.mark.anyio
async def test_a_storage_error_is_no_pseudonymization_failure() -> None:
    harness = build_harness(
        pseudonyms=FakePseudonymMapStore(insert_failure=DatabaseUnavailableError())
    )

    with pytest.raises(DatabaseUnavailableError):
        await harness.pseudonymize.pseudonymize(ticket_message())

    assert harness.audit.entries == []
    assert harness.transactions.commit_count == 0


@pytest.mark.anyio
async def test_restore_logs_once_when_a_pseudonym_is_missing_from_the_map() -> None:
    pseudonyms = FakePseudonymMapStore(
        {TICKET_ID: {"[NAME_1]": PseudonymEntry("[NAME_1]", PseudonymType.NAME, "Lan Tran")}}
    )
    events = RecordingEventRecorder()
    restorer = RestorePseudonyms(pseudonyms, events)

    restored = await restorer.restore(TICKET_ID, ("Hi [NAME_1]", "[NAME_2] and [NAME_3]"))

    assert restored == ("Hi Lan Tran", "[NAME_2] and [NAME_3]")
    assert events.names() == (EventName.PSEUDONYM_RESTORE_FAILED,)

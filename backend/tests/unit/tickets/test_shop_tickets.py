"""Tests of the shop's ticket use cases with fake ports (ADR-0013, ERR-15, SEC-17)."""

from uuid import UUID

import pytest

from supportiq_backend.accounts import (
    AccountId,
    Authorizer,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
)
from supportiq_backend.commerce import OrderId, OrderNotFoundError
from supportiq_backend.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    IdempotencyKeyReusedError,
    StoredResponse,
)
from supportiq_backend.platform import (
    DatabaseUnavailableError,
    EventName,
    RequestContractError,
    SpanName,
)
from supportiq_backend.suggestions import (
    SuggestionStarter,
    SuggestionStarterPorts,
    SuggestionTrigger,
)
from supportiq_backend.tickets import (
    CreateShopTicket,
    CreateShopTicketPorts,
    GetShopTicket,
    HandlingMode,
    ListShopTickets,
    NewShopTicket,
    ShopTicket,
    ShopTicketStores,
    TicketId,
    TicketNotFoundError,
    TicketPosition,
    build_new_shop_ticket,
)
from tests.unit.commerce.fakes import FakeCommerceGateway, build_order
from tests.unit.idempotency.fakes import FakeIdempotencyStore
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeClock,
    FakeTransactionRunner,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.suggestions.fakes import (
    FakeSuggestionStore,
    FakeTicketLinks,
    RecordingSuggestionQueue,
)
from tests.unit.tickets.fakes import FIRST_TICKET_ID, FakeTicketStore

pytestmark = pytest.mark.anyio

CUSTOMER_ID = CustomerId("10000000-0000-4000-8000-000000000001")
OTHER_CUSTOMER_ID = CustomerId("10000000-0000-4000-8000-000000000002")
CUSTOMER = CustomerPrincipal(AccountId("account-of-the-customer"), CUSTOMER_ID)
OTHER_CUSTOMER = CustomerPrincipal(AccountId("account-of-the-other"), OTHER_CUSTOMER_ID)
STAFF = InternalPrincipal(AccountId("account-of-the-staff"), InternalRole.STAFF)
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000001"))
ORDER_ID = OrderId("ORD-20901")
OTHER_ORDER_ID = OrderId("ORD-20902")
MESSAGE = "  Where is my parcel?\n"
NEW_TICKET = NewShopTicket(ORDER_ID, MESSAGE)
RETENTION_MS = 86_400_000
FIRST_TICKET = ShopTicket(FIRST_TICKET_ID, ORDER_ID, "First", FAKE_CLOCK_START)
SECOND_TICKET = ShopTicket(TicketId("TCK-1002"), OTHER_ORDER_ID, "Second", FAKE_CLOCK_START)


def render_ticket_id(ticket: ShopTicket) -> StoredResponse:
    return StoredResponse(201, f"{ticket.ticket_id}|{ticket.created_at.isoformat()}")


def build_stores(
    tickets: FakeTicketStore | None = None, suggestions: FakeSuggestionStore | None = None
) -> ShopTicketStores:
    return ShopTicketStores(
        tickets=tickets or FakeTicketStore(),
        orders=FakeCommerceGateway(
            orders={CUSTOMER_ID: (build_order(ORDER_ID), build_order(OTHER_ORDER_ID))}
        ),
        idempotency=FakeIdempotencyStore(),
        suggestions=suggestions or FakeSuggestionStore(),
        links=FakeTicketLinks(),
    )


def build_starter(
    clock: FakeClock, events: RecordingEventRecorder, queue: RecordingSuggestionQueue
) -> SuggestionStarter:
    return SuggestionStarter(
        SuggestionStarterPorts(
            clock=clock,
            ids=SequentialIdGenerator(start=100),
            traces=FixedTraceContext(),
            events=events,
            queue=queue,
        )
    )


def build_create(
    transactions: FakeTransactionRunner[ShopTicketStores],
    events: RecordingEventRecorder | None = None,
    handling_mode: HandlingMode = HandlingMode.ASSISTED,
    steps: RecordingStepTracer | None = None,
    queue: RecordingSuggestionQueue | None = None,
) -> CreateShopTicket:
    recorder = events or RecordingEventRecorder()
    clock = FakeClock()
    return CreateShopTicket(
        transactions,
        CreateShopTicketPorts(
            guard=IdempotencyGuard(clock, RETENTION_MS),
            authorizer=Authorizer(recorder),
            clock=clock,
            ids=SequentialIdGenerator(),
            events=recorder,
            steps=steps or RecordingStepTracer(),
            starter=build_starter(clock, recorder, queue or RecordingSuggestionQueue()),
        ),
        handling_mode,
        render_ticket_id,
    )


def build_list(tickets: FakeTicketStore) -> ListShopTickets:
    return ListShopTickets(
        FakeTransactionRunner(build_stores(tickets)), Authorizer(RecordingEventRecorder())
    )


def build_get(tickets: FakeTicketStore) -> GetShopTicket:
    return GetShopTicket(
        FakeTransactionRunner(build_stores(tickets)), Authorizer(RecordingEventRecorder())
    )


async def test_creation_stores_the_message_exactly_as_written() -> None:
    tickets = FakeTicketStore()
    await build_create(FakeTransactionRunner(build_stores(tickets))).execute(
        CUSTOMER, NEW_TICKET, KEY
    )

    (record,) = tickets.inserted

    assert record.ticket.message == MESSAGE
    assert record.ticket.order_id == ORDER_ID
    assert record.customer_id == CUSTOMER_ID
    assert record.created_at == FAKE_CLOCK_START
    assert record.message_id == UUID(int=1)


@pytest.mark.parametrize("handling_mode", HandlingMode)
async def test_creation_uses_the_configured_handling_mode(handling_mode: HandlingMode) -> None:
    tickets = FakeTicketStore()
    use_case = build_create(
        FakeTransactionRunner(build_stores(tickets)), handling_mode=handling_mode
    )

    await use_case.execute(CUSTOMER, NEW_TICKET, KEY)

    assert tickets.inserted[0].handling_mode is handling_mode


async def test_creation_commits_once_and_returns_the_rendered_response() -> None:
    transactions = FakeTransactionRunner(build_stores())

    response = await build_create(transactions).execute(CUSTOMER, NEW_TICKET, KEY)

    assert response == StoredResponse(201, f"TCK-1001|{FAKE_CLOCK_START.isoformat()}")
    assert transactions.commit_count == 1


async def test_creation_records_the_event_with_the_ticket_id_only() -> None:
    events = RecordingEventRecorder()

    await build_create(FakeTransactionRunner(build_stores()), events).execute(
        CUSTOMER, NEW_TICKET, KEY
    )

    (created,) = events.of(EventName.TICKET_CREATED)
    assert created.attributes == {"ticket_id": FIRST_TICKET_ID}


async def test_creation_runs_in_the_span_of_its_step() -> None:
    steps = RecordingStepTracer()

    await build_create(FakeTransactionRunner(build_stores()), steps=steps).execute(
        CUSTOMER, NEW_TICKET, KEY
    )

    assert steps.steps == [SpanName.CREATE_TICKET]
    assert steps.tickets == [FIRST_TICKET_ID]


async def test_repeat_returns_the_first_response_and_creates_nothing_more() -> None:
    tickets = FakeTicketStore()
    events = RecordingEventRecorder()
    use_case = build_create(FakeTransactionRunner(build_stores(tickets)), events)

    first = await use_case.execute(CUSTOMER, NEW_TICKET, KEY)
    repeat = await use_case.execute(CUSTOMER, NEW_TICKET, KEY)

    assert repeat == first
    assert len(tickets.inserted) == 1
    assert len(events.of(EventName.TICKET_CREATED)) == 1


async def test_same_key_with_another_message_is_refused() -> None:
    tickets = FakeTicketStore()
    use_case = build_create(FakeTransactionRunner(build_stores(tickets)))
    await use_case.execute(CUSTOMER, NEW_TICKET, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await use_case.execute(CUSTOMER, NewShopTicket(ORDER_ID, "Another message"), KEY)

    assert len(tickets.inserted) == 1


async def test_same_key_with_another_order_is_refused() -> None:
    use_case = build_create(FakeTransactionRunner(build_stores()))
    await use_case.execute(CUSTOMER, NEW_TICKET, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await use_case.execute(CUSTOMER, NewShopTicket(OTHER_ORDER_ID, MESSAGE), KEY)


@pytest.mark.parametrize("order_id", [OrderId("ORD-99999"), OTHER_ORDER_ID])
async def test_order_that_is_not_the_callers_creates_nothing_and_commits_nothing(
    order_id: OrderId,
) -> None:
    tickets = FakeTicketStore()
    stores = build_stores(tickets)
    transactions = FakeTransactionRunner(stores)
    events = RecordingEventRecorder()

    with pytest.raises(OrderNotFoundError):
        await build_create(transactions, events).execute(
            OTHER_CUSTOMER, NewShopTicket(order_id, MESSAGE), KEY
        )

    assert tickets.inserted == []
    assert transactions.commit_count == 0
    assert transactions.rollback_count == 1
    assert events.of(EventName.TICKET_CREATED) == ()


async def test_failure_of_the_insert_rolls_back_and_records_no_event() -> None:
    tickets = FakeTicketStore(insert_failure=DatabaseUnavailableError())
    transactions = FakeTransactionRunner(build_stores(tickets))
    events = RecordingEventRecorder()

    with pytest.raises(DatabaseUnavailableError):
        await build_create(transactions, events).execute(CUSTOMER, NEW_TICKET, KEY)

    assert transactions.commit_count == 0
    assert transactions.rollback_count == 1
    assert events.of(EventName.TICKET_CREATED) == ()


async def test_failure_of_the_commit_records_no_event() -> None:
    transactions = FakeTransactionRunner(build_stores(), commit_failure=DatabaseUnavailableError())
    events = RecordingEventRecorder()

    with pytest.raises(DatabaseUnavailableError):
        await build_create(transactions, events).execute(CUSTOMER, NEW_TICKET, KEY)

    assert events.of(EventName.TICKET_CREATED) == ()


async def test_only_a_customer_can_create_a_ticket() -> None:
    use_case = build_create(FakeTransactionRunner(build_stores()))

    with pytest.raises(ForbiddenRoleError):
        use_case.authorize(STAFF)


def test_authorized_customer_is_returned_for_the_use_case() -> None:
    customer = build_create(FakeTransactionRunner(build_stores())).authorize(CUSTOMER)

    assert customer == CUSTOMER


@pytest.mark.parametrize("message", ["\x00", "before\x00after", "\ud800"])
def test_message_that_cannot_be_stored_is_an_invalid_request(message: str) -> None:
    with pytest.raises(RequestContractError) as caught:
        build_new_shop_ticket(ORDER_ID, message)

    assert caught.value.locations == ("body.message",)


def test_order_id_that_cannot_be_stored_stays_for_the_order_check() -> None:
    ticket = build_new_shop_ticket("ORD\x00", MESSAGE)

    assert ticket.order_id == "ORD\x00"


def test_new_ticket_keeps_the_message_unchanged() -> None:
    ticket = build_new_shop_ticket(ORDER_ID, MESSAGE)

    assert ticket.message == MESSAGE


@pytest.mark.parametrize("value", [NEW_TICKET, FIRST_TICKET], ids=["new-ticket", "shop-ticket"])
def test_repr_hides_the_message_and_the_order(value: object) -> None:
    text = repr(value)

    assert ORDER_ID not in text
    assert MESSAGE not in text
    assert "First" not in text


async def test_page_names_the_next_position_when_more_follow() -> None:
    tickets = FakeTicketStore(tickets={CUSTOMER_ID: (FIRST_TICKET, SECOND_TICKET)})

    page = await build_list(tickets).execute(CUSTOMER, None, None, 1)

    assert page.items == (FIRST_TICKET,)
    assert page.next_position == TicketPosition(FAKE_CLOCK_START, FIRST_TICKET_ID)


async def test_page_continues_after_the_position() -> None:
    tickets = FakeTicketStore(tickets={CUSTOMER_ID: (FIRST_TICKET, SECOND_TICKET)})
    position = TicketPosition(FAKE_CLOCK_START, FIRST_TICKET_ID)

    page = await build_list(tickets).execute(CUSTOMER, None, position, 1)

    assert page.items == (SECOND_TICKET,)
    assert page.next_position is None


async def test_list_filters_by_the_callers_order() -> None:
    tickets = FakeTicketStore(tickets={CUSTOMER_ID: (FIRST_TICKET, SECOND_TICKET)})

    page = await build_list(tickets).execute(CUSTOMER, OTHER_ORDER_ID, None, 20)

    assert page.items == (SECOND_TICKET,)


async def test_list_about_an_order_that_is_not_the_callers_is_not_found() -> None:
    with pytest.raises(OrderNotFoundError):
        await build_list(FakeTicketStore()).execute(OTHER_CUSTOMER, ORDER_ID, None, 20)


async def test_only_a_customer_can_list_tickets() -> None:
    with pytest.raises(ForbiddenRoleError):
        build_list(FakeTicketStore()).authorize(STAFF)


async def test_ticket_of_the_caller_is_returned() -> None:
    tickets = FakeTicketStore(tickets={CUSTOMER_ID: (FIRST_TICKET,)})

    ticket = await build_get(tickets).execute(CUSTOMER, FIRST_TICKET_ID)

    assert ticket == FIRST_TICKET


async def test_ticket_of_another_customer_is_not_found() -> None:
    tickets = FakeTicketStore(tickets={CUSTOMER_ID: (FIRST_TICKET,)})

    with pytest.raises(TicketNotFoundError):
        await build_get(tickets).execute(OTHER_CUSTOMER, FIRST_TICKET_ID)


async def test_failure_of_the_store_reaches_the_list() -> None:
    tickets = FakeTicketStore(load_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await build_list(tickets).execute(CUSTOMER, None, None, 20)


async def test_failure_of_the_store_reaches_the_read() -> None:
    tickets = FakeTicketStore(load_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await build_get(tickets).execute(CUSTOMER, FIRST_TICKET_ID)


async def test_failure_to_open_the_transaction_reaches_the_list_and_the_read() -> None:
    transactions = FakeTransactionRunner(build_stores(), begin_failure=DatabaseUnavailableError())
    authorizer = Authorizer(RecordingEventRecorder())

    with pytest.raises(DatabaseUnavailableError):
        await ListShopTickets(transactions, authorizer).execute(CUSTOMER, None, None, 20)
    with pytest.raises(DatabaseUnavailableError):
        await GetShopTicket(transactions, authorizer).execute(CUSTOMER, FIRST_TICKET_ID)


async def test_only_a_customer_can_read_a_ticket() -> None:
    with pytest.raises(ForbiddenRoleError):
        await build_get(FakeTicketStore()).execute(STAFF, FIRST_TICKET_ID)


@pytest.mark.anyio
async def test_an_assisted_ticket_gets_its_first_suggestion_in_the_same_transaction() -> None:
    suggestions = FakeSuggestionStore()
    transactions = FakeTransactionRunner(build_stores(suggestions=suggestions))
    queue = RecordingSuggestionQueue()
    create = build_create(transactions, queue=queue)

    await create.execute(CUSTOMER, NewShopTicket(OrderId(ORDER_ID), MESSAGE), KEY)

    (suggestion,) = suggestions.data.suggestions.values()
    assert suggestion.trigger is SuggestionTrigger.TICKET_CREATED
    assert suggestion.requested_by is None
    assert transactions.commit_count == 1
    assert queue.notifications == [(FIRST_TICKET_ID, suggestion.suggestion_id)]


@pytest.mark.anyio
async def test_a_manual_ticket_gets_no_suggestion_and_wakes_no_claim_loop() -> None:
    suggestions = FakeSuggestionStore()
    queue = RecordingSuggestionQueue()
    create = build_create(
        FakeTransactionRunner(build_stores(suggestions=suggestions)),
        handling_mode=HandlingMode.MANUAL,
        queue=queue,
    )

    await create.execute(CUSTOMER, NewShopTicket(OrderId(ORDER_ID), MESSAGE), KEY)

    assert suggestions.data.suggestions == {}
    assert queue.notifications == []

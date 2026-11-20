"""Repeats, concurrency, and failures of ticket creation, as the design's diagram says (ERR-15)."""

import asyncio
from http import HTTPStatus
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts import AccountId, Authorizer, CustomerId, CustomerPrincipal
from app.commerce import OrderId
from app.composition_root.tickets_wiring import build_shop_ticket_stores
from app.idempotency import (
    IdempotencyGuard,
    IdempotencyKey,
    StoredResponse,
)
from app.platform import EventName, UnexpectedFailureError
from app.platform.adapters.database import (
    SqlAlchemyTransactionRunner,
    create_session_factory,
)
from app.suggestions import SuggestionStarter, SuggestionStarterPorts
from app.tickets import (
    CreateShopTicket,
    CreateShopTicketPorts,
    HandlingMode,
    NewShopTicket,
    ShopTicket,
)
from tests.integration.application import (
    RunningBackend,
    build_settings,
    running_client,
)
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase, create_owner_engine
from tests.integration.tickets.shop_requests import (
    HELD_REQUEST_HASH,
    KEY,
    MESSAGE,
    OTHER_KEY,
    RETENTION_MS,
    SHORT_LOCK_MS,
    TICKETS,
    count_tickets,
    create_ticket,
    sign_in_as_new_customer,
)
from tests.unit.platform.fakes import (
    FAKE_CLOCK_START,
    FakeClock,
    FixedTraceContext,
    RecordingEventRecorder,
    RecordingStepTracer,
    SequentialIdGenerator,
)
from tests.unit.suggestions.fakes import RecordingProgressNotifier, RecordingSuggestionQueue

pytestmark = pytest.mark.anyio

TICKETS_OF_TWO_CUSTOMERS = 2


async def test_repeat_returns_the_exact_first_response_and_creates_no_second_ticket(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    first = await create_ticket(backend.client, headers, order_id)
    backend.clock.advance(1_000)

    repeat = await create_ticket(backend.client, headers, order_id)

    assert repeat.status_code == HTTPStatus.CREATED
    assert repeat.content == first.content
    assert await count_tickets(builder) == 1
    assert len(backend.events.of(EventName.TICKET_CREATED)) == 1


async def test_repeat_with_other_whitespace_and_key_order_is_the_same_request(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    request_headers = {**headers, "Idempotency-Key": KEY, "Content-Type": "application/json"}
    compact = f'{{"order_id":"{order_id}","message":"Hi"}}'
    spaced = f'{{\n  "message" : "Hi",\n  "order_id" : "{order_id}"\n}}\n'

    first = await backend.client.post(TICKETS, content=compact, headers=request_headers)
    repeat = await backend.client.post(TICKETS, content=spaced, headers=request_headers)

    assert repeat.content == first.content
    assert await count_tickets(builder) == 1


async def test_same_key_with_another_body_returns_409_and_creates_nothing(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    await create_ticket(backend.client, headers, order_id)

    response = await create_ticket(backend.client, headers, order_id, message="Another message")

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["type"] == "urn:supportiq:problem:idempotency-key-reused"
    assert await count_tickets(builder) == 1


async def test_message_that_differs_only_in_a_trailing_space_is_another_body(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    await create_ticket(backend.client, headers, order_id, message="Hi")

    response = await create_ticket(backend.client, headers, order_id, message="Hi ")

    assert response.status_code == HTTPStatus.CONFLICT


async def test_one_key_belongs_to_one_customer(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    other_id, other_headers = await sign_in_as_new_customer(builder)
    other_order = await builder.order_of_one_product(other_id)

    first = await create_ticket(backend.client, headers, order_id)
    second = await create_ticket(backend.client, other_headers, other_order)

    assert first.status_code == second.status_code == HTTPStatus.CREATED
    assert await count_tickets(builder) == TICKETS_OF_TWO_CUSTOMERS


async def test_two_new_keys_create_two_tickets(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    first = await create_ticket(backend.client, headers, order_id, key=KEY)
    second = await create_ticket(backend.client, headers, order_id, key=OTHER_KEY)

    assert first.json()["ticket_id"] != second.json()["ticket_id"]


async def test_two_concurrent_requests_on_two_connections_create_one_ticket(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    first, second = await asyncio.gather(
        create_ticket(backend.client, headers, order_id),
        create_ticket(backend.client, headers, order_id),
    )

    assert first.status_code == second.status_code == HTTPStatus.CREATED
    assert first.content == second.content
    assert await count_tickets(builder) == 1
    assert await builder.scalar("SELECT count(*) FROM customer_messages") == 1
    assert len(backend.events.of(EventName.TICKET_CREATED)) == 1


async def test_two_concurrent_requests_with_different_bodies_create_one_ticket(
    backend: RunningBackend, builder: DatabaseBuilder, headers: dict[str, str], order_id: str
) -> None:
    responses = await asyncio.gather(
        create_ticket(backend.client, headers, order_id, message="First"),
        create_ticket(backend.client, headers, order_id, message="Second"),
    )

    assert sorted(response.status_code for response in responses) == [
        HTTPStatus.CREATED,
        HTTPStatus.CONFLICT,
    ]
    assert await count_tickets(builder) == 1


async def test_wait_for_the_same_key_longer_than_the_lock_timeout_returns_503(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    order_id: str,
) -> None:
    settings = build_settings(worker_database, database_lock_timeout_ms=SHORT_LOCK_MS)
    account_id = await builder.scalar("SELECT account_id FROM accounts")

    async with (
        running_client(settings, RecordingEventRecorder(), FakeClock()) as client,
        app_engine.begin() as holder,
    ):
        await holder.execute(
            text(
                "INSERT INTO idempotency_records "
                "(account_id, operation_id, idempotency_key, request_hash, created_at) "
                "VALUES (:account_id, 'createShopTicket', :key, :request_hash, :now)"
            ),
            {
                "account_id": account_id,
                "key": KEY,
                "request_hash": HELD_REQUEST_HASH,
                "now": FAKE_CLOCK_START,
            },
        )
        response = await create_ticket(client, headers, order_id)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.json()["type"] == "urn:supportiq:problem:not-ready"
    assert await count_tickets(builder) == 0


async def test_lock_wait_on_the_ticket_insert_rolls_back_the_idempotency_record(
    worker_database: WorkerDatabase,
    builder: DatabaseBuilder,
    headers: dict[str, str],
    order_id: str,
) -> None:
    settings = build_settings(worker_database, database_lock_timeout_ms=SHORT_LOCK_MS)
    owner_engine = create_owner_engine(worker_database)

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        async with owner_engine.begin() as holder:
            await holder.execute(text("LOCK TABLE tickets IN ACCESS EXCLUSIVE MODE"))
            refused = await create_ticket(client, headers, order_id)
        records = await builder.scalar("SELECT count(*) FROM idempotency_records")
        retried = await create_ticket(client, headers, order_id)
    await owner_engine.dispose()

    assert refused.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert records == 0
    assert retried.status_code == HTTPStatus.CREATED


async def test_failure_after_the_insert_leaves_no_record_in_postgresql(
    app_engine: AsyncEngine, builder: DatabaseBuilder, customer_id: UUID, order_id: str
) -> None:
    def failing_render(_ticket: ShopTicket) -> StoredResponse:
        raise UnexpectedFailureError

    clock = FakeClock()
    events = RecordingEventRecorder()
    use_case = CreateShopTicket(
        SqlAlchemyTransactionRunner(create_session_factory(app_engine), build_shop_ticket_stores),
        CreateShopTicketPorts(
            guard=IdempotencyGuard(clock, RETENTION_MS),
            authorizer=Authorizer(events),
            clock=clock,
            ids=SequentialIdGenerator(),
            events=events,
            steps=RecordingStepTracer(),
            starter=SuggestionStarter(
                SuggestionStarterPorts(
                    clock=clock,
                    ids=SequentialIdGenerator(start=100),
                    traces=FixedTraceContext(),
                    events=events,
                    queue=RecordingSuggestionQueue(),
                    progress=RecordingProgressNotifier(),
                )
            ),
        ),
        HandlingMode.ASSISTED,
        failing_render,
    )
    account_id = await builder.scalar("SELECT account_id FROM accounts")
    caller = CustomerPrincipal(AccountId(str(account_id)), CustomerId(str(customer_id)))

    with pytest.raises(UnexpectedFailureError):
        await use_case.execute(
            caller, NewShopTicket(OrderId(order_id), MESSAGE), IdempotencyKey(UUID(KEY))
        )

    assert await count_tickets(builder) == 0
    assert await builder.scalar("SELECT count(*) FROM customer_messages") == 0
    assert await builder.scalar("SELECT count(*) FROM suggestions") == 0
    assert await builder.scalar("SELECT count(*) FROM idempotency_records") == 0


async def test_refused_order_is_not_remembered_so_the_key_runs_again(
    backend: RunningBackend, headers: dict[str, str], order_id: str
) -> None:
    await create_ticket(backend.client, headers, "ORD-99999")

    response = await create_ticket(backend.client, headers, order_id)

    assert response.status_code == HTTPStatus.CREATED

"""The wiring of tickets: its stores, use cases, and routers (ARCH-21)."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from supportiq_backend.accounts.adapters.staff_directory import PostgresStaffDirectory
from supportiq_backend.audit.adapters.audit_log import PostgresAuditLog
from supportiq_backend.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from supportiq_backend.commerce.adapters.customer_records import PostgresCustomerRecords
from supportiq_backend.commerce.api.shop import to_money, to_order_view
from supportiq_backend.composition_root.accounts_wiring import AccountsWiring
from supportiq_backend.composition_root.shared_ports import SharedPorts
from supportiq_backend.composition_root.suggestions_wiring import SuggestionsWiring
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from supportiq_backend.platform import EventRecorder
from supportiq_backend.platform.adapters.database import SqlAlchemyTransactionRunner
from supportiq_backend.platform.settings import HandlingModeSetting, Settings
from supportiq_backend.pseudonymization import RestorePseudonyms
from supportiq_backend.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from supportiq_backend.suggestions.adapters.suggestion_store import PostgresSuggestionStore
from supportiq_backend.tickets import (
    ConsolePorts,
    ConsoleStores,
    CreateEscalation,
    CreateReplyProposal,
    CreateShopTicket,
    CreateShopTicketPorts,
    GetConsoleTicket,
    GetShopTicket,
    HandlingMode,
    ListConsoleTickets,
    ListShopTickets,
    RecordTicketView,
    SendReply,
    ShopTicketStores,
)
from supportiq_backend.tickets.adapters.console_store import (
    PostgresConsoleTicketStore,
    PostgresTicketLinks,
)
from supportiq_backend.tickets.adapters.escalation_store import PostgresEscalationStore
from supportiq_backend.tickets.adapters.proposal_store import PostgresReplyProposalStore
from supportiq_backend.tickets.adapters.reply_store import PostgresReplyStore
from supportiq_backend.tickets.adapters.ticket_store import PostgresTicketStore
from supportiq_backend.tickets.api.console import (
    ConsoleTicketRoutes,
    build_console_tickets_router,
    render_created_escalation,
    render_created_proposal,
    render_sent_reply,
)
from supportiq_backend.tickets.api.order_views import OrderViewMappers
from supportiq_backend.tickets.api.shop import (
    ShopTicketRoutes,
    build_shop_tickets_router,
    render_created_ticket,
)


def to_handling_mode(setting: HandlingModeSetting) -> HandlingMode:
    """Turn the setting into the handling mode that the tickets feature names.

    Args:
        setting: The validated setting.

    Returns:
        The handling mode with the same value.
    """
    return HandlingMode(setting.value)


def build_shop_ticket_stores(session: AsyncSession) -> ShopTicketStores:
    """Build the stores of the shop's ticket use cases on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ShopTicketStores(
        tickets=PostgresTicketStore(session),
        orders=PostgresCommerceGateway(session),
        idempotency=PostgresIdempotencyStore(session),
        suggestions=PostgresSuggestionStore(session),
        links=PostgresTicketLinks(session),
    )


class ConsoleStoreBuilder:
    """Build the stores of the console use cases on one session, so all commit together."""

    def __init__(self, events: EventRecorder) -> None:
        """Keep the event recorder of the restorer.

        Args:
            events: Where a pseudonym missing from a map is recorded.
        """
        self._events = events

    def __call__(self, session: AsyncSession) -> ConsoleStores:
        """Build the stores; the restorer reads the map in the same transaction (ADR-0010).

        Args:
            session: The session of the transaction.

        Returns:
            The stores.
        """
        return ConsoleStores(
            tickets=PostgresConsoleTicketStore(session),
            replies=PostgresReplyStore(session),
            proposals=PostgresReplyProposalStore(session),
            escalations=PostgresEscalationStore(session),
            suggestions=PostgresSuggestionStore(session),
            links=PostgresTicketLinks(session),
            records=PostgresCustomerRecords(session),
            staff=PostgresStaffDirectory(session),
            restorer=RestorePseudonyms(PostgresPseudonymMapStore(session), self._events),
            idempotency=PostgresIdempotencyStore(session),
            audit=PostgresAuditLog(session),
        )


def wire_tickets(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    accounts: AccountsWiring,
    suggestions: SuggestionsWiring,
) -> tuple[APIRouter, ...]:
    """Create the use cases of tickets and their routers.

    Args:
        settings: The validated settings.
        session_factory: The session factory of the replicas.
        shared: The shared ports.
        accounts: The role checks and the session dependency.
        suggestions: The starter of suggestions and the ai-service client.

    Returns:
        The routers of the shop's and the console's ticket operations.
    """
    return (
        _wire_shop(settings, session_factory, shared, accounts, suggestions),
        _wire_console(session_factory, shared, accounts, suggestions),
    )


def _wire_shop(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    accounts: AccountsWiring,
    suggestions: SuggestionsWiring,
) -> APIRouter:
    transactions = SqlAlchemyTransactionRunner(session_factory, build_shop_ticket_stores)
    return build_shop_tickets_router(
        ShopTicketRoutes(
            list_tickets=ListShopTickets(transactions, accounts.authorizer),
            create_ticket=CreateShopTicket(
                transactions,
                CreateShopTicketPorts(
                    guard=shared.guard,
                    authorizer=accounts.authorizer,
                    clock=shared.clock,
                    ids=shared.ids,
                    events=shared.events,
                    steps=shared.steps,
                    starter=suggestions.starter,
                ),
                to_handling_mode(settings.default_handling_mode),
                render_created_ticket,
            ),
            get_ticket=GetShopTicket(transactions, accounts.authorizer),
            check_origin=accounts.check_origin,
            current_session=accounts.current_session,
        )
    )


def _wire_console(
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    accounts: AccountsWiring,
    suggestions: SuggestionsWiring,
) -> APIRouter:
    transactions = SqlAlchemyTransactionRunner(session_factory, ConsoleStoreBuilder(shared.events))
    ports = ConsolePorts(
        authorizer=accounts.authorizer,
        guard=shared.guard,
        clock=shared.clock,
        ids=shared.ids,
        traces=shared.traces,
        events=shared.events,
        steps=shared.steps,
        starter=suggestions.starter,
        ai_service=suggestions.ai_service,
    )
    return build_console_tickets_router(
        ConsoleTicketRoutes(
            list_tickets=ListConsoleTickets(transactions, ports),
            get_ticket=GetConsoleTicket(transactions, ports),
            record_view=RecordTicketView(transactions, ports),
            create_suggestion=suggestions.create_suggestion,
            create_proposal=CreateReplyProposal(transactions, ports, render_created_proposal),
            send_reply=SendReply(transactions, ports, render_sent_reply),
            create_escalation=CreateEscalation(transactions, ports, render_created_escalation),
            check_origin=accounts.check_origin,
            current_session=accounts.current_session,
            order_views=OrderViewMappers(to_order_view=to_order_view, to_money=to_money),
        )
    )

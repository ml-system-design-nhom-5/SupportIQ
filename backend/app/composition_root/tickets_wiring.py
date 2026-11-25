"""The wiring of tickets: its stores, use cases, and routers (ARCH-21)."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounts.adapters.staff_directory import PostgresStaffDirectory
from app.audit.adapters.audit_log import PostgresAuditLog
from app.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from app.commerce.adapters.customer_records import PostgresCustomerRecords
from app.commerce.api.shop import to_money, to_order_view
from app.composition_root.accounts_wiring import AccountsWiring
from app.composition_root.shared_ports import SharedPorts
from app.composition_root.suggestions_wiring import SuggestionsWiring
from app.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from app.platform import EventRecorder
from app.platform.adapters.database import SqlAlchemyTransactionRunner
from app.platform.settings import HandlingModeSetting, Settings
from app.pseudonymization import RestorePseudonyms
from app.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from app.suggestions.adapters.suggestion_store import PostgresSuggestionStore
from app.suggestions.api.admin import to_asset_versions_view
from app.tickets import (
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
from app.tickets.adapters.console_store import (
    PostgresConsoleTicketStore,
    PostgresTicketLinks,
)
from app.tickets.adapters.escalation_store import PostgresEscalationStore
from app.tickets.adapters.proposal_store import PostgresReplyProposalStore
from app.tickets.adapters.reply_store import PostgresReplyStore
from app.tickets.adapters.ticket_state_store import PostgresTicketStateStore
from app.tickets.adapters.ticket_store import PostgresTicketStore
from app.tickets.api.console import ConsoleTicketRoutes, build_console_tickets_router
from app.tickets.api.console_action_routes import (
    ConsoleActionRoutes,
    build_console_actions_router,
    render_created_escalation,
    render_created_proposal,
    render_sent_reply,
)
from app.tickets.api.console_view_mappers import ConsoleViewMappers
from app.tickets.api.order_views import OrderViewMappers
from app.tickets.api.shop import (
    ShopTicketRoutes,
    build_shop_tickets_router,
    render_created_ticket,
)

# The mappings of commerce and suggestions that the console's views reuse (CODE-55).
CONSOLE_VIEW_MAPPERS = ConsoleViewMappers(
    orders=OrderViewMappers(to_order_view=to_order_view, to_money=to_money),
    to_asset_versions_view=to_asset_versions_view,
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
            ticket_states=PostgresTicketStateStore(session),
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
        The routers of the shop's ticket operations, of the console's ticket reads and
        requests, and of the console's staff actions.
    """
    return (
        _wire_shop(settings, session_factory, shared, accounts, suggestions),
        *_wire_console(session_factory, shared, accounts, suggestions),
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
) -> tuple[APIRouter, APIRouter]:
    transactions = SqlAlchemyTransactionRunner(session_factory, ConsoleStoreBuilder(shared.events))
    ports = _build_console_ports(shared, accounts, suggestions)
    tickets_router = build_console_tickets_router(
        ConsoleTicketRoutes(
            list_tickets=ListConsoleTickets(transactions, ports),
            get_ticket=GetConsoleTicket(transactions, ports),
            record_view=RecordTicketView(transactions, ports),
            create_suggestion=suggestions.create_suggestion,
            check_origin=accounts.check_origin,
            current_session=accounts.current_session,
            views=CONSOLE_VIEW_MAPPERS,
        )
    )
    return tickets_router, _build_console_actions_router(transactions, ports, accounts)


def _build_console_actions_router(
    transactions: SqlAlchemyTransactionRunner[ConsoleStores],
    ports: ConsolePorts,
    accounts: AccountsWiring,
) -> APIRouter:
    return build_console_actions_router(
        ConsoleActionRoutes(
            create_proposal=CreateReplyProposal(transactions, ports, render_created_proposal),
            send_reply=SendReply(transactions, ports, render_sent_reply),
            create_escalation=CreateEscalation(transactions, ports, render_created_escalation),
            check_origin=accounts.check_origin,
            current_session=accounts.current_session,
        )
    )


def _build_console_ports(
    shared: SharedPorts, accounts: AccountsWiring, suggestions: SuggestionsWiring
) -> ConsolePorts:
    return ConsolePorts(
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

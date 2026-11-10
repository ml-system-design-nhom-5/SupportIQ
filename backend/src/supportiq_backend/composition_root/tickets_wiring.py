"""The wiring of tickets: its stores, use cases, and router (ARCH-21)."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from supportiq_backend.commerce.adapters.commerce_gateway import PostgresCommerceGateway
from supportiq_backend.composition_root.accounts_wiring import AccountsWiring
from supportiq_backend.composition_root.shared_ports import SharedPorts
from supportiq_backend.idempotency.adapters.idempotency_store import PostgresIdempotencyStore
from supportiq_backend.platform.adapters.database import SqlAlchemyTransactionRunner
from supportiq_backend.platform.settings import HandlingModeSetting, Settings
from supportiq_backend.tickets import (
    CreateShopTicket,
    CreateShopTicketPorts,
    GetShopTicket,
    HandlingMode,
    ListShopTickets,
    ShopTicketStores,
)
from supportiq_backend.tickets.adapters.ticket_store import PostgresTicketStore
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
    """Build the stores of the ticket use cases on one session, so all commit together.

    Args:
        session: The session of the transaction.

    Returns:
        The stores.
    """
    return ShopTicketStores(
        tickets=PostgresTicketStore(session),
        orders=PostgresCommerceGateway(session),
        idempotency=PostgresIdempotencyStore(session),
    )


def wire_tickets(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shared: SharedPorts,
    accounts: AccountsWiring,
) -> APIRouter:
    """Create the use cases of tickets and their router.

    Args:
        settings: The validated settings.
        session_factory: The session factory of the replicas.
        shared: The shared ports.
        accounts: The role checks and the session dependency.

    Returns:
        The router of the shop's ticket operations.
    """
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
                ),
                to_handling_mode(settings.default_handling_mode),
                render_created_ticket,
            ),
            get_ticket=GetShopTicket(transactions, accounts.authorizer),
            check_origin=accounts.check_origin,
            current_session=accounts.current_session,
        )
    )

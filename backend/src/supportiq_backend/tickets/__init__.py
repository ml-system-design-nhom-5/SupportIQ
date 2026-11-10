"""Public API of tickets: tickets and customer messages (ARCH-17)."""

from supportiq_backend.tickets.application import (
    CreateShopTicket,
    CreateShopTicketPorts,
    GetShopTicket,
    ListShopTickets,
    ShopTicketStores,
)
from supportiq_backend.tickets.domain import (
    HandlingMode,
    NewShopTicket,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketNotFoundError,
    TicketPage,
    TicketPosition,
    TicketSource,
    TicketStatus,
    TicketStore,
    build_new_shop_ticket,
)

__all__ = [
    "CreateShopTicket",
    "CreateShopTicketPorts",
    "GetShopTicket",
    "HandlingMode",
    "ListShopTickets",
    "NewShopTicket",
    "ShopTicket",
    "ShopTicketRecord",
    "ShopTicketStores",
    "TicketId",
    "TicketNotFoundError",
    "TicketPage",
    "TicketPosition",
    "TicketSource",
    "TicketStatus",
    "TicketStore",
    "build_new_shop_ticket",
]

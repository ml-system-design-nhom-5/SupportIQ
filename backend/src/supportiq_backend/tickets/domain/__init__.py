"""Domain of tickets: shop tickets and the `TicketStore` port."""

from supportiq_backend.tickets.domain.errors import TicketNotFoundError
from supportiq_backend.tickets.domain.ports import TicketStore
from supportiq_backend.tickets.domain.tickets import (
    HandlingMode,
    NewShopTicket,
    ShopTicket,
    ShopTicketRecord,
    TicketId,
    TicketPage,
    TicketPosition,
    TicketSource,
    TicketStatus,
    build_new_shop_ticket,
)

__all__ = [
    "HandlingMode",
    "NewShopTicket",
    "ShopTicket",
    "ShopTicketRecord",
    "TicketId",
    "TicketNotFoundError",
    "TicketPage",
    "TicketPosition",
    "TicketSource",
    "TicketStatus",
    "TicketStore",
    "build_new_shop_ticket",
]

"""Use cases of tickets: the shop's tickets and the console workflow."""

from supportiq_backend.tickets.application.console import (
    ConsolePorts,
    ConsoleStores,
    GetConsoleTicket,
    ListConsoleTickets,
)
from supportiq_backend.tickets.application.replies import SendReply
from supportiq_backend.tickets.application.shop_tickets import (
    CreateShopTicket,
    CreateShopTicketPorts,
    GetShopTicket,
    ListShopTickets,
    ShopTicketStores,
)
from supportiq_backend.tickets.application.ticket_views import RecordTicketView

__all__ = [
    "ConsolePorts",
    "ConsoleStores",
    "CreateShopTicket",
    "CreateShopTicketPorts",
    "GetConsoleTicket",
    "GetShopTicket",
    "ListConsoleTickets",
    "ListShopTickets",
    "RecordTicketView",
    "SendReply",
    "ShopTicketStores",
]

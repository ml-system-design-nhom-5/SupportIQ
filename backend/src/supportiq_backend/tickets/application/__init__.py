"""Use cases of tickets: the shop's tickets and the console workflow."""

from supportiq_backend.tickets.application.console import GetConsoleTicket, ListConsoleTickets
from supportiq_backend.tickets.application.console_ports import ConsolePorts, ConsoleStores
from supportiq_backend.tickets.application.escalations import CreateEscalation
from supportiq_backend.tickets.application.proposals import CreateReplyProposal
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
    "CreateEscalation",
    "CreateReplyProposal",
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

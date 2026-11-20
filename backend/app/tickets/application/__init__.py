"""Use cases of tickets: the shop's tickets and the console workflow."""

from app.tickets.application.console import GetConsoleTicket, ListConsoleTickets
from app.tickets.application.console_ports import ConsolePorts, ConsoleStores
from app.tickets.application.escalations import CreateEscalation
from app.tickets.application.proposals import CreateReplyProposal
from app.tickets.application.replies import SendReply
from app.tickets.application.shop_tickets import (
    CreateShopTicket,
    CreateShopTicketPorts,
    GetShopTicket,
    ListShopTickets,
    ShopTicketStores,
)
from app.tickets.application.ticket_views import RecordTicketView

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

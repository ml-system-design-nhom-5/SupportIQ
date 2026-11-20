"""Reply proposals: replies that staff prepare for a manager to send (contracts v1 design).

A proposal never reaches the customer; only `sendReply` writes a reply (FR-04). Its body and
note are Confidential, so the classes that hold them have no generated `repr` (LOG-29).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from app.accounts import AccountId
from app.tickets.domain.reply_requests import (
    ProposalId,
    ProposalRequest,
    ReplyBasis,
)
from app.tickets.domain.tickets import TicketId


@dataclass(frozen=True, slots=True, repr=False)
class ReplyProposal:
    """A reply proposal as stored and as the console shows it; inserted once, never updated.

    Attributes:
        proposal_id: The identifier.
        ticket_id: The ticket, `awaiting_approval` from then on until a manager sends a reply.
        request: The body that staff proposed, on its basis.
        proposed_by: The staff member who submitted it.
        created_at: When it was submitted.
    """

    proposal_id: ProposalId
    ticket_id: TicketId
    request: ProposalRequest
    proposed_by: AccountId
    created_at: datetime


@dataclass(frozen=True, slots=True, repr=False)
class SentProposal:
    """The ticket's proposal that a manager sends, with the body that the manager sends.

    Attributes:
        basis: Always `reply_proposal`.
        proposal: The proposal of the ticket.
        body: The text that the customer reads: the proposed body, as is or edited.
    """

    basis: ClassVar[ReplyBasis] = ReplyBasis.REPLY_PROPOSAL
    proposal: ReplyProposal
    body: str


# A reply body whose proposal is resolved: a body on its own basis, or the ticket's proposal
# with the body that the manager sends.
type ResolvedReply = ProposalRequest | SentProposal

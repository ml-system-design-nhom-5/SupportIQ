"""The reply proposal port of tickets on `reply_proposals` (contracts v1 design).

A ticket has at most one proposal: the state machine moves it from `open` to
`awaiting_approval` once, and the proposal is inserted in the same transaction. A proposal is
never updated, and it never reaches the customer (FR-04).
"""

from typing import assert_never
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts import AccountId
from app.platform import UnexpectedFailureError
from app.platform.persistence import parse_stored_enum
from app.suggestions import SuggestionId
from app.tickets.adapters.identifiers import (
    to_optional_suggestion_id,
    to_optional_uuid,
)
from app.tickets.adapters.tables import ReplyProposalRow
from app.tickets.domain import (
    AiDraftReply,
    NoAiDraftReply,
    ProposalId,
    ProposalRequest,
    RejectedAiDraftReply,
    ReplyBasis,
    ReplyProposal,
    StaffReasonCode,
    TicketId,
)


class PostgresReplyProposalStore:
    """Implement the `ReplyProposalStore` port in the transaction of one session."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind the store to the session of a transaction.

        Args:
            session: The session of the use case's transaction.
        """
        self._session = session

    async def insert_proposal(self, proposal: ReplyProposal) -> None:
        """Insert a proposal; it is never updated.

        Args:
            proposal: The proposal.
        """
        request = proposal.request
        await self._session.execute(
            insert(ReplyProposalRow).values(
                proposal_id=proposal.proposal_id,
                ticket_id=proposal.ticket_id,
                basis=request.basis.value,
                suggestion_id=to_optional_uuid(request.suggestion_id),
                acknowledged_warning_ids=sorted(request.acknowledged_warning_ids),
                staff_reason_codes=[code.value for code in request.staff_reason_codes],
                proposed_by_account_id=UUID(proposal.proposed_by),
                created_at=proposal.created_at,
                body=request.body,
                note=request.note,
            )
        )

    async def load_proposal(self, ticket_id: TicketId) -> ReplyProposal | None:
        """Load the proposal of a ticket.

        Args:
            ticket_id: The ticket.

        Returns:
            The proposal, or None before staff submit one.

        Raises:
            UnexpectedFailureError: The stored proposal breaks an invariant of its basis, or a
                stored text is no value of its enum.
        """
        rows = await self._session.scalars(
            select(ReplyProposalRow).where(ReplyProposalRow.ticket_id == ticket_id)
        )
        row = rows.one_or_none()
        if row is None:
            return None
        return ReplyProposal(
            proposal_id=ProposalId(row.proposal_id),
            ticket_id=TicketId(row.ticket_id),
            request=_to_request(row),
            proposed_by=AccountId(str(row.proposed_by_account_id)),
            created_at=row.created_at,
        )


def _to_request(row: ReplyProposalRow) -> ProposalRequest:
    reason_codes = tuple(
        parse_stored_enum(StaffReasonCode, code) for code in row.staff_reason_codes
    )
    basis = parse_stored_enum(ReplyBasis, row.basis)
    match basis:
        case ReplyBasis.AI_DRAFT:
            return AiDraftReply(
                body=row.body,
                suggestion_id=_draft_suggestion_id(row),
                acknowledged_warning_ids=frozenset(row.acknowledged_warning_ids),
                staff_reason_codes=reason_codes,
                note=row.note,
            )
        case ReplyBasis.REJECTED_AI_DRAFT:
            return RejectedAiDraftReply(
                body=row.body,
                suggestion_id=_draft_suggestion_id(row),
                staff_reason_codes=reason_codes,
                note=row.note,
            )
        case ReplyBasis.NO_AI_DRAFT:
            return NoAiDraftReply(row.body, to_optional_suggestion_id(row.suggestion_id))
        case ReplyBasis.REPLY_PROPOSAL:
            # The CHECK of `reply_proposals.basis` refuses it: a defect if it is ever read.
            raise UnexpectedFailureError
        case _:
            assert_never(basis)


def _draft_suggestion_id(row: ReplyProposalRow) -> SuggestionId:
    # A proposal on a draft always names the suggestion of the draft (contract
    # `AiDraftReplyRequest`, `RejectedAiDraftReplyRequest`).
    suggestion_id = to_optional_suggestion_id(row.suggestion_id)
    if suggestion_id is None:
        raise UnexpectedFailureError
    return suggestion_id

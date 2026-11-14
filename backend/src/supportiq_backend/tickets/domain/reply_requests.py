"""The bodies of replies and reply proposals, one variant per basis (contracts v1 design).

A body and a staff note are Confidential, so the classes that hold them have no generated
`repr` (LOG-29). The three variants that a proposal also takes answer the same questions,
their suggestion, acknowledged warnings, staff reason codes, and note, so the code that stores
or shows a body reads them without a match over the variants.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, NewType
from uuid import UUID

from supportiq_backend.suggestions import SuggestionId

ProposalId = NewType("ProposalId", UUID)


class ReplyBasis(StrEnum):
    """What a reply is based on (contracts v1 design, `sendReply`)."""

    AI_DRAFT = "ai_draft"
    REJECTED_AI_DRAFT = "rejected_ai_draft"
    NO_AI_DRAFT = "no_ai_draft"
    REPLY_PROPOSAL = "reply_proposal"


class StaffReasonCode(StrEnum):
    """Why staff edited, rejected, or escalated (ADR-0006)."""

    WRONG_INTENT = "wrong_intent"
    WRONG_SOURCE = "wrong_source"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    KB_GAP = "kb_gap"
    MISSING_CASE_INFO = "missing_case_info"
    TONE_OR_CLARITY = "tone_or_clarity"
    CASE_EXCEPTION = "case_exception"
    OTHER = "other"


@dataclass(frozen=True, slots=True, repr=False)
class AiDraftReply:
    """A reply based on the current draft, sent as is or edited.

    Attributes:
        basis: Always `ai_draft`.
        body: The text that the customer reads.
        suggestion_id: The suggestion of the draft.
        acknowledged_warning_ids: Every warning of that suggestion.
        staff_reason_codes: Why staff edited, when they say.
        note: A note for the record, required with `other`.
    """

    basis: ClassVar[ReplyBasis] = ReplyBasis.AI_DRAFT
    body: str
    suggestion_id: SuggestionId
    acknowledged_warning_ids: frozenset[str]
    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None


@dataclass(frozen=True, slots=True, repr=False)
class RejectedAiDraftReply:
    """A reply written instead of a ready draft that staff rejected.

    Attributes:
        basis: Always `rejected_ai_draft`.
        body: The text that the customer reads.
        suggestion_id: The suggestion of the rejected draft.
        staff_reason_codes: Why staff rejected it, at least one.
        note: A note for the record, required with `other`.
    """

    basis: ClassVar[ReplyBasis] = ReplyBasis.REJECTED_AI_DRAFT
    body: str
    suggestion_id: SuggestionId
    staff_reason_codes: tuple[StaffReasonCode, ...]
    note: str | None

    @property
    def acknowledged_warning_ids(self) -> frozenset[str]:
        """Return no warning: staff acknowledge the warnings of a draft that they send."""
        return frozenset()


@dataclass(frozen=True, slots=True, repr=False)
class NoAiDraftReply:
    """A reply without a ready draft, or on a ticket in manual mode.

    Attributes:
        basis: Always `no_ai_draft`.
        body: The text that the customer reads.
        suggestion_id: The current suggestion, when staff name it.
    """

    basis: ClassVar[ReplyBasis] = ReplyBasis.NO_AI_DRAFT
    body: str
    suggestion_id: SuggestionId | None

    @property
    def acknowledged_warning_ids(self) -> frozenset[str]:
        """Return no warning: there is no draft whose warnings staff would acknowledge."""
        return frozenset()

    @property
    def staff_reason_codes(self) -> tuple[StaffReasonCode, ...]:
        """Return no reason code: the contract's body without a draft carries none."""
        return ()

    @property
    def note(self) -> str | None:
        """Return no note: the contract's body without a draft carries none."""
        return None


@dataclass(frozen=True, slots=True, repr=False)
class ProposalReply:
    """A manager's reply from a reply proposal, as proposed or edited.

    Attributes:
        basis: Always `reply_proposal`.
        body: The text that the customer reads.
        proposal_id: The proposal, as the request sent it: an opaque string that is compared
            with the ticket's proposal and never parsed (CON-15).
    """

    basis: ClassVar[ReplyBasis] = ReplyBasis.REPLY_PROPOSAL
    body: str
    proposal_id: str


# The bodies of `createReplyProposal`: every basis but `reply_proposal`, because a proposal is
# never based on another proposal (contract `ReplyProposalBasis`).
type ProposalRequest = AiDraftReply | RejectedAiDraftReply | NoAiDraftReply
# The bodies of `sendReply`.
type ReplyRequest = ProposalRequest | ProposalReply

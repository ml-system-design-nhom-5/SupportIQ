/**
 * How a ticket reaches a manager (console UI design, Flow and States): a reply proposal that staff
 * submitted, which leaves the ticket `awaiting_approval`, or an escalation, which leaves it
 * `escalated`. Both are mapped once from the workspace (TS-09). Their text is Confidential: shown,
 * never logged.
 */
import { requireMembers } from "@/features/backend-requests";
import type {
  EscalationContract,
  ReplyProposalBasisContract,
  ReplyProposalContract,
  StaffMemberContract,
} from "@/features/console-tickets/api/contract-types";
import {
  type ShownStaffReasonCode,
  toStaffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";

/** The bases of a proposal in the contract. */
const proposalBases = [
  "ai_draft",
  "rejected_ai_draft",
  "no_ai_draft",
] as const satisfies readonly ReplyProposalBasisContract[];

/** The staff member who submitted a proposal or escalated a ticket. */
export type HandoffAuthor = {
  readonly accountId: string;
  readonly displayName: string;
};

/**
 * What a proposal is based on, or `unknown` for a basis that this version does not know (CON-22).
 * `ai_draft`: the AI draft, as is or edited. `rejected_ai_draft`: a reply that staff wrote after
 * they rejected the AI draft. `no_ai_draft`: a reply that staff wrote without a ready draft.
 */
export type ProposalBasis = (typeof proposalBases)[number] | "unknown";

/** A reply that staff prepared for a manager to send. */
export type ReplyProposal = {
  readonly proposalId: string;
  /** The proposed reply, which a manager sends as is or edited. */
  readonly body: string;
  readonly basis: ProposalBasis;
  /** The reasons that staff gave, in the order of the contract; empty when they gave none. */
  readonly reasonCodes: readonly ShownStaffReasonCode[];
  /** The staff note; absent when staff wrote none. Confidential: shown, never logged or stored. */
  readonly note?: string;
  readonly proposedBy: HandoffAuthor;
  /** When it was submitted, as an RFC 3339 timestamp. */
  readonly createdAt: string;
};

/** The escalation of a ticket to the manager queue. */
export type TicketEscalation = {
  /** Why staff escalated, in the order of the contract; at least one. */
  readonly reasonCodes: readonly ShownStaffReasonCode[];
  /** The staff note; absent when staff wrote none. */
  readonly note?: string;
  readonly escalatedBy: HandoffAuthor;
  /** When the ticket was escalated, as an RFC 3339 timestamp. */
  readonly escalatedAt: string;
};

/**
 * Map the proposal of a ticket.
 *
 * @param proposal - A `ReplyProposalView`.
 * @returns The proposal, its text, its basis, the reasons and the note of staff, who submitted
 *   it, and when.
 */
export function toReplyProposal(proposal: ReplyProposalContract): ReplyProposal {
  requireMembers(proposal, [
    "proposal_id",
    "body",
    "basis",
    "staff_reason_codes",
    "proposed_by",
    "created_at",
  ]);
  return {
    proposalId: proposal.proposal_id,
    body: proposal.body,
    basis: toProposalBasis(proposal.basis),
    reasonCodes: toStaffReasonCodes(proposal.staff_reason_codes),
    ...(proposal.note === undefined ? {} : { note: proposal.note }),
    proposedBy: toHandoffAuthor(proposal.proposed_by),
    createdAt: proposal.created_at,
  };
}

/**
 * Map the basis of a proposal.
 *
 * @param value - The `basis` of a `ReplyProposalView`.
 * @returns The basis, or `unknown` for a value that this version does not know (CON-22).
 */
export function toProposalBasis(value: string): ProposalBasis {
  return proposalBases.find((basis) => basis === value) ?? "unknown";
}

/**
 * Map the escalation of a ticket.
 *
 * @param escalation - An `EscalationView`.
 * @returns The reasons, the note, who escalated, and when.
 */
export function toTicketEscalation(escalation: EscalationContract): TicketEscalation {
  requireMembers(escalation, ["staff_reason_codes", "escalated_by", "escalated_at"]);
  return {
    reasonCodes: toStaffReasonCodes(escalation.staff_reason_codes),
    ...(escalation.note === undefined ? {} : { note: escalation.note }),
    escalatedBy: toHandoffAuthor(escalation.escalated_by),
    escalatedAt: escalation.escalated_at,
  };
}

/**
 * Name the author of a proposal or an escalation as the console mockups do: "(you)" for the
 * signed-in account, and "(staff)" for anyone else, because only staff submit and escalate
 * (mockup.js, the proposal and the escalation of the manager views).
 *
 * @param author - The author.
 * @param signedInAccountId - The account of the session; undefined until it is known.
 * @returns For example "Minh Le (staff)" or "Mai Nguyen (you)".
 */
export function describeHandoffAuthor(
  author: HandoffAuthor,
  signedInAccountId: string | undefined,
): string {
  return `${author.displayName} ${author.accountId === signedInAccountId ? "(you)" : "(staff)"}`;
}

/**
 * Map the staff member of a proposal or an escalation.
 *
 * @param member - A `StaffMemberView`.
 * @returns Its account and the name shown for it.
 */
function toHandoffAuthor(member: StaffMemberContract): HandoffAuthor {
  requireMembers(member, ["account_id", "display_name"]);
  return { accountId: member.account_id, displayName: member.display_name };
}

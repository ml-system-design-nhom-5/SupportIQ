/**
 * How a ticket reaches a manager (console UI design, Flow and States): a reply proposal that staff
 * submitted, which leaves the ticket `awaiting_approval`, or an escalation, which leaves it
 * `escalated`. Both are mapped once from the workspace (TS-09). Their text is Confidential: shown,
 * never logged.
 */
import { requireMembers } from "@/features/backend-requests";
import type {
  EscalationContract,
  ReplyProposalContract,
} from "@/features/console-tickets/api/contract-types";
import {
  type StaffReasonCode,
  toStaffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";

/** A reply that staff prepared for a manager to send. */
export type ReplyProposal = {
  readonly proposalId: string;
  /** The proposed reply, which a manager sends as is or edited. */
  readonly body: string;
  readonly proposedByName: string;
  /** When it was submitted, as an RFC 3339 timestamp. */
  readonly createdAt: string;
};

/** The escalation of a ticket to the manager queue. */
export type TicketEscalation = {
  /** Why staff escalated, in the order of the contract; at least one. */
  readonly reasonCodes: readonly StaffReasonCode[];
  /** The staff note; absent when staff wrote none. */
  readonly note?: string;
  readonly escalatedByName: string;
  /** When the ticket was escalated, as an RFC 3339 timestamp. */
  readonly escalatedAt: string;
};

/**
 * Map the proposal of a ticket.
 *
 * @param proposal - A `ReplyProposalView`.
 * @returns The proposal, its text, who submitted it, and when.
 */
export function toReplyProposal(proposal: ReplyProposalContract): ReplyProposal {
  requireMembers(proposal, ["proposal_id", "body", "proposed_by", "created_at"]);
  return {
    proposalId: proposal.proposal_id,
    body: proposal.body,
    proposedByName: proposal.proposed_by.display_name,
    createdAt: proposal.created_at,
  };
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
    escalatedByName: escalation.escalated_by.display_name,
    escalatedAt: escalation.escalated_at,
  };
}

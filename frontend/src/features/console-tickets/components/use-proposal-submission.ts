/**
 * Submit for approval of the reply area (console UI design, Actions; FR-06; UI-16): one click
 * submits what staff composed for a manager, with no confirmation, because nothing reaches the
 * customer (UI-17 asks it only of Send reply). The body is built at the click from the reply area
 * as it is, and the button is disabled while the AI runs or a new suggestion starts, so the
 * proposal is always based on the current suggestion.
 */
import { useCreateIdempotencyKey } from "@/features/backend-requests";
import { chooseIdempotencyKey } from "@/features/console-tickets/api/keyed-writes";
import { useCreateReplyProposal } from "@/features/console-tickets/api/use-create-reply-proposal";
import type { ComposerTicket } from "@/features/console-tickets/model/composer-ticket";
import { findReplyBlock } from "@/features/console-tickets/model/reply-block";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";
import {
  type DatedFailure,
  readDatedFailure,
} from "@/features/console-tickets/model/reply-failure";
import { buildReplyProposalRequest } from "@/features/console-tickets/model/reply-request";

/** Submit for approval and its state. */
export type ProposalSubmission = {
  /** Submits the reply for approval; does nothing while it is disabled or sending. */
  readonly submit: () => void;
  /** True while the proposal is sending, with its automatic retries. */
  readonly isSubmitting: boolean;
  /** The last failed submission, with when it was sent; undefined after a success. */
  readonly submitFailure: DatedFailure | undefined;
};

/**
 * Keep Submit for approval of a ticket.
 *
 * @param ticketId - The ticket of the address.
 * @param composed - The ticket and what staff composed, as rendered now.
 * @param onSubmitted - Called once the proposal was stored.
 * @returns The handler, whether it is sending, and its last failure.
 */
export function useProposalSubmission(
  ticketId: string,
  composed: { readonly ticket: ComposerTicket; readonly state: ComposerState },
  onSubmitted: () => void,
): ProposalSubmission {
  const createProposal = useCreateReplyProposal(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  return {
    submit: () => {
      const { ticket, state } = composed;
      if (
        createProposal.isPending ||
        findReplyBlock(ticket, state, "submit_reply_proposal") !== undefined
      ) {
        return;
      }
      const request = buildReplyProposalRequest(ticket, state);
      const idempotencyKey = chooseIdempotencyKey(request, createProposal, createIdempotencyKey);
      createProposal.mutate({ request, idempotencyKey }, { onSuccess: onSubmitted });
    },
    isSubmitting: createProposal.isPending,
    submitFailure: readDatedFailure(createProposal, "submit_reply_proposal"),
  };
}

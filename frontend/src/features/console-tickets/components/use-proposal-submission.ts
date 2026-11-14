/**
 * Submit for approval of the reply area (console UI design, Actions; FR-06; UI-16): one click
 * submits what staff composed for a manager, with no confirmation, because nothing reaches the
 * customer (UI-17 asks it only of Send reply). The body is built at the click from the reply area
 * as it is, and the button is disabled while the AI runs or a new suggestion starts, so the
 * proposal is always based on the current suggestion.
 */
import { getRequestFailure, useCreateIdempotencyKey } from "@/features/backend-requests";
import { useCreateReplyProposal } from "@/features/console-tickets/api/use-create-reply-proposal";
import type { ComposerTicket } from "@/features/console-tickets/model/composer-ticket";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";
import {
  buildReplyProposalRequest,
  isSameReply,
} from "@/features/console-tickets/model/reply-request";
import { findReplyBlock } from "@/features/console-tickets/model/send-block";
import {
  describeReplyFailure,
  type SendFailureView,
} from "@/features/console-tickets/model/send-failure";

/** Submit for approval and its state. */
export type ProposalSubmission = {
  /** Submits the reply for approval; does nothing while it is disabled or sending. */
  readonly submit: () => void;
  readonly isSubmitting: boolean;
  /** The last failed submission, in plain language; undefined after a success or before any. */
  readonly submitFailure: SendFailureView | undefined;
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
  const failure = getRequestFailure(createProposal.error);
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
      const failed = createProposal.isError ? createProposal.variables : undefined;
      // The same proposal submitted again after a failure keeps its key (TS-29).
      const idempotencyKey =
        failed !== undefined && isSameReply(failed.request, request)
          ? failed.idempotencyKey
          : createIdempotencyKey();
      createProposal.mutate({ request, idempotencyKey }, { onSuccess: onSubmitted });
    },
    isSubmitting: createProposal.isPending,
    submitFailure:
      failure === undefined ? undefined : describeReplyFailure(failure, "submit_reply_proposal"),
  };
}

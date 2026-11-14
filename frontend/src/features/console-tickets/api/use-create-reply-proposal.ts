/**
 * Submit a reply for a manager to send (`createReplyProposal`): Submit for approval, which leaves
 * the ticket `awaiting_approval` and read-only for staff (FR-06; console UI design, Flow). Nothing
 * reaches the customer. One `Idempotency-Key` belongs to one proposal: automatic retries reuse it,
 * like every write with a key, and so does submitting the same proposal again after a failure, so a
 * lost answer never submits twice (TS-29, ERR-15). After a submission, and after a refusal that
 * means the ticket changed, the workspace and the queues load again.
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import {
  buildIdempotentWriteKey,
  getRequestFailure,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import type { CreateReplyProposalRequestContract } from "@/features/console-tickets/api/contract-types";
import {
  type ReplyProposal,
  toReplyProposal,
} from "@/features/console-tickets/model/manager-handoff";
import { describeReplyFailure } from "@/features/console-tickets/model/send-failure";

/** One Submit for approval: the request body and its key. */
export type SubmittedProposal = {
  readonly request: CreateReplyProposalRequestContract;
  /** Stays while staff submit the same proposal again after a failure. */
  readonly idempotencyKey: string;
};

/**
 * Submit the reply of a ticket for approval.
 *
 * @param ticketId - The ticket.
 * @returns The mutation, whose data is the stored proposal.
 */
export function useCreateReplyProposal(
  ticketId: string,
): UseMutationResult<ReplyProposal, Error, SubmittedProposal> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadTicket = () => {
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.workspace(ticketId) });
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.queues() });
  };
  return useMutation({
    mutationKey: buildIdempotentWriteKey("createReplyProposal"),
    mutationFn: (proposal: SubmittedProposal) =>
      sendAttempt(proposal.idempotencyKey, () =>
        requestData(
          () =>
            client.POST("/v1/console/tickets/{ticket_id}/reply-proposals", {
              params: {
                path: { ticket_id: ticketId },
                header: { "Idempotency-Key": proposal.idempotencyKey },
              },
              body: proposal.request,
            }),
          toReplyProposal,
        ),
      ),
    onSuccess: reloadTicket,
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (
        failure !== undefined &&
        describeReplyFailure(failure, "submit_reply_proposal").shouldReload
      ) {
        reloadTicket();
      }
    },
  });
}

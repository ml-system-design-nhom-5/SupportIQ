/**
 * Send the reply to the customer (`sendReply`): the only operation that sends anything to a
 * customer, and only after staff confirm Send reply (FR-04, UI-17). It is never retried
 * automatically (TS-29), so its mutation key is not one of the idempotent writes that the
 * composition root retries. Confirming the same reply again after a failure reuses its
 * `Idempotency-Key`, so a reply whose outcome was unknown reaches the customer at most once
 * (ERR-16). After a send, and after a refusal that means the ticket changed, the workspace and the
 * queues load again.
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { getRequestFailure, requestData, useWriteAttemptSender } from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import type {
  ConsoleReplyContract,
  SendReplyRequestContract,
} from "@/features/console-tickets/api/contract-types";
import { describeSendFailure } from "@/features/console-tickets/model/send-failure";

/** One confirmed Send reply: the request body and its key. */
export type ConfirmedReply = {
  readonly request: SendReplyRequestContract;
  /** Stays while staff confirm the same reply again after a failure. */
  readonly idempotencyKey: string;
};

/**
 * Send the reply of a ticket.
 *
 * @param ticketId - The ticket.
 * @returns The mutation, whose data is the sent reply; it never retries.
 */
export function useSendReply(
  ticketId: string,
): UseMutationResult<ConsoleReplyContract, Error, ConfirmedReply> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadTicket = () => {
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.workspace(ticketId) });
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.queues() });
  };
  return useMutation({
    mutationKey: consoleQueryKeys.sendReply(ticketId),
    retry: false,
    mutationFn: (reply: ConfirmedReply) =>
      sendAttempt(reply.idempotencyKey, () =>
        requestData(
          () =>
            client.POST("/v1/console/tickets/{ticket_id}/replies", {
              params: {
                path: { ticket_id: ticketId },
                header: { "Idempotency-Key": reply.idempotencyKey },
              },
              body: reply.request,
            }),
          (sentReply) => sentReply,
        ),
      ),
    onSuccess: reloadTicket,
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && describeSendFailure(failure).shouldReload) {
        reloadTicket();
      }
    },
  });
}

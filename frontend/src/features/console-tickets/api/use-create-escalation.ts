/**
 * Move a ticket to a manager (`createEscalation`): Escalate ticket, with at least one staff reason
 * code and a note with `other` (ADR-0006; console UI design, Actions and Dialogs). The AI only
 * recommends an escalation; this staff action decides it, and the ticket becomes read-only for
 * staff. One `Idempotency-Key` belongs to one escalation: automatic retries reuse it, like every
 * write with a key, and so does escalating with the same reasons again after a failure (TS-29,
 * ERR-15). After an escalation, and after a refusal that means the ticket changed, the workspace
 * and the queues load again.
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
import type { CreateEscalationRequestContract } from "@/features/console-tickets/api/contract-types";
import {
  type TicketEscalation,
  toTicketEscalation,
} from "@/features/console-tickets/model/manager-handoff";
import { describeReplyFailure } from "@/features/console-tickets/model/send-failure";

/** One Escalate ticket: the request body and its key. */
export type RequestedEscalation = {
  readonly request: CreateEscalationRequestContract;
  /** Stays while staff escalate with the same reasons again after a failure. */
  readonly idempotencyKey: string;
};

/**
 * Escalate a ticket.
 *
 * @param ticketId - The ticket.
 * @returns The mutation, whose data is the escalation.
 */
export function useCreateEscalation(
  ticketId: string,
): UseMutationResult<TicketEscalation, Error, RequestedEscalation> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadTicket = () => {
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.workspace(ticketId) });
    void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.queues() });
  };
  return useMutation({
    mutationKey: buildIdempotentWriteKey("createEscalation"),
    mutationFn: (escalation: RequestedEscalation) =>
      sendAttempt(escalation.idempotencyKey, () =>
        requestData(
          () =>
            client.POST("/v1/console/tickets/{ticket_id}/escalations", {
              params: {
                path: { ticket_id: ticketId },
                header: { "Idempotency-Key": escalation.idempotencyKey },
              },
              body: escalation.request,
            }),
          toTicketEscalation,
        ),
      ),
    onSuccess: reloadTicket,
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && describeReplyFailure(failure, "escalate").shouldReload) {
        reloadTicket();
      }
    },
  });
}

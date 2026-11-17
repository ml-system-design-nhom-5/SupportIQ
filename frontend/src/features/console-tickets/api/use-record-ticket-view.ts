/**
 * Record that a person opened a ticket (`recordTicketView`), once each time the workspace opens.
 * The first view starts the handling clock that NFR-11 measures, and a view of a ticket whose AI
 * failed starts a retry (console UI design, Observability and Flow). The `Idempotency-Key` belongs
 * to this opening of the workspace, so automatic retries and a repeated effect send the same key
 * (TS-29, ERR-15).
 */
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useBackendClient } from "@/api/client";
import {
  buildIdempotentWriteKey,
  getRequestFailure,
  type RequestFailure,
  requestNoContent,
  useCreateIdempotencyKey,
} from "@/features/backend-requests";

/** The state of the view of one opening of the workspace. */
export type TicketViewState = {
  /** True once `backend` answered, with success or a failure. */
  readonly isSettled: boolean;
  /** The failure, after the automatic retries; absent after a success. */
  readonly failure?: RequestFailure;
};

/**
 * Record the view when the workspace opens.
 *
 * @param ticketId - The ticket of the workspace.
 * @returns Whether the view is settled, and its failure when there is one.
 */
export function useRecordTicketView(ticketId: string): TicketViewState {
  const client = useBackendClient();
  const createIdempotencyKey = useCreateIdempotencyKey();
  const [idempotencyKey] = useState(createIdempotencyKey);
  const { mutate, isSuccess, isError, error } = useMutation({
    mutationKey: buildIdempotentWriteKey("recordTicketView"),
    mutationFn: () =>
      requestNoContent(() =>
        client.POST("/v1/console/tickets/{ticket_id}/views", {
          params: {
            path: { ticket_id: ticketId },
            header: { "Idempotency-Key": idempotencyKey },
          },
        }),
      ),
  });
  // TS-22: opening the workspace is synchronized with `backend`, which records the view. The page
  // mounts once per ticket, because its route element has the ticket ID as its key.
  useEffect(() => {
    mutate();
  }, [mutate]);
  const failure = getRequestFailure(error);
  return { isSettled: isSuccess || isError, ...(failure === undefined ? {} : { failure }) };
}

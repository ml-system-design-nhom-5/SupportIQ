/**
 * What every write of the reply area shares (console UI design, Flow; TS-29, ERR-15, ERR-16): one
 * `Idempotency-Key` belongs to one staff action, so the same request sent again after a failure
 * reuses its key and happens at most once, while any other request gets a new key. After a write,
 * the workspace and the queues load again, so staff see the ticket as `backend` left it.
 */
import type { QueryClient } from "@tanstack/react-query";

import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";

/** A write of the reply area: its request body and its key. */
export type KeyedWrite<Request> = {
  readonly request: Request;
  /** Stays while staff send the same request again after a failure. */
  readonly idempotencyKey: string;
};

/** What a write needs to know of its mutation: whether the last request failed, and which. */
export type LastWrite<Request> = {
  readonly isError: boolean;
  readonly variables: KeyedWrite<Request> | undefined;
};

/**
 * Choose the `Idempotency-Key` of a write. Requests are compared by their JSON, because the
 * console builds them, so equal requests serialize equally.
 *
 * @param request - The request to send.
 * @param lastWrite - The state of the mutation, with the last request when it failed.
 * @param createIdempotencyKey - Creates a new key.
 * @returns The key of the failed request when this is the same request; a new key otherwise.
 */
export function chooseIdempotencyKey<Request>(
  request: Request,
  lastWrite: LastWrite<Request>,
  createIdempotencyKey: () => string,
): string {
  const failed = lastWrite.isError ? lastWrite.variables : undefined;
  return failed !== undefined && JSON.stringify(failed.request) === JSON.stringify(request)
    ? failed.idempotencyKey
    : createIdempotencyKey();
}

/**
 * Load the ticket and the queues again after a write, or after a refusal that means the ticket
 * changed.
 *
 * @param queryClient - The query client.
 * @param ticketId - The ticket of the address.
 */
export function reloadTicketAfterWrite(queryClient: QueryClient, ticketId: string): void {
  void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.workspace(ticketId) });
  void queryClient.invalidateQueries({ queryKey: consoleQueryKeys.queues() });
}

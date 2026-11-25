/**
 * Read a console queue page by page (`listConsoleTickets`, CON-14). Once it loaded, the queue loads
 * again at the inbox polling interval while the inbox is open (console UI design, Inbox).
 */
import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import { getInboxPollingIntervalMs } from "@/features/console-tickets/model/polling";
import type { QueueStatus } from "@/features/console-tickets/model/queue";
import {
  type TicketSummaryPage,
  toTicketSummaryPage,
} from "@/features/console-tickets/model/ticket-summary";

/** The infinite query of a queue. */
export type TicketQueueQuery = UseInfiniteQueryResult<
  InfiniteData<TicketSummaryPage, string | undefined>
>;

/** What one page request needs. */
type QueuePageRequest = {
  readonly client: BackendClient;
  readonly status: QueueStatus;
  readonly cursor: string | undefined;
  readonly signal: AbortSignal;
};

/**
 * Read the tickets of one status.
 *
 * @param status - The queue status.
 * @returns The infinite query; `fetchNextPage` follows `next_cursor` while there is one.
 */
export function useTicketQueue(status: QueueStatus): TicketQueueQuery {
  const client = useBackendClient();
  return useInfiniteQuery({
    queryKey: consoleQueryKeys.queue(status),
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      fetchQueuePage({ client, status, cursor: pageParam, signal }),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    refetchInterval: (query) => getInboxPollingIntervalMs(query.state.data !== undefined),
  });
}

/**
 * Fetch one page of a queue. An empty cursor is never sent, because `backend` refuses it.
 *
 * @param request - The client, the status, the cursor, and the abort signal.
 * @returns The page.
 */
function fetchQueuePage(request: QueuePageRequest): Promise<TicketSummaryPage> {
  const query = {
    status: request.status,
    ...(request.cursor === undefined ? {} : { cursor: request.cursor }),
  };
  return requestData(
    () => request.client.GET("/v1/console/tickets", { params: { query }, signal: request.signal }),
    toTicketSummaryPage,
  );
}

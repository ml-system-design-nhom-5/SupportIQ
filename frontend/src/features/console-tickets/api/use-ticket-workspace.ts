/**
 * Read the workspace of a ticket (`getConsoleTicket`). The read changes nothing. While a part of
 * the suggestion is `pending`, the workspace loads again after each event of the progress stream,
 * or every 30 s when the stream cannot run (use-suggestion-progress.ts).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import {
  type TicketWorkspace,
  toTicketWorkspace,
} from "@/features/console-tickets/model/workspace";

/** Which workspace to read, and whether its view is recorded. */
export type TicketWorkspaceRequest = {
  readonly ticketId: string;
  /**
   * True once `recordTicketView` answered. The view can start a retry of a failed suggestion, so
   * the workspace loads after it (console UI design, Flow).
   */
  readonly isViewSettled: boolean;
};

/**
 * Read the workspace.
 *
 * @param request - The ticket and whether its view is recorded.
 * @returns The query of the workspace, which waits for the view.
 */
export function useTicketWorkspace(
  request: TicketWorkspaceRequest,
): UseQueryResult<TicketWorkspace> {
  const client = useBackendClient();
  const { ticketId } = request;
  return useQuery({
    queryKey: consoleQueryKeys.workspace(ticketId),
    queryFn: ({ signal }) =>
      requestData(
        () =>
          client.GET("/v1/console/tickets/{ticket_id}", {
            params: { path: { ticket_id: ticketId } },
            signal,
          }),
        toTicketWorkspace,
      ),
    enabled: request.isViewSettled,
  });
}

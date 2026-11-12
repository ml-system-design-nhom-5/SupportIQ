/**
 * The paths of the ticket screens of the console (console UI design, Screens): `/console` with
 * the inbox and no ticket selected, and `/console/tickets/{ticket_id}` for the workspace. The
 * queue that the inbox shows is the `status` search parameter, absent for Open, so it stays when a
 * ticket opens and after a reload.
 */
import type { QueueStatus } from "@/features/console-tickets/model/queue";
import { rootPathByArea } from "@/features/session";

/** The search parameter that holds the queue status. */
export const QUEUE_STATUS_PARAMETER = "status";

/** The route of the ticket workspace, relative to the console root. */
export const TICKET_ROUTE = "tickets/:ticketId";

/** The route parameter of the ticket ID. */
export const TICKET_ID_PARAMETER = "ticketId";

/**
 * Build the search of a queue.
 *
 * @param status - The queue status.
 * @returns An empty string for Open, otherwise for example `?status=closed`.
 */
export function buildQueueSearch(status: QueueStatus): string {
  return status === "open"
    ? ""
    : `?${new URLSearchParams({ [QUEUE_STATUS_PARAMETER]: status }).toString()}`;
}

/**
 * Build the path of a ticket workspace.
 *
 * @param ticketId - The `ticket_id`.
 * @param status - The queue that the inbox shows, which the path keeps.
 * @returns For example `/console/tickets/TCK-1042`.
 */
export function buildTicketPath(ticketId: string, status: QueueStatus): string {
  return `${rootPathByArea.console}/tickets/${encodeURIComponent(ticketId)}${buildQueueSearch(status)}`;
}

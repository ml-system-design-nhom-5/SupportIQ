/**
 * The console queues (console UI design, Inbox): one per ticket status, chosen in the dropdown of
 * the inbox. Staff have only Open; managers also have Awaiting approval, Escalated, and Closed
 * (contracts v1 design, Roles and permissions). `backend` enforces this with `403`; the inbox only
 * offers the statuses of the role (UI-40).
 */
import { presentationByConsoleTicketStatus } from "@/design-system";
import type { AccountRole } from "@/features/session";

const everyQueueStatus = ["open", "awaiting_approval", "escalated", "closed"] as const;

const staffQueueStatuses: readonly QueueStatus[] = ["open"];

const emptyQueueTextByStatus: Readonly<Record<QueueStatus, string>> = {
  open: "No open tickets",
  awaiting_approval: "No tickets awaiting approval",
  escalated: "No escalated tickets",
  closed: "No closed tickets",
};

/** The status of the tickets of a queue (`ConsoleTicketStatus` of the contract). */
export type QueueStatus = (typeof everyQueueStatus)[number];

/**
 * List the queues that a role may open.
 *
 * @param role - The role of the signed-in account.
 * @returns Every status for a manager; Open for staff and any other role.
 */
export function getQueueStatuses(role: AccountRole): readonly QueueStatus[] {
  return role === "manager" ? everyQueueStatus : staffQueueStatuses;
}

/**
 * Read the queue status of the address.
 *
 * @param value - The `status` search parameter, or null when the address has none.
 * @param statuses - The queues of the role.
 * @returns The status when the role has its queue, otherwise Open.
 */
export function parseQueueStatus(
  value: string | null,
  statuses: readonly QueueStatus[],
): QueueStatus {
  return statuses.find((status) => status === value) ?? "open";
}

/**
 * Name a queue in the dropdown, with the label of its ticket status (UI-12).
 *
 * @param status - The queue status.
 * @returns For example "Awaiting approval".
 */
export function getQueueLabel(status: QueueStatus): string {
  return presentationByConsoleTicketStatus[status].label;
}

/**
 * Say in which order a queue lists its tickets, as `listConsoleTickets` orders them.
 *
 * @param status - The queue status.
 * @returns "Newest first" for Closed, which is ordered by `closed_at`; "Oldest first" otherwise.
 */
export function getQueueOrderLabel(status: QueueStatus): string {
  return status === "closed" ? "Newest first" : "Oldest first";
}

/**
 * Say that a queue is empty.
 *
 * @param status - The queue status.
 * @returns For example "No open tickets".
 */
export function getEmptyQueueText(status: QueueStatus): string {
  return emptyQueueTextByStatus[status];
}

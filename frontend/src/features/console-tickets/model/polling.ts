/**
 * How often the console asks `backend` again (console UI design, Inbox and Flow). `frontend` polls
 * because v1 has no push updates (contracts v1 design, Non-goals). The lead approved both values
 * on 2026-11-12, which answers the polling question of the console UI design.
 */
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { hasPendingPart } from "@/features/console-tickets/model/workspace-state";

/**
 * The inbox reloads its queue this often while it is open, so new tickets and the "Opened" line of
 * a colleague appear without a click.
 */
export const INBOX_POLLING_INTERVAL_MS = 15_000;

/**
 * The workspace reloads the ticket this often while a part of the suggestion is `pending`, so the
 * analysis and then the draft appear soon after `ai-service` answers. A draft takes up to 10 s of
 * LLM time (NFR-07), and the end-to-end latency target is p50 at most 4 s (NFR-08).
 */
export const WORKSPACE_POLLING_INTERVAL_MS = 2_000;

/**
 * Choose how soon the inbox loads its queue again.
 *
 * @param hasQueue - True once a page of the queue loaded.
 * @returns {@link INBOX_POLLING_INTERVAL_MS} once the queue loaded; false before, so a queue that
 *   failed to load, such as with `403`, is not asked for again until staff try again.
 */
export function getInboxPollingIntervalMs(hasQueue: boolean): number | false {
  return hasQueue ? INBOX_POLLING_INTERVAL_MS : false;
}

/**
 * Choose how soon the workspace loads the ticket again.
 *
 * @param workspace - The loaded ticket, or undefined before the first load.
 * @returns {@link WORKSPACE_POLLING_INTERVAL_MS} while a part of the suggestion is `pending`;
 *   false otherwise, so the workspace stops polling. A ticket that failed to load is not asked for
 *   again until staff try again.
 */
export function getWorkspacePollingIntervalMs(
  workspace: TicketWorkspace | undefined,
): number | false {
  return workspace !== undefined && hasPendingPart(workspace)
    ? WORKSPACE_POLLING_INTERVAL_MS
    : false;
}

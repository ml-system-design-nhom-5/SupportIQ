/**
 * How often the console asks `backend` again (console UI design, Inbox and Flow). The lead decided
 * on 2026-11-13 that the console never polls more often than every 30 s. The inbox polls; the
 * workspace follows the suggestion progress stream while a part is `pending`, and polls only when
 * the stream cannot run (ADR-0022, statements 6 and 7).
 */

/**
 * The inbox reloads its queue this often while it is open, so new tickets and the "Opened" line of
 * a colleague appear without a click.
 */
export const INBOX_POLLING_INTERVAL_MS = 30_000;

/**
 * While the progress stream cannot run, the workspace reloads the ticket this often as long as a
 * part of the suggestion is `pending`, and opens a new stream after a reload that succeeds
 * (ADR-0022, statement 7).
 */
export const WORKSPACE_FALLBACK_POLLING_INTERVAL_MS = 30_000;

/**
 * A new progress stream that sends no event within this time has failed, as a stream does that a
 * proxy buffers or cuts off (ADR-0022, sequence diagram). `backend` sends the current state as
 * soon as the stream opens (statement 3), and the ingress already bounds the wait for the
 * response headers at 10 000 ms (ADR-0016, statement 4).
 */
export const FIRST_EVENT_TIMEOUT_MS = 10_000;

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

/**
 * The suggestion progress stream of a ticket (`getSuggestionEvents`, ADR-0022), which the browser
 * opens with `EventSource`, because the generated client does not read streams. The composition
 * root provides the opener (ARCH-31), so tests and stories use a fake one.
 */
import { createContext } from "react";

import type { paths } from "@/api/generated/backend";

/** The path of the stream, as the contract names it. */
const SUGGESTION_EVENTS_PATH =
  "/v1/console/tickets/{ticket_id}/suggestion-events" satisfies keyof paths;

/** The name of each event of the stream (ADR-0024, statement 1). */
export const SUGGESTION_EVENT = "suggestion";

/** The `readyState` of a source that the browser does not connect again (HTML, EventSource). */
export const CLOSED_READY_STATE = 2;

/** The part of `EventSource` that the console uses. */
export type SuggestionEventSource = {
  readonly readyState: number;
  readonly addEventListener: (type: string, listener: (event: MessageEvent) => void) => void;
  readonly close: () => void;
};

/** Opens an `EventSource` at a path of `backend`. */
export type OpenEventSource = (path: string) => SuggestionEventSource;

/** Holds the opener that the composition root provides. */
export const EventSourceContext = createContext<OpenEventSource | null>(null);

/**
 * Build the path of the stream of a ticket.
 *
 * @param ticketId - The ticket.
 * @returns For example `/v1/console/tickets/TCK-1042/suggestion-events`.
 */
export function buildSuggestionEventsPath(ticketId: string): string {
  return SUGGESTION_EVENTS_PATH.replace("{ticket_id}", encodeURIComponent(ticketId));
}

/**
 * The progress of the current suggestion, as the stream of `getSuggestionEvents` signals it, and
 * when the workspace follows it (ADR-0022, statements 2 and 6; ADR-0024). An event holds only the
 * suggestion ID and the statuses of its two parts. Its `data` is JSON text from outside the page,
 * so it is read as untrusted input: text that is not such an event gives nothing.
 */
import type { SuggestionProgressEventContract } from "@/features/console-tickets/api/contract-types";
import { parseJson, readField } from "@/features/console-tickets/model/json-text";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import { hasPendingPart } from "@/features/console-tickets/model/workspace-state";

/** The status of a part that is not done yet, in both parts of the contract. */
const PENDING_STATUS: SuggestionProgressEventContract["analysis_status"] &
  SuggestionProgressEventContract["draft_status"] = "pending";

/** The progress of the current suggestion. */
export type SuggestionProgress = {
  readonly suggestionId: string;
  /** Whether a part is still `pending`; an unknown status counts as done (CON-22). */
  readonly hasPendingPart: boolean;
};

/**
 * Read the data of one `suggestion` event.
 *
 * @param data - The `data` of the event: a `SuggestionProgressEvent` as JSON text.
 * @returns The progress, or undefined when the data is not such an event.
 */
export function parseSuggestionProgress(data: string): SuggestionProgress | undefined {
  const event = parseJson(data);
  const suggestionId = readField(event, "suggestion_id");
  const analysisStatus = readField(event, "analysis_status");
  const draftStatus = readField(event, "draft_status");
  if (
    typeof suggestionId !== "string" ||
    typeof analysisStatus !== "string" ||
    typeof draftStatus !== "string"
  ) {
    return undefined;
  }
  return {
    suggestionId,
    hasPendingPart: analysisStatus === PENDING_STATUS || draftStatus === PENDING_STATUS,
  };
}

/**
 * Tell whether the workspace follows the progress of its suggestion (ADR-0022, statement 6).
 *
 * @param workspace - The loaded ticket.
 * @returns True for an `open` ticket in `assisted` mode while a part of its current suggestion is
 *   `pending`.
 */
export function canFollowProgress(workspace: TicketWorkspace): boolean {
  return (
    workspace.status === "open" &&
    workspace.handlingMode === "assisted" &&
    hasPendingPart(workspace)
  );
}

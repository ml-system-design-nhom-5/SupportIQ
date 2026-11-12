/**
 * The statuses of a ticket and of its AI output, mapped once from the contract (CON-22, TS-15):
 * the ticket status, the handling mode, the draft status, and the confidence band.
 */
import type {
  AiStatusName,
  ConfidenceBandName,
  ConsoleTicketStatusName,
  HandlingModeName,
} from "@/design-system";

const ticketStatuses: ReadonlySet<string> = new Set([
  "open",
  "awaiting_approval",
  "escalated",
  "closed",
]);

const aiStatusByDraftStatus: ReadonlyMap<string, AiStatusName> = new Map([
  ["pending", "pending"],
  ["draft_ready", "draft_ready"],
  ["abstained", "abstained"],
  ["escalation_recommended", "escalation_recommended"],
  ["llm_unavailable", "unavailable"],
  ["unavailable", "unavailable"],
]);

const confidenceBands: ReadonlySet<string> = new Set(["high", "medium", "low"]);

/**
 * Map a ticket status.
 *
 * @param value - A `ConsoleTicketStatus`.
 * @returns The status, or `unknown`, which the console shows as a state with no action.
 */
export function toTicketStatus(value: string): ConsoleTicketStatusName {
  return isTicketStatus(value) ? value : "unknown";
}

/**
 * Map a handling mode.
 *
 * @param value - A `HandlingMode`.
 * @returns `assisted`, or `manual` for any other value, as the contract says.
 */
export function toHandlingMode(value: string): HandlingModeName {
  return value === "assisted" ? "assisted" : "manual";
}

/**
 * Map the status of a draft to the AI status that the inbox and the reply area show.
 *
 * @param value - A `DraftStatus`.
 * @returns The AI status; `llm_unavailable` and any unknown value are `unavailable` (CON-22).
 */
export function toAiStatus(value: string): AiStatusName {
  return aiStatusByDraftStatus.get(value) ?? "unavailable";
}

/**
 * Map a confidence band.
 *
 * @param value - A `ConfidenceBand`.
 * @returns The band, or `low` for a value that this version does not know (CON-22).
 */
export function toConfidenceBand(value: string): ConfidenceBandName {
  return isConfidenceBand(value) ? value : "low";
}

/**
 * Tell whether a value is a ticket status of the contract.
 *
 * @param value - A `ConsoleTicketStatus` from `backend`.
 * @returns True for `open`, `awaiting_approval`, `escalated`, and `closed`.
 */
function isTicketStatus(value: string): value is Exclude<ConsoleTicketStatusName, "unknown"> {
  return ticketStatuses.has(value);
}

/**
 * Tell whether a value is a confidence band of the contract.
 *
 * @param value - A `ConfidenceBand` from `backend`.
 * @returns True for `high`, `medium`, and `low`.
 */
function isConfidenceBand(value: string): value is ConfidenceBandName {
  return confidenceBands.has(value);
}

/**
 * The actions that `backend` allows the caller on a ticket now (`TicketAction`), mapped once from
 * `allowed_actions` (TS-09). `backend` computes them with the same rules that the operations check,
 * so the console offers no action that would be refused; it never decides a permission itself
 * (UI-40).
 */
import type { TicketActionContract } from "@/features/console-tickets/api/contract-types";

/** The actions of the contract, in its order. */
const knownTicketActions = [
  "send_reply",
  "submit_reply_proposal",
  "escalate",
  "correct_intent",
  "retry_suggestion",
] as const satisfies readonly TicketActionContract[];

const ticketActions: ReadonlySet<string> = new Set(knownTicketActions);

/**
 * An action that the caller may take.
 * `send_reply`: `sendReply`.
 * `submit_reply_proposal`: `createReplyProposal`.
 * `escalate`: `createEscalation`.
 * `correct_intent`: `createSuggestion` with `intent_override`.
 * `retry_suggestion`: `createSuggestion` without `intent_override`.
 */
export type TicketAction = (typeof knownTicketActions)[number];

/**
 * Map the allowed actions of a ticket.
 *
 * @param values - The `allowed_actions` of a `TicketWorkspace`.
 * @returns The actions; a value that this version does not know is ignored (CON-22).
 */
export function toTicketActions(values: readonly string[]): ReadonlySet<TicketAction> {
  return new Set(values.filter(isTicketAction));
}

/**
 * Tell whether a value is an action of the contract.
 *
 * @param value - A `TicketAction` from `backend`.
 * @returns True for an action of {@link knownTicketActions}.
 */
function isTicketAction(value: string): value is TicketAction {
  return ticketActions.has(value);
}

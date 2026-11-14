/**
 * The main action of the reply area and why it is disabled (UI-16, UI-18, UI-43; console UI
 * design, Actions and placement rule 2). Send reply is the main action when `backend` allows it;
 * when authority is required, staff get Submit for approval instead. One line above the buttons
 * names the first reason that applies, or a note when the main action is enabled. `backend` checks
 * every rule again (FR-04, FR-06, SEC-38); the console only spares staff a refused request.
 */
import { formatCount } from "@/design-system";
import { countContractCharacters, MESSAGE_MAX_LENGTH } from "@/features/backend-requests";
import {
  type ComposerMode,
  type ComposerTicket,
  getComposerMode,
  getReplyBody,
} from "@/features/console-tickets/model/composer-ticket";
import { hasPlaceholder } from "@/features/console-tickets/model/placeholders";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";
import { STAFF_NOTE_MAX_LENGTH } from "@/features/console-tickets/model/staff-reason-codes";

/** An action that sends what staff composed: Send reply, or Submit for approval. */
export type ReplyAction = "send_reply" | "submit_reply_proposal";

/** The verb of each action in the reasons, as in "to send the reply". */
const verbByAction: Readonly<Record<ReplyAction, string>> = {
  send_reply: "send",
  submit_reply_proposal: "submit",
};

/**
 * Choose the main action, on the right of the action bar (UI-16).
 *
 * @param ticket - The ticket.
 * @returns Send reply when `backend` allows it; Submit for approval when only a proposal is
 *   allowed, as when authority is required; Send reply, disabled, otherwise.
 */
export function getPrimaryAction(ticket: ComposerTicket): ReplyAction {
  return !ticket.allowedActions.has("send_reply") &&
    ticket.allowedActions.has("submit_reply_proposal")
    ? "submit_reply_proposal"
    : "send_reply";
}

/**
 * Say why an action is disabled.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @param action - The action; the main action by default.
 * @returns The first reason that applies, or undefined when the action is enabled.
 */
export function findReplyBlock(
  ticket: ComposerTicket,
  state: ComposerState,
  action: ReplyAction = getPrimaryAction(ticket),
): string | undefined {
  const verb = verbByAction[action];
  return (
    findTicketBlock(ticket, action) ??
    findRejectionBlock(getComposerMode(ticket, state), state, verb) ??
    findBodyBlock(getReplyBody(ticket, state), describeEmptyBody(ticket, action), verb) ??
    findWarningBlock(ticket, state, verb)
  );
}

/**
 * Say what the line above the buttons notes while the main action is enabled.
 *
 * @param ticket - The ticket.
 * @returns That a manager sends the reply when staff submit it for approval; why Reject draft and
 *   Escalate ticket are disabled for a manager on a proposal; or undefined.
 */
export function findActionNote(ticket: ComposerTicket): string | undefined {
  if (getPrimaryAction(ticket) === "submit_reply_proposal") {
    return "A manager sends the reply on this ticket.";
  }
  return ticket.draft?.kind === "reply_proposal" && ticket.allowedActions.has("send_reply")
    ? "Reject draft and Escalate ticket are not available while the ticket awaits approval."
    : undefined;
}

/**
 * Say why the ticket allows no reply or proposal now.
 *
 * @param ticket - The ticket.
 * @param action - The action.
 * @returns The reason, or undefined when `backend` allows the action.
 */
function findTicketBlock(ticket: ComposerTicket, action: ReplyAction): string | undefined {
  if (ticket.status === "closed") {
    return "This ticket is closed. A reply was already sent.";
  }
  const isAllowed = ticket.allowedActions.has(action);
  if (!isAllowed && (ticket.status === "awaiting_approval" || ticket.status === "escalated")) {
    return "This ticket is read-only for you. A manager sends the reply.";
  }
  if (ticket.isSuggestionRunning) {
    return "The AI is still working on this ticket.";
  }
  if (ticket.isIntentChoiceNeeded) {
    return "Choose an intent to get a draft.";
  }
  return isAllowed ? undefined : describeNotAllowed(ticket, action);
}

/**
 * Say that the role cannot take the action on this ticket.
 *
 * @param ticket - The ticket.
 * @param action - The action that `backend` does not allow.
 * @returns The reason.
 */
function describeNotAllowed(ticket: ComposerTicket, action: ReplyAction): string {
  if (action === "submit_reply_proposal") {
    return "You cannot submit a reply for approval on this ticket.";
  }
  return ticket.isAuthorityRequired
    ? "Only a manager can send the reply of this ticket."
    : "You cannot send a reply on this ticket.";
}

/**
 * Say what to do while the editor is empty, with the other ways out that the ticket offers
 * (console UI design, mockups of the states).
 *
 * @param ticket - The ticket.
 * @param action - The action.
 * @returns The sentence.
 */
function describeEmptyBody(ticket: ComposerTicket, action: ReplyAction): string {
  if (action === "submit_reply_proposal") {
    return "Write a reply to submit it for approval.";
  }
  const { situation, allowedActions } = ticket;
  if (situation === "manual_handling" && allowedActions.has("submit_reply_proposal")) {
    return "Write a reply to send it or to submit it for approval.";
  }
  return situation === "escalation_recommended" && allowedActions.has("escalate")
    ? "Write a reply to send it, or escalate the ticket."
    : "Write a reply to send it.";
}

/**
 * Say what a rejection still needs (ADR-0006): a reason code, and a note for `other`.
 *
 * @param mode - What staff do.
 * @param state - What staff composed.
 * @param verb - The verb of the action.
 * @returns The reason, or undefined when the rejection is complete or there is none.
 */
function findRejectionBlock(
  mode: ComposerMode,
  state: ComposerState,
  verb: string,
): string | undefined {
  if (mode !== "rejecting") {
    return undefined;
  }
  if (state.reasonCodes.size === 0) {
    return `Choose why you rejected the draft to ${verb} the reply.`;
  }
  if (!state.reasonCodes.has("other")) {
    return undefined;
  }
  if (state.note.trim() === "") {
    return `Write a note for the reason Other to ${verb} the reply.`;
  }
  return countContractCharacters(state.note) > STAFF_NOTE_MAX_LENGTH
    ? `Shorten the note to ${formatCount(STAFF_NOTE_MAX_LENGTH)} characters to ${verb} the reply.`
    : undefined;
}

/**
 * Say what the text still needs: some text, at most 2 000 characters, and no placeholder (UI-43).
 *
 * @param body - The text that the action sends.
 * @param emptyReason - What to say while the text is empty.
 * @param verb - The verb of the action.
 * @returns The reason, or undefined when the text may be sent.
 */
function findBodyBlock(body: string, emptyReason: string, verb: string): string | undefined {
  if (body.trim() === "") {
    return emptyReason;
  }
  if (countContractCharacters(body) > MESSAGE_MAX_LENGTH) {
    return `Shorten the reply to ${formatCount(MESSAGE_MAX_LENGTH)} characters to ${verb} it.`;
  }
  return hasPlaceholder(body) ? `Replace the highlighted text to ${verb} the reply.` : undefined;
}

/**
 * Say how many warnings staff still have to acknowledge (UI-18). A rejected draft, a reply
 * without a draft, and a proposal carry no warning to acknowledge.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @param verb - The verb of the action.
 * @returns The reason, or undefined when every warning is acknowledged.
 */
function findWarningBlock(
  ticket: ComposerTicket,
  state: ComposerState,
  verb: string,
): string | undefined {
  if (getComposerMode(ticket, state) === "rejecting") {
    return undefined;
  }
  const count = ticket.warningIds.filter(
    (warningId) => !state.acknowledgedWarningIds.has(warningId),
  ).length;
  if (count === 0) {
    return undefined;
  }
  return `Acknowledge ${formatCount(count)} ${count === 1 ? "warning" : "warnings"} to ${verb} the reply.`;
}

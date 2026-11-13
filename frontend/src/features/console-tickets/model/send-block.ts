/**
 * Why Send reply is disabled (UI-16, UI-18, UI-43; console UI design, Actions and placement rule
 * 2): one line above the buttons names the first reason that applies, and Send reply stays
 * disabled until the reply may be sent. `backend` checks every rule again (FR-04, FR-06, SEC-38);
 * the console only spares staff a refused request.
 */
import { formatCount } from "@/design-system";
import { countContractCharacters, MESSAGE_MAX_LENGTH } from "@/features/backend-requests";
import { hasPlaceholder } from "@/features/console-tickets/model/placeholders";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";
import {
  type ComposerMode,
  type ComposerTicket,
  getComposerMode,
  getReplyBody,
} from "@/features/console-tickets/model/reply-request";
import { STAFF_NOTE_MAX_LENGTH } from "@/features/console-tickets/model/staff-reason-codes";

/**
 * Say why Send reply is disabled, in the line above the buttons (placement rule 2).
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The first reason that applies, or undefined when Send reply is enabled.
 */
export function findSendBlock(ticket: ComposerTicket, state: ComposerState): string | undefined {
  return (
    findTicketBlock(ticket) ??
    findRejectionBlock(getComposerMode(ticket, state), state) ??
    findBodyBlock(getReplyBody(ticket, state)) ??
    findWarningBlock(ticket, state)
  );
}

/**
 * Say why the ticket allows no reply now.
 *
 * @param ticket - The ticket.
 * @returns The reason, or undefined when `send_reply` is allowed.
 */
function findTicketBlock(ticket: ComposerTicket): string | undefined {
  if (ticket.isClosed) {
    return "This ticket is closed. A reply was already sent.";
  }
  if (ticket.isSuggestionRunning) {
    return "The AI is still working on this ticket.";
  }
  if (ticket.isIntentChoiceNeeded) {
    return "Choose an intent to get a draft.";
  }
  if (ticket.allowedActions.has("send_reply")) {
    return undefined;
  }
  return ticket.isAuthorityRequired
    ? "Only a manager can send the reply of this ticket."
    : "You cannot send a reply on this ticket.";
}

/**
 * Say what a rejection still needs (ADR-0006): a reason code, and a note for `other`.
 *
 * @param mode - What staff do.
 * @param state - What staff composed.
 * @returns The reason, or undefined when the rejection is complete or there is none.
 */
function findRejectionBlock(mode: ComposerMode, state: ComposerState): string | undefined {
  if (mode !== "rejecting") {
    return undefined;
  }
  if (state.reasonCodes.size === 0) {
    return "Choose why you rejected the draft to send the reply.";
  }
  if (!state.reasonCodes.has("other")) {
    return undefined;
  }
  return findNoteBlock(state.note);
}

/**
 * Say what the note of the reason code `other` still needs.
 *
 * @param note - The note.
 * @returns The reason, or undefined when the note has from 1 to 1 000 characters.
 */
function findNoteBlock(note: string): string | undefined {
  if (note.trim() === "") {
    return "Write a note for the reason Other to send the reply.";
  }
  return countContractCharacters(note) > STAFF_NOTE_MAX_LENGTH
    ? `Shorten the note to ${formatCount(STAFF_NOTE_MAX_LENGTH)} characters to send the reply.`
    : undefined;
}

/**
 * Say what the text of the reply still needs: some text, at most 2 000 characters, and no
 * placeholder (UI-43).
 *
 * @param body - The text that Send reply sends.
 * @returns The reason, or undefined when the text may be sent.
 */
function findBodyBlock(body: string): string | undefined {
  if (body.trim() === "") {
    return "Write a reply to send it.";
  }
  if (countContractCharacters(body) > MESSAGE_MAX_LENGTH) {
    return `Shorten the reply to ${formatCount(MESSAGE_MAX_LENGTH)} characters to send it.`;
  }
  return hasPlaceholder(body) ? "Replace the highlighted text to send the reply." : undefined;
}

/**
 * Say how many warnings staff still have to acknowledge (UI-18). A rejected draft and a reply
 * without a draft carry no warning.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The reason, or undefined when every warning is acknowledged.
 */
function findWarningBlock(ticket: ComposerTicket, state: ComposerState): string | undefined {
  const mode = getComposerMode(ticket, state);
  if (mode === "rejecting" || mode === "writing") {
    return undefined;
  }
  const count = ticket.warningIds.filter(
    (warningId) => !state.acknowledgedWarningIds.has(warningId),
  ).length;
  if (count === 0) {
    return undefined;
  }
  return `Acknowledge ${formatCount(count)} ${count === 1 ? "warning" : "warnings"} to send the reply.`;
}

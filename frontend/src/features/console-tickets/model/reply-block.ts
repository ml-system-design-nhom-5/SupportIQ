/**
 * The main action of the reply area and why it is disabled (UI-16, UI-18, UI-43; console UI
 * design, Actions and placement rule 2). Send reply is the main action; when authority is
 * required, staff get Submit for approval in its place. The place follows the authority flag and
 * the role, so it never moves while `allowed_actions` changes (UI-15); whether an action is
 * enabled follows `allowed_actions` (UI-40). One line above the buttons names the first reason
 * that applies, or a note while the main action is enabled. `backend` checks every rule again
 * (FR-04, FR-06, SEC-38); the console only spares staff a refused request.
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
import {
  describeStaffNoteProblem,
  findStaffNoteProblem,
} from "@/features/console-tickets/model/staff-reason-codes";
import type { TicketAction } from "@/features/console-tickets/model/ticket-actions";

/** An action that sends what staff composed: Send reply, or Submit for approval. */
export type ReplyAction = Extract<TicketAction, "send_reply" | "submit_reply_proposal">;

/** The verb of each action in the reasons, as in "to send the reply". */
const verbByAction: Readonly<Record<ReplyAction, string>> = {
  send_reply: "send",
  submit_reply_proposal: "submit",
};

/** What the line says while a write that hands the ticket to a manager is sending. */
const handoverReasons: Readonly<Record<NonNullable<ComposerTicket["handover"]>, string>> = {
  submit_reply_proposal: "The reply is being submitted for approval.",
  escalate: "The ticket is being escalated.",
};

/**
 * Choose the main action, on the right of the action bar (UI-16).
 *
 * @param ticket - The ticket.
 * @returns Submit for approval for staff on a ticket that requires authority; Send reply
 *   otherwise, for a manager always.
 */
export function getPrimaryAction(ticket: ComposerTicket): ReplyAction {
  return ticket.isAuthorityRequired && !ticket.isManager ? "submit_reply_proposal" : "send_reply";
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
 *   Escalate ticket are disabled for a manager on a proposal; why the actions that only staff take
 *   are disabled for a manager otherwise ({@link findManagerNote}); or undefined.
 */
export function findActionNote(ticket: ComposerTicket): string | undefined {
  if (getPrimaryAction(ticket) === "submit_reply_proposal") {
    return "A manager sends the reply on this ticket.";
  }
  if (ticket.draft?.kind === "reply_proposal" && ticket.allowedActions.has("send_reply")) {
    return "Reject draft and Escalate ticket are not available while the ticket awaits approval.";
  }
  return findManagerNote(ticket);
}

/**
 * Say why a manager cannot take the actions that only staff take: Escalate ticket
 * (`createEscalation`) and, where it is a visible button in manual handling, Submit for approval
 * (`createReplyProposal`).
 *
 * @param ticket - The ticket.
 * @returns The note for a manager without `escalate`; undefined for staff, who may escalate.
 */
function findManagerNote(ticket: ComposerTicket): string | undefined {
  if (!ticket.isManager || ticket.allowedActions.has("escalate")) {
    return undefined;
  }
  if (ticket.situation === "manual_handling") {
    return "Only staff escalate a ticket or submit a reply for approval.";
  }
  return "Only staff escalate a ticket. Managers handle escalated tickets.";
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
  if (ticket.handover !== undefined) {
    return handoverReasons[ticket.handover];
  }
  return findReadOnlyBlock(ticket, action) ?? findSuggestionBlock(ticket, action);
}

/**
 * Say that a ticket handed to a manager is read-only for staff.
 *
 * @param ticket - The ticket.
 * @param action - The action.
 * @returns The reason for staff on a ticket that awaits approval or is escalated; undefined
 *   otherwise, and always for a manager, who handles those tickets.
 */
function findReadOnlyBlock(ticket: ComposerTicket, action: ReplyAction): string | undefined {
  const isHandedOver = ticket.status === "awaiting_approval" || ticket.status === "escalated";
  return !ticket.isManager && isHandedOver && !ticket.allowedActions.has(action)
    ? "This ticket is read-only for you. A manager sends the reply."
    : undefined;
}

/**
 * Say why the current suggestion, or the role, allows no reply or proposal now.
 *
 * @param ticket - The ticket.
 * @param action - The action.
 * @returns The reason, or undefined when `backend` allows the action.
 */
function findSuggestionBlock(ticket: ComposerTicket, action: ReplyAction): string | undefined {
  if (ticket.isSuggestionRunning) {
    return "The AI is still working on this ticket.";
  }
  if (ticket.isIntentChoiceNeeded) {
    return "Choose an intent to get a draft.";
  }
  return ticket.allowedActions.has(action) ? undefined : describeNotAllowed(ticket, action);
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
    return ticket.isManager
      ? "Only staff submit a reply for approval."
      : "You cannot submit a reply for approval on this ticket.";
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
  const problem = findStaffNoteProblem(state.note, state.reasonCodes.has("other"));
  return problem === undefined
    ? undefined
    : describeStaffNoteProblem(problem, `to ${verb} the reply`);
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

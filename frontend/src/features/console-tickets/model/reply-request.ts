/**
 * The reply that Send reply sends (console UI design, Actions): its `basis` follows from what
 * staff did, and Send reply stays disabled, with one line that says why, until the reply may be
 * sent (UI-16, UI-18, UI-43). `backend` checks every rule again and refuses with `403`, `409`, or
 * `422` (FR-04, FR-06, SEC-38); the console only spares staff a refused request. Nothing here sends:
 * only a staff click and a confirmation send a reply.
 */
import { formatCount } from "@/design-system";
import { countContractCharacters, MESSAGE_MAX_LENGTH } from "@/features/backend-requests";
import type { SendReplyRequestContract } from "@/features/console-tickets/api/contract-types";
import { hasPlaceholder } from "@/features/console-tickets/model/placeholders";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type { ComposerState, DraftMode } from "@/features/console-tickets/model/reply-composer";
import {
  STAFF_NOTE_MAX_LENGTH,
  staffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";
import type { TicketAction } from "@/features/console-tickets/model/ticket-actions";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import {
  hasPendingPart,
  type ReplyAreaState,
} from "@/features/console-tickets/model/workspace-state";

/** What the composer needs to know of the ticket, derived from the workspace. */
export type ComposerTicket = {
  readonly allowedActions: ReadonlySet<TicketAction>;
  readonly isAuthorityRequired: boolean;
  /** True while a part of the current suggestion is `pending`. */
  readonly isSuggestionRunning: boolean;
  /** True when the AI abstained for low confidence: staff choose an intent first (ESC-01). */
  readonly isIntentChoiceNeeded: boolean;
  /** The current suggestion; absent in `manual` mode. */
  readonly suggestionId?: string;
  /** The ready draft of the current suggestion; absent when there is none. */
  readonly draft?: { readonly suggestionId: string; readonly text: string };
  /** The `warning_id` of every warning of the current suggestion. */
  readonly warningIds: readonly string[];
};

/** What the composer reads of the regions of the workspace. */
export type ComposerRegions = {
  readonly reply: ReplyAreaState;
  /** The warnings of the analysis; empty without a ready analysis. */
  readonly warnings: readonly SuggestionWarning[];
};

/** What staff do: a mode of a ready draft, or `writing` a reply when there is none. */
export type ComposerMode = DraftMode | "writing";

/**
 * Read what the composer needs of the ticket.
 *
 * @param workspace - The ticket.
 * @param regions - The state of its reply area and the warnings of its analysis.
 * @returns The allowed actions, the authority flag, whether the AI is running, the current
 *   suggestion, its ready draft, and its warnings.
 */
export function toComposerTicket(
  workspace: TicketWorkspace,
  regions: ComposerRegions,
): ComposerTicket {
  const suggestionId = workspace.suggestion?.suggestionId;
  const draftText = regions.reply.kind === "draft" ? regions.reply.draft.text : undefined;
  return {
    allowedActions: workspace.allowedActions,
    isAuthorityRequired: workspace.isAuthorityRequired,
    isSuggestionRunning: hasPendingPart(workspace),
    isIntentChoiceNeeded: regions.reply.kind === "choose_intent",
    ...(suggestionId === undefined ? {} : { suggestionId }),
    ...(suggestionId === undefined || draftText === undefined
      ? {}
      : { draft: { suggestionId, text: draftText } }),
    warningIds: regions.warnings.map((warning) => warning.warningId),
  };
}

/**
 * Choose what staff do now.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The draft mode while there is a ready draft; `writing` otherwise.
 */
export function getComposerMode(ticket: ComposerTicket, state: ComposerState): ComposerMode {
  return ticket.draft === undefined ? "writing" : state.draftMode;
}

/**
 * Read the text that Send reply sends.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The draft's `text` while staff read the draft as is; the editor's text otherwise.
 */
export function getReplyBody(ticket: ComposerTicket, state: ComposerState): string {
  return ticket.draft !== undefined && state.draftMode === "viewing"
    ? ticket.draft.text
    : state.body;
}

/**
 * Tell whether staff may edit or reject the draft (console UI design, Actions): the draft is
 * ready, and `backend` allows a reply or a reply proposal.
 *
 * @param ticket - The ticket.
 * @returns True when Edit draft and Reject draft are enabled.
 */
export function canChangeDraft(ticket: ComposerTicket): boolean {
  return (
    ticket.draft !== undefined &&
    (ticket.allowedActions.has("send_reply") || ticket.allowedActions.has("submit_reply_proposal"))
  );
}

/**
 * Tell whether two confirmations send the same reply, so the second reuses the
 * `Idempotency-Key` of the first (TS-29). The bodies are built by {@link buildSendReplyRequest},
 * so equal requests serialize equally.
 *
 * @param first - The request of the earlier confirmation.
 * @param second - The request of the later one.
 * @returns True when the requests are equal.
 */
export function isSameReply(
  first: SendReplyRequestContract,
  second: SendReplyRequestContract,
): boolean {
  return JSON.stringify(first) === JSON.stringify(second);
}

/**
 * Build the body of `sendReply`, with the basis of the console UI design (Actions):
 * `ai_draft` for a ready draft sent as is or edited, with every warning acknowledged;
 * `rejected_ai_draft` with the chosen reason codes; `no_ai_draft` without a ready draft.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The request body.
 */
export function buildSendReplyRequest(
  ticket: ComposerTicket,
  state: ComposerState,
): SendReplyRequestContract {
  const body = getReplyBody(ticket, state);
  const draft = ticket.draft;
  if (draft === undefined) {
    return {
      basis: "no_ai_draft",
      body,
      ...(ticket.suggestionId === undefined ? {} : { suggestion_id: ticket.suggestionId }),
    };
  }
  if (state.draftMode === "rejecting") {
    return {
      basis: "rejected_ai_draft",
      body,
      suggestion_id: draft.suggestionId,
      staff_reason_codes: staffReasonCodes.filter((code) => state.reasonCodes.has(code)),
      ...(state.reasonCodes.has("other") ? { note: state.note } : {}),
    };
  }
  return {
    basis: "ai_draft",
    body,
    suggestion_id: draft.suggestionId,
    acknowledged_warning_ids: [...ticket.warningIds],
  };
}

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

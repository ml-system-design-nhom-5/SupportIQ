/**
 * The reply that Send reply sends (console UI design, Actions): its `basis` follows from what
 * staff did, and it names only the warnings that staff acknowledged, so `422` stays the backstop of
 * UI-18. `backend` checks every rule again and refuses with `403`, `409`, or `422` (FR-04, FR-06,
 * SEC-38). Nothing here sends: only a staff click and a confirmation send a reply.
 */
import type { SendReplyRequestContract } from "@/features/console-tickets/api/contract-types";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type { ComposerState, DraftMode } from "@/features/console-tickets/model/reply-composer";
import { staffReasonCodes } from "@/features/console-tickets/model/staff-reason-codes";
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
  /** True once the ticket is closed: its reply was sent. */
  readonly isClosed: boolean;
  /**
   * True while a part of the current suggestion is `pending`, or while an intent correction or Try
   * AI again is sending, which starts a new suggestion.
   */
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
 * @param isSuggestionRequested - True while an intent correction or Try AI again is sending.
 * @returns The allowed actions, the authority flag, whether the ticket is closed, whether the AI
 *   is running, the current suggestion, its ready draft, and its warnings.
 */
export function toComposerTicket(
  workspace: TicketWorkspace,
  regions: ComposerRegions,
  isSuggestionRequested: boolean,
): ComposerTicket {
  const suggestionId = workspace.suggestion?.suggestionId;
  const draftText = regions.reply.kind === "draft" ? regions.reply.draft.text : undefined;
  return {
    allowedActions: workspace.allowedActions,
    isAuthorityRequired: workspace.isAuthorityRequired,
    isClosed: workspace.status === "closed",
    isSuggestionRunning: isSuggestionRequested || hasPendingPart(workspace),
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
 * `ai_draft` for a ready draft sent as is or edited, with the warnings that staff acknowledged;
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
    acknowledged_warning_ids: ticket.warningIds.filter((warningId) =>
      state.acknowledgedWarningIds.has(warningId),
    ),
  };
}

/**
 * What the reply composer reads of the ticket (console UI design, Actions and States): the
 * actions that `backend` allows, whether the AI is running, and the ready text that staff start
 * from: the AI draft of the current suggestion, or, for a manager on a ticket awaiting approval,
 * the reply proposal (FR-06). The UI decides no permission itself (UI-40).
 */
import type { ConsoleTicketStatusName } from "@/design-system";
import type { SuggestionWarning } from "@/features/console-tickets/model/reason-codes";
import type {
  ComposedTextOwner,
  ComposerState,
  DraftMode,
} from "@/features/console-tickets/model/reply-composer";
import type { TicketAction } from "@/features/console-tickets/model/ticket-actions";
import type { TicketWorkspace } from "@/features/console-tickets/model/workspace";
import {
  hasPendingPart,
  type ReplyAreaState,
} from "@/features/console-tickets/model/workspace-state";

/**
 * The ready text that staff start from.
 * `ai_draft`: the ready draft of the current suggestion.
 * `reply_proposal`: the proposal that a manager sends as is or edited.
 */
export type ComposerDraft =
  | { readonly kind: "ai_draft"; readonly suggestionId: string; readonly text: string }
  | { readonly kind: "reply_proposal"; readonly proposalId: string; readonly text: string };

/**
 * Where staff write a reply without a draft, which changes what the action bar asks for.
 * `manual_handling`: the AI could not help, or the ticket is in `manual` mode (UI-26).
 * `escalation_recommended`: the AI recommends an escalation (ESC-03).
 */
export type ComposerSituation = "manual_handling" | "escalation_recommended";

/** A write of the reply area that is sending and hands the ticket to a manager. */
export type HandoverWrite = "submit_reply_proposal" | "escalate";

/** What the composer needs to know of the ticket, derived from the workspace. */
export type ComposerTicket = {
  readonly status: ConsoleTicketStatusName;
  /** True for a manager, who sends the reply where staff submit it for approval (FR-06). */
  readonly isManager: boolean;
  /** The write that is sending and hands the ticket to a manager; absent while none is. */
  readonly handover?: HandoverWrite;
  readonly allowedActions: ReadonlySet<TicketAction>;
  readonly isAuthorityRequired: boolean;
  /**
   * True while a part of the current suggestion is `pending`, or while an intent correction or Try
   * AI again is sending, which starts a new suggestion.
   */
  readonly isSuggestionRunning: boolean;
  /** True when the AI abstained for low confidence: staff choose an intent first (ESC-01). */
  readonly isIntentChoiceNeeded: boolean;
  /** The current suggestion; absent in `manual` mode. */
  readonly suggestionId?: string;
  /** The ready text that staff start from; absent when there is none. */
  readonly draft?: ComposerDraft;
  /** Where staff write without a draft; absent everywhere else. */
  readonly situation?: ComposerSituation;
  /** The `warning_id` of every warning that a reply based on the AI draft acknowledges. */
  readonly warningIds: readonly string[];
};

/** What the composer reads of the regions of the workspace. */
export type ComposerRegions = {
  readonly reply: ReplyAreaState;
  /** The warnings of the analysis; empty without a ready analysis. */
  readonly warnings: readonly SuggestionWarning[];
};

/** What staff do: a mode of the ready text, or `writing` a reply when there is none. */
export type ComposerMode = DraftMode | "writing";

/** What the workspace knows besides the ticket. */
export type ComposerContext = {
  /** True while an intent correction or Try AI again is sending. */
  readonly isSuggestionRequested: boolean;
  /** True when the session is a manager's. */
  readonly isManager: boolean;
};

/**
 * Read what the composer needs of the ticket.
 *
 * @param workspace - The ticket.
 * @param regions - The state of its reply area and the warnings of its analysis.
 * @param context - Whether a new suggestion is requested, and whether the session is a manager's.
 * @returns The status, the role, the allowed actions, the authority flag, whether the AI is
 *   running, the current suggestion, the ready text, where staff write without one, and the
 *   warnings.
 */
export function toComposerTicket(
  workspace: TicketWorkspace,
  regions: ComposerRegions,
  context: ComposerContext,
): ComposerTicket {
  const suggestionId = workspace.suggestion?.suggestionId;
  const { reply } = regions;
  const situation = getSituation(reply);
  const { isSuggestionRequested } = context;
  return {
    status: workspace.status,
    isManager: context.isManager,
    allowedActions: workspace.allowedActions,
    isAuthorityRequired: workspace.isAuthorityRequired,
    isSuggestionRunning: isSuggestionRequested || hasPendingPart(workspace),
    isIntentChoiceNeeded: reply.kind === "choose_intent",
    ...(suggestionId === undefined ? {} : { suggestionId }),
    ...toComposerDraft(reply, suggestionId),
    ...(situation === undefined ? {} : { situation }),
    warningIds: reply.kind === "draft" ? regions.warnings.map((warning) => warning.warningId) : [],
  };
}

/**
 * Choose what staff do now.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The draft mode while there is a ready text; `writing` otherwise.
 */
export function getComposerMode(ticket: ComposerTicket, state: ComposerState): ComposerMode {
  return ticket.draft === undefined ? "writing" : state.draftMode;
}

/**
 * Read the text that Send reply or Submit for approval sends.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The ready text while staff read it as is; the editor's text otherwise. A proposal is
 *   sent as is unless the manager edits it, so no other text is ever sent as the proposal.
 */
export function getReplyBody(ticket: ComposerTicket, state: ComposerState): string {
  const { draft } = ticket;
  if (draft?.kind === "reply_proposal") {
    return state.draftMode === "editing" ? state.body : draft.text;
  }
  return draft !== undefined && state.draftMode === "viewing" ? draft.text : state.body;
}

/**
 * Name the ready text that what staff composed belongs to: the current suggestion and, while the
 * ticket awaits approval, its proposal (FR-06).
 *
 * @param ticket - The ticket.
 * @returns The suggestion and the proposal.
 */
export function getComposedTextOwner(ticket: ComposerTicket): ComposedTextOwner {
  return {
    suggestionId: ticket.suggestionId,
    proposalId: ticket.draft?.kind === "reply_proposal" ? ticket.draft.proposalId : undefined,
  };
}

/**
 * Tell whether staff may edit or reject the AI draft (console UI design, Actions): the draft is
 * ready, and `backend` allows a reply or a reply proposal.
 *
 * @param ticket - The ticket.
 * @returns True when Edit draft and Reject draft are enabled.
 */
export function canChangeDraft(ticket: ComposerTicket): boolean {
  return (
    ticket.draft?.kind === "ai_draft" &&
    (ticket.allowedActions.has("send_reply") || ticket.allowedActions.has("submit_reply_proposal"))
  );
}

/**
 * Tell whether a manager may edit the proposal (Edit proposal): the ticket awaits approval, and
 * `backend` allows the manager to send its reply.
 *
 * @param ticket - The ticket.
 * @returns True when Edit proposal is enabled.
 */
export function canEditProposal(ticket: ComposerTicket): boolean {
  return ticket.draft?.kind === "reply_proposal" && ticket.allowedActions.has("send_reply");
}

/**
 * Read the ready text of the reply area.
 *
 * @param reply - The state of the reply area.
 * @param suggestionId - The current suggestion.
 * @returns The proposal of a ticket awaiting approval, the AI draft to review, or nothing, as a
 *   member to spread.
 */
function toComposerDraft(
  reply: ReplyAreaState,
  suggestionId: string | undefined,
): { readonly draft?: ComposerDraft } {
  if (reply.kind === "proposal") {
    const { proposalId, body } = reply.proposal;
    return { draft: { kind: "reply_proposal", proposalId, text: body } };
  }
  return reply.kind === "draft" && suggestionId !== undefined
    ? { draft: { kind: "ai_draft", suggestionId, text: reply.draft.text } }
    : {};
}

/**
 * Tell where staff write a reply without a draft.
 *
 * @param reply - The state of the reply area.
 * @returns Manual handling, an escalation recommendation, or undefined.
 */
function getSituation(reply: ReplyAreaState): ComposerSituation | undefined {
  if (reply.kind === "manual_mode" || reply.kind === "ai_unavailable") {
    return "manual_handling";
  }
  return reply.kind === "no_draft" && reply.status === "escalation_recommended"
    ? "escalation_recommended"
    : undefined;
}

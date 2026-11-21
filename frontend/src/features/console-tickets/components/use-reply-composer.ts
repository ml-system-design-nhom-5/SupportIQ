/**
 * The reply area of one opened ticket (console UI design, Actions and Dialogs): what staff
 * composed, the main action and why it is disabled, Send reply with its confirmation (UI-17),
 * Submit for approval, and Escalate ticket. The state lives as long as the ticket is open, so a
 * reload of the workspace keeps the text that staff typed; it is never written to browser storage,
 * because it is Confidential. It follows the ready text of the ticket: a new suggestion or a new
 * proposal resets what belonged to the old one. While Submit for approval or Escalate ticket is
 * sending, the other actions wait, so two writes never race.
 */
import { type Dispatch, type SetStateAction, useState } from "react";

import {
  type Escalation,
  useEscalation,
} from "@/features/console-tickets/components/use-escalation";
import {
  type ProposalSubmission,
  useProposalSubmission,
} from "@/features/console-tickets/components/use-proposal-submission";
import {
  type ReplySending,
  useReplySending,
} from "@/features/console-tickets/components/use-reply-sending";
import {
  canChangeDraft,
  canEditProposal,
  type ComposerMode,
  type ComposerTicket,
  getComposedTextOwner,
  getComposerMode,
  getReplyBody,
} from "@/features/console-tickets/model/composer-ticket";
import {
  findActionNote,
  findReplyBlock,
  getPrimaryAction,
  type ReplyAction,
} from "@/features/console-tickets/model/reply-block";
import {
  type ComposerState,
  createComposerState,
  followSuggestion,
} from "@/features/console-tickets/model/reply-composer";
import {
  pickLatestFailure,
  type ReplyFailureView,
} from "@/features/console-tickets/model/reply-failure";

/** The reply area of the opened ticket. */
export type ReplyComposer = Omit<ReplySending, "sendFailure"> &
  Omit<ProposalSubmission, "submitFailure"> & {
    /** What staff composed, for the current ready text. */
    readonly state: ComposerState;
    /** What staff do: a mode of the ready text, or `writing` without one. */
    readonly mode: ComposerMode;
    /** True when Edit draft and Reject draft are enabled. */
    readonly canChangeDraft: boolean;
    /** True when a manager may edit the proposal (Edit proposal). */
    readonly canEditProposal: boolean;
    /** True in manual handling, where Submit for approval is a visible button (UI-16, UI-26). */
    readonly isManualHandling: boolean;
    /** True when `backend` allows a reply or a proposal, so the editor is shown. */
    readonly canWrite: boolean;
    /** True when `backend` allows Submit for approval, so More is enabled. */
    readonly canSubmit: boolean;
    /** Changes what staff composed. */
    readonly change: (update: (state: ComposerState) => ComposerState) => void;
    /** The text that the main action sends. */
    readonly body: string;
    /** The main action, on the right of the action bar (UI-16). */
    readonly primaryAction: ReplyAction;
    /** Why the main action is disabled; undefined when it is enabled. */
    readonly primaryBlock: string | undefined;
    /** Why Submit for approval is disabled; undefined when it is enabled. */
    readonly submitBlock: string | undefined;
    /** The line above the buttons: why an action is disabled, or a note. */
    readonly barLine: string | undefined;
    /** The latest failed write of the reply area, in plain language. */
    readonly failure: ReplyFailureView | undefined;
    /** Escalate ticket and its dialog. */
    readonly escalation: Escalation;
  };

/** What happens after an action of the reply area succeeded. */
export type ReplyComposerEvents = {
  readonly onSent: () => void;
  readonly onSubmitted: () => void;
  readonly onEscalated: () => void;
};

/**
 * Keep the reply area of a ticket.
 *
 * @param ticketId - The ticket of the address, the ticket of every write.
 * @param ticket - What the composer reads of the ticket.
 * @param events - Called once a reply was sent, a proposal was submitted, or the ticket was
 *   escalated.
 * @returns The state, its change, the main action and its block, and the handlers of the writes.
 */
export function useReplyComposer(
  ticketId: string,
  ticket: ComposerTicket,
  events: ReplyComposerEvents,
): ReplyComposer {
  const [state, setState] = useComposerState(ticket);
  // Once the ticket went to a manager, by staff or by a colleague, what staff composed is done
  // with; after a colleague's action, the unsent text stays to copy (console UI design, Flow, 6).
  const startOver = () => {
    setState(createComposerState(ticket.suggestionId));
  };
  const submission = useProposalSubmission(ticketId, { ticket, state }, () => {
    startOver();
    events.onSubmitted();
  });
  const escalation = useEscalation(ticketId, ticket, () => {
    startOver();
    events.onEscalated();
  });
  const busyTicket = withHandover(ticket, submission.isSubmitting, escalation.isEscalating);
  const sendBlock = findReplyBlock(busyTicket, state, "send_reply");
  const { sendFailure, ...sending } = useReplySending(
    ticketId,
    { ticket, state, sendBlock },
    { onSent: events.onSent, onTakenByColleague: startOver },
  );
  return {
    ...describeComposition(busyTicket, state, setState),
    ...sending,
    submit: submission.submit,
    isSubmitting: submission.isSubmitting,
    failure: pickLatestFailure([sendFailure, submission.submitFailure, escalation.closedFailure]),
    escalation: { ...escalation, canEscalate: escalation.canEscalate && !submission.isSubmitting },
  };
}

/**
 * Keep what staff composed with the ready text of the ticket, during the render that shows a new
 * suggestion or proposal (TS-21).
 *
 * @param ticket - The ticket.
 * @returns The state for the current ready text, and its setter.
 */
function useComposerState(
  ticket: ComposerTicket,
): readonly [ComposerState, Dispatch<SetStateAction<ComposerState>>] {
  const owner = getComposedTextOwner(ticket);
  const [stored, setState] = useState(() =>
    createComposerState(owner.suggestionId, owner.proposalId),
  );
  const state = followSuggestion(stored, owner);
  if (state !== stored) {
    setState(state);
  }
  return [state, setState];
}

/**
 * Describe what staff composed and what the actions of the bar may do with it.
 *
 * @param ticket - The ticket, with the write that is sending.
 * @param state - What staff composed.
 * @param change - Changes what staff composed.
 * @returns The state, the mode, the main action, the blocks, and the line above the buttons.
 */
function describeComposition(
  ticket: ComposerTicket,
  state: ComposerState,
  change: ReplyComposer["change"],
) {
  const primaryAction = getPrimaryAction(ticket);
  const primaryBlock = findReplyBlock(ticket, state, primaryAction);
  const submitBlock = findReplyBlock(ticket, state, "submit_reply_proposal");
  const isManualHandling = ticket.situation === "manual_handling";
  const { allowedActions } = ticket;
  return {
    state,
    mode: getComposerMode(ticket, state),
    canChangeDraft: canChangeDraft(ticket),
    canEditProposal: canEditProposal(ticket),
    isManualHandling,
    canWrite: allowedActions.has("send_reply") || allowedActions.has("submit_reply_proposal"),
    canSubmit: allowedActions.has("submit_reply_proposal"),
    change,
    body: getReplyBody(ticket, state),
    primaryAction,
    primaryBlock,
    submitBlock,
    // A visible Submit for approval says why it is disabled while Send reply is enabled (UI-16):
    // the note of a manager names it, and for staff its own block follows.
    barLine: primaryBlock ?? findActionNote(ticket) ?? (isManualHandling ? submitBlock : undefined),
  };
}

/**
 * Mark the write that is sending and hands the ticket to a manager.
 *
 * @param ticket - The ticket.
 * @param isSubmitting - True while Submit for approval is sending.
 * @param isEscalating - True while Escalate ticket is sending.
 * @returns The ticket with the write, or the same ticket while none is sending.
 */
function withHandover(
  ticket: ComposerTicket,
  isSubmitting: boolean,
  isEscalating: boolean,
): ComposerTicket {
  if (isSubmitting) {
    return { ...ticket, handover: "submit_reply_proposal" };
  }
  return isEscalating ? { ...ticket, handover: "escalate" } : ticket;
}

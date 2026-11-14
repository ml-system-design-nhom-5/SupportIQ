/**
 * What the reply area says when Send reply or Submit for approval fails (console UI design, Flow
 * and Errors and guardrails). Every problem becomes plain language (UI-25), and the text in the editor is never
 * lost. A refusal that means the ticket changed reloads the workspace, so staff see its current
 * state. After a timeout, a lost connection, `502`, or `504`, nobody knows whether the reply
 * arrived; sending the same reply again reuses its key, so it arrives once (ERR-16).
 */
import {
  categorizeFailure,
  describeFailure,
  type FailureCategory,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import type { ReplyAction } from "@/features/console-tickets/model/send-block";

/** How the reply area shows a failed Send reply or Submit for approval. */
export type SendFailureView = FailureView & {
  /** True when the workspace loads the ticket again. */
  readonly shouldReload: boolean;
};

/** The categories whose refusal says that the ticket changed, with what the reply area says. */
const messageByReloadedCategory: ReadonlyMap<FailureCategory, string> = new Map([
  ["suggestion_pending", "The AI is still working on this ticket. Your text is kept."],
  [
    "suggestion_superseded",
    "The AI made a new draft for this ticket. Check it; your text is kept.",
  ],
  ["invalid_state", "This ticket was already handled. It now shows its current state."],
  [
    "permission_denied",
    "A colleague escalated this ticket or submitted it for approval. Your text is kept.",
  ],
  [
    "authority_required",
    "Only a manager can send the reply of this ticket. Submit it for approval instead.",
  ],
]);

/** What a failed action says of the reply, by action. */
type ReplyFailureTexts = {
  readonly notDone: string;
  readonly unknownOutcome: string;
  readonly unknownOutcomeMessage: string;
};

/** A write of the reply area: Send reply, Submit for approval, or Escalate ticket. */
export type ReplyAreaWrite = ReplyAction | "escalate";

const textsByAction: Readonly<Record<ReplyAreaWrite, ReplyFailureTexts>> = {
  send_reply: {
    notDone: "The reply was not sent.",
    unknownOutcome: "The reply may have been sent.",
    unknownOutcomeMessage:
      "We could not confirm it. Sending the same reply again is safe: the customer gets it once.",
  },
  submit_reply_proposal: {
    notDone: "The reply was not submitted.",
    unknownOutcome: "The reply may have been submitted.",
    unknownOutcomeMessage:
      "We could not confirm it. Submitting the same reply again is safe: a manager gets it once.",
  },
  escalate: {
    notDone: "The ticket was not escalated.",
    unknownOutcome: "The ticket may have been escalated.",
    unknownOutcomeMessage:
      "We could not confirm it. Escalating again with the same reasons is safe: it is escalated once.",
  },
};

/**
 * Describe a failed Send reply, Submit for approval, or Escalate ticket.
 *
 * @param failure - The failure of `sendReply`, `createReplyProposal`, or `createEscalation`.
 * @param action - The action that failed.
 * @returns The lead, the message, whether the workspace reloads, and the trace ID.
 */
export function describeReplyFailure(
  failure: RequestFailure,
  action: ReplyAreaWrite,
): SendFailureView {
  const { message, traceId } = describeFailure(failure);
  const traceIdView = traceId === undefined ? {} : { traceId };
  const texts = textsByAction[action];
  if (isWriteOutcomeUnknown(failure)) {
    return {
      lead: texts.unknownOutcome,
      message: texts.unknownOutcomeMessage,
      shouldReload: false,
      ...traceIdView,
    };
  }
  const reloadedMessage = messageByReloadedCategory.get(categorizeFailure(failure));
  return {
    lead: texts.notDone,
    message: reloadedMessage ?? message,
    shouldReload: reloadedMessage !== undefined,
    ...traceIdView,
  };
}

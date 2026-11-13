/**
 * What the reply area says when Send reply fails (console UI design, Flow and Errors and
 * guardrails). Every problem becomes plain language (UI-25), and the text in the editor is never
 * lost. A refusal that means the ticket changed reloads the workspace, so staff see its current
 * state. After a timeout, a lost connection, `502`, or `504`, nobody knows whether the reply
 * arrived; confirming the same reply again reuses its key, so the customer gets it once (ERR-16).
 */
import {
  categorizeFailure,
  describeFailure,
  type FailureCategory,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";

/** How the reply area shows a failed send. */
export type SendFailureView = {
  /** The bold first sentence: what happened to the reply. */
  readonly lead: string;
  /** What it means and what to do next. */
  readonly message: string;
  /** True when the workspace loads the ticket again. */
  readonly shouldReload: boolean;
  readonly traceId?: string;
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

/**
 * Describe a failed send.
 *
 * @param failure - The failure of `sendReply`.
 * @returns The lead, the message, whether the workspace reloads, and the trace ID.
 */
export function describeSendFailure(failure: RequestFailure): SendFailureView {
  const { message, traceId } = describeFailure(failure);
  const traceIdView = traceId === undefined ? {} : { traceId };
  if (isWriteOutcomeUnknown(failure)) {
    return {
      lead: "The reply may have been sent.",
      message:
        "We could not confirm it. Sending the same reply again is safe: the customer gets it once.",
      shouldReload: false,
      ...traceIdView,
    };
  }
  const reloadedMessage = messageByReloadedCategory.get(categorizeFailure(failure));
  return {
    lead: "The reply was not sent.",
    message: reloadedMessage ?? message,
    shouldReload: reloadedMessage !== undefined,
    ...traceIdView,
  };
}

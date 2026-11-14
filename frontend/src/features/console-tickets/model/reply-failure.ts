/**
 * What the reply area says when Send reply, Submit for approval, or Escalate ticket fails (console
 * UI design, Flow and Errors and guardrails). Every problem becomes plain language (UI-25), and the
 * text in the editor is never lost. A refusal that means the ticket changed reloads the workspace,
 * so staff see its current state. After a timeout, a lost connection, `502`, or `504`, nobody
 * knows whether the write arrived; sending it again reuses its key, so it happens once (ERR-16).
 */
import {
  categorizeFailure,
  describeFailure,
  type FailureCategory,
  getRequestFailure,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import type { TicketAction } from "@/features/console-tickets/model/ticket-actions";

/** How the reply area shows a failed write. */
export type ReplyFailureView = FailureView & {
  /** True when the workspace loads the ticket again. */
  readonly shouldReload: boolean;
};

/** A failed write, and when it was sent, so the reply area shows the latest one. */
export type DatedFailure = {
  readonly view: ReplyFailureView;
  /** When the failed request was sent, in milliseconds since the epoch. */
  readonly submittedAt: number;
};

/** What the reply area reads of the mutation of a write. */
export type WriteOutcome = {
  readonly error: Error | null;
  /** When the last request was sent, in milliseconds since the epoch. */
  readonly submittedAt: number;
};

/** A write of the reply area: Send reply, Submit for approval, or Escalate ticket. */
export type ReplyAreaWrite = Extract<
  TicketAction,
  "send_reply" | "submit_reply_proposal" | "escalate"
>;

/** The refusals of every write that mean the ticket changed, with what the reply area says. */
const changedTicketMessages: readonly (readonly [FailureCategory, string])[] = [
  ["suggestion_pending", "The AI is still working on this ticket. Your text is kept."],
  [
    "suggestion_superseded",
    "The AI made a new draft for this ticket. Check it; your text is kept.",
  ],
  ["invalid_state", "This ticket was already handled. It now shows its current state."],
];

/**
 * The refusals of each write that reload the workspace. For `sendReply`, `403 forbidden` means that
 * a colleague escalated or submitted the ticket. For `createReplyProposal` and `createEscalation`,
 * a colleague's action answers `409 invalid-ticket-state`, and `403` only means a refused `Origin`,
 * which the shared message explains (contract, `ForbiddenRoleOrOrigin`).
 */
const reloadedMessagesByWrite: Readonly<
  Record<ReplyAreaWrite, ReadonlyMap<FailureCategory, string>>
> = {
  send_reply: new Map([
    ...changedTicketMessages,
    [
      "permission_denied",
      "A colleague escalated this ticket or submitted it for approval. Your text is kept.",
    ],
    [
      "authority_required",
      "Only a manager can send the reply of this ticket. Submit it for approval instead.",
    ],
  ]),
  submit_reply_proposal: new Map(changedTicketMessages),
  escalate: new Map(changedTicketMessages),
};

/** What a failed write says of itself. */
type WriteFailureTexts = {
  readonly notDone: string;
  readonly unknownOutcome: string;
  readonly unknownOutcomeMessage: string;
};

const textsByWrite: Readonly<Record<ReplyAreaWrite, WriteFailureTexts>> = {
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
 * @param write - The write that failed.
 * @returns The lead, the message, whether the workspace reloads, and the trace ID.
 */
export function describeReplyFailure(
  failure: RequestFailure,
  write: ReplyAreaWrite,
): ReplyFailureView {
  const { message, traceId } = describeFailure(failure);
  const traceIdView = traceId === undefined ? {} : { traceId };
  const texts = textsByWrite[write];
  if (isWriteOutcomeUnknown(failure)) {
    return {
      lead: texts.unknownOutcome,
      message: texts.unknownOutcomeMessage,
      shouldReload: false,
      ...traceIdView,
    };
  }
  const reloadedMessage = reloadedMessagesByWrite[write].get(categorizeFailure(failure));
  return {
    lead: texts.notDone,
    message: reloadedMessage ?? message,
    shouldReload: reloadedMessage !== undefined,
    ...traceIdView,
  };
}

/**
 * Read the last failure of a write.
 *
 * @param outcome - The error of the mutation and when its request was sent.
 * @param write - The write.
 * @returns The failure in plain language, with when it was sent; undefined without one.
 */
export function readDatedFailure(
  outcome: WriteOutcome,
  write: ReplyAreaWrite,
): DatedFailure | undefined {
  const failure = getRequestFailure(outcome.error);
  return failure === undefined
    ? undefined
    : { view: describeReplyFailure(failure, write), submittedAt: outcome.submittedAt };
}

/**
 * Choose the failure that the reply area shows: the one of the latest request.
 *
 * @param failures - The failures of the writes; undefined for a write without one.
 * @returns The latest failure, or undefined when no write failed.
 */
export function pickLatestFailure(
  failures: readonly (DatedFailure | undefined)[],
): ReplyFailureView | undefined {
  let latest: DatedFailure | undefined;
  for (const failure of failures) {
    if (
      failure !== undefined &&
      (latest === undefined || failure.submittedAt > latest.submittedAt)
    ) {
      latest = failure;
    }
  }
  return latest?.view;
}

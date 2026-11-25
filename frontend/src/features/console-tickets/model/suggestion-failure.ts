/**
 * What a failed `createSuggestion` says (UI-25): a correction of the intent (UI-22, UI-42), or Try
 * AI again (UI-26). A refusal that means the screen was old says that the ticket changed, because
 * the workspace reloads after it (console UI design, Flow step 4, Errors and guardrails). After an
 * unknown outcome, nobody knows whether `backend` started the suggestion, so the lead never says
 * that it did not happen (ERR-07, ERR-16).
 */
import {
  describeFailure,
  type FailureCategory,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";
import type { FailureView } from "@/features/console-tickets/model/failure-view";

/** What a refusal of an old screen says; the workspace reloads after it. */
const OLD_SCREEN_MESSAGE = "This ticket changed in the meantime. It now shows its current state.";

/**
 * The refusals of an old screen that {@link OLD_SCREEN_MESSAGE} explains: no intent is known any
 * more, or nothing can be retried (`422`), or the ticket is no longer open in `assisted` mode
 * (`409 invalid-ticket-state`).
 */
const oldScreenCategories: ReadonlySet<FailureCategory> = new Set([
  "invalid_request",
  "invalid_state",
]);

/** The request that failed: a correction of the intent, or Try AI again. */
export type SuggestionRequestKind = "correction" | "retry";

/** The leads of a request: when it did not happen, and when nobody knows. */
type SuggestionFailureLeads = {
  readonly notDone: string;
  readonly unknownOutcome: string;
};

/** The leads of each request. */
const leadsByRequest: Readonly<Record<SuggestionRequestKind, SuggestionFailureLeads>> = {
  correction: {
    notDone: "The intent was not changed.",
    unknownOutcome: "The intent may have been changed.",
  },
  retry: {
    notDone: "The AI did not start again.",
    unknownOutcome: "The AI may have started again.",
  },
};

/**
 * Describe a failed correction or retry. A refusal of an old screen says that the ticket changed;
 * every other failure uses the shared message (TS-26).
 *
 * @param failure - The failure of `createSuggestion`.
 * @param request - The request that failed.
 * @returns The lead, the message, and the trace ID when there is one. After an unknown outcome,
 *   the lead says that the request may have happened.
 */
export function describeSuggestionFailure(
  failure: RequestFailure,
  request: SuggestionRequestKind,
): FailureView {
  const description = describeFailure(failure);
  const leads = leadsByRequest[request];
  return {
    lead: isWriteOutcomeUnknown(failure) ? leads.unknownOutcome : leads.notDone,
    message: oldScreenCategories.has(description.category)
      ? OLD_SCREEN_MESSAGE
      : description.message,
    ...(description.traceId === undefined ? {} : { traceId: description.traceId }),
  };
}

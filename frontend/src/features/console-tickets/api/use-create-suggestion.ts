/**
 * Start a new suggestion for a ticket (`createSuggestion`): correct or confirm the intent with
 * `intent_override` (UI-22, UI-42), or retry the AI after a failure without it (UI-26). `backend`
 * answers `202` with the new suggestion, `pending`, which the workspace shows at once and then polls
 * until no part is pending (console UI design, Flow). Each action needs its action in
 * `allowed_actions`; the UI never decides that itself (UI-40).
 *
 * One `Idempotency-Key` belongs to one staff action: automatic retries reuse it, and so does the
 * same action repeated after a failure, so a lost answer never starts a second suggestion (TS-29,
 * ERR-15). A refusal that means the screen was old, or a failure whose outcome is unknown, reloads
 * the workspace (console UI design, Flow step 4, Errors and guardrails).
 */
import {
  type QueryClient,
  useMutation,
  type UseMutationResult,
  useQueryClient,
} from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import {
  buildIdempotentWriteKey,
  getRequestFailure,
  isWriteOutcomeUnknown,
  type ProblemType,
  requestData,
  type RequestFailure,
  useFormIdempotencyKey,
  useWriteAttemptSender,
} from "@/features/backend-requests";
import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import type { ChoosableIntentLabel } from "@/features/console-tickets/model/intent-area";
import type { TicketAction } from "@/features/console-tickets/model/ticket-actions";
import {
  type Suggestion,
  type TicketWorkspace,
  toSuggestion,
} from "@/features/console-tickets/model/workspace";

/**
 * The refusals of an old screen: no intent is known while a part is pending, no intent is known
 * at all or nothing can be retried (`422`), or the ticket is no longer open in `assisted` mode.
 */
const problemTypesOfOldScreens: ReadonlySet<ProblemType> = new Set([
  "suggestion_pending",
  "invalid_request",
  "invalid_ticket_state",
]);

/** One staff action: a correction with the intent that staff chose, or a retry without one. */
type SuggestionRequest = {
  readonly idempotencyKey: string;
  /** The intent that staff chose; absent for a retry. */
  readonly intentOverride?: ChoosableIntentLabel;
  /** The ready draft that a correction makes outdated; absent when there was none. */
  readonly outdatedDraft?: ReadyDraft;
};

/** The mutation of `createSuggestion`. */
type SuggestionMutation = UseMutationResult<Suggestion, Error, SuggestionRequest>;

/** The requests of a ticket's suggestion, and their state. */
export type SuggestionRequests = {
  /**
   * Confirm or correct the intent (UI-22, UI-42). Does nothing without `correct_intent`, or while a
   * request is sending.
   */
  readonly correctIntent: (intentLabel: ChoosableIntentLabel) => void;
  /** Retry the AI (UI-26). Does nothing without `retry_suggestion`, or while a request is sending. */
  readonly retry: () => void;
  /** True while a correction or a retry is sending, with its automatic retries. */
  readonly isSending: boolean;
  /** The failure of the last correction; absent once another request starts. */
  readonly correctionFailure?: RequestFailure;
  /** The failure of the last retry; absent once another request starts. */
  readonly retryFailure?: RequestFailure;
  /**
   * The draft that was ready when the last correction succeeded, which the reply area marks as
   * outdated while the new draft generates (UI-22). Present only while the suggestion that the
   * correction started is the ticket's current one.
   */
  readonly outdatedDraft?: ReadyDraft;
};

/**
 * Correct the intent or retry the AI.
 *
 * @param ticketId - The ticket of the address, whose workspace query the requests update.
 * @param workspace - The ticket as the workspace shows it: its allowed actions and its current
 *   draft.
 * @returns The two requests, whether one is sending, their failures, and the outdated draft.
 */
export function useCreateSuggestion(
  ticketId: string,
  workspace: TicketWorkspace,
): SuggestionRequests {
  const mutation = useSuggestionMutation(ticketId);
  // One key for one action, like the fields of a form: the same intent, or a retry, sent again
  // after a failure keeps it; another action, or any action after a success, gets a new key.
  const { getOrCreateKey, forgetKey } = useFormIdempotencyKey();
  const send = (action: TicketAction, request: Omit<SuggestionRequest, "idempotencyKey">) => {
    if (mutation.isPending || !workspace.allowedActions.has(action)) {
      return;
    }
    if (!(mutation.isError && mutation.variables.intentOverride === request.intentOverride)) {
      forgetKey();
    }
    mutation.mutate({ ...request, idempotencyKey: getOrCreateKey() });
  };
  return {
    correctIntent: (intentLabel) => {
      send("correct_intent", { intentOverride: intentLabel, ...getReadyDraft(workspace) });
    },
    retry: () => {
      send("retry_suggestion", {});
    },
    isSending: mutation.isPending,
    ...describeOutcome(mutation, workspace),
  };
}

/**
 * Create the mutation. A success shows the new suggestion at once and loads the workspace again
 * for its actions; a refusal of an old screen, or an unknown outcome, loads it again as well.
 *
 * @param ticketId - The ticket.
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
function useSuggestionMutation(ticketId: string): SuggestionMutation {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadWorkspace = () =>
    queryClient.invalidateQueries({ queryKey: consoleQueryKeys.workspace(ticketId) });
  return useMutation({
    mutationKey: buildIdempotentWriteKey("createSuggestion"),
    mutationFn: (request: SuggestionRequest) =>
      sendAttempt(request.idempotencyKey, () => createSuggestion(client, ticketId, request)),
    onSuccess: (suggestion) => {
      showSuggestion(queryClient, ticketId, suggestion);
      void reloadWorkspace();
    },
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && shouldReloadAfter(failure)) {
        void reloadWorkspace();
      }
    },
  });
}

/**
 * Send the request.
 *
 * @param client - The backend client.
 * @param ticketId - The ticket.
 * @param request - The key, and the intent of a correction.
 * @returns The new suggestion, or the original one for a retry with the same key.
 */
function createSuggestion(
  client: BackendClient,
  ticketId: string,
  request: SuggestionRequest,
): Promise<Suggestion> {
  return requestData(
    () =>
      client.POST("/v1/console/tickets/{ticket_id}/suggestions", {
        params: {
          path: { ticket_id: ticketId },
          header: { "Idempotency-Key": request.idempotencyKey },
        },
        body:
          request.intentOverride === undefined ? {} : { intent_override: request.intentOverride },
      }),
    toSuggestion,
  );
}

/**
 * Show the new suggestion in the cached workspace, before it loads again. A cached workspace that
 * already holds it, from a load that answered first, stays as it is.
 *
 * @param queryClient - The query client.
 * @param ticketId - The ticket.
 * @param suggestion - The new suggestion.
 */
function showSuggestion(queryClient: QueryClient, ticketId: string, suggestion: Suggestion): void {
  queryClient.setQueryData<TicketWorkspace>(consoleQueryKeys.workspace(ticketId), (cached) =>
    cached === undefined || cached.suggestion?.suggestionId === suggestion.suggestionId
      ? cached
      : { ...cached, suggestion },
  );
}

/**
 * Tell whether a failure leaves the workspace out of date.
 *
 * @param failure - The failure of `createSuggestion`.
 * @returns True for a refusal of an old screen, and for an unknown outcome, after which a new
 *   suggestion may exist.
 */
function shouldReloadAfter(failure: RequestFailure): boolean {
  return (
    isWriteOutcomeUnknown(failure) ||
    (failure.kind === "problem" && problemTypesOfOldScreens.has(failure.problemType))
  );
}

/**
 * Read the draft of the current suggestion when it is ready, to keep it as the outdated draft.
 *
 * @param workspace - The ticket.
 * @returns The draft as a member to spread, or nothing without a ready draft.
 */
function getReadyDraft(workspace: TicketWorkspace): { readonly outdatedDraft?: ReadyDraft } {
  const draft = workspace.suggestion?.draft;
  return draft?.status === "draft_ready" ? { outdatedDraft: draft } : {};
}

/**
 * Describe the outcome of the last request.
 *
 * @param mutation - The mutation.
 * @param workspace - The ticket, whose current suggestion scopes the outdated draft.
 * @returns The failure of the correction or of the retry, or the outdated draft of a correction
 *   whose suggestion is still current.
 */
function describeOutcome(
  mutation: SuggestionMutation,
  workspace: TicketWorkspace,
): Pick<SuggestionRequests, "correctionFailure" | "retryFailure" | "outdatedDraft"> {
  if (mutation.isSuccess) {
    const isCurrent = mutation.data.suggestionId === workspace.suggestion?.suggestionId;
    const { outdatedDraft } = mutation.variables;
    return isCurrent && outdatedDraft !== undefined ? { outdatedDraft } : {};
  }
  const failure = getRequestFailure(mutation.error);
  if (!mutation.isError || failure === undefined) {
    return {};
  }
  return mutation.variables.intentOverride === undefined
    ? { retryFailure: failure }
    : { correctionFailure: failure };
}

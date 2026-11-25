/**
 * The one function that turns a failed request into a message for people (TS-26, UI-25, ERR-07).
 *
 * Messages say what happened and what to do next. They never contain a status code, a problem
 * type, or an internal name. A screen that has its own state for a category, such as "This order
 * was not found", uses the category and shows its own text.
 */
import type {
  ProblemType,
  RequestFailure,
} from "@/features/backend-requests/model/request-failure";

const messageByCategory: Readonly<Record<FailureCategory, string>> = {
  session_expired: "Your session has ended. Sign in again to continue.",
  permission_denied: "Your account is not allowed to do this.",
  not_found: "This was not found. Reload the page and try again.",
  invalid_request: "The request was not accepted. Check what you entered and try again.",
  conflict: "This request conflicts with an earlier one. Reload the page and try again.",
  authority_required:
    "Only a manager can send the reply of this ticket. Submit the reply for approval instead.",
  invalid_state: "This ticket changed, so this is no longer possible. Reload it to see its state.",
  suggestion_pending:
    "The AI is still working on this ticket. Wait until it is done, then try again.",
  suggestion_superseded:
    "The AI made a newer suggestion for this ticket. Reload it and check the new draft.",
  unavailable: "The service is not available right now. Try again in a moment.",
  too_large: "The request is too large. Shorten your text and try again.",
  rate_limited: "Too many requests were sent. Wait a moment, then try again.",
  network: "The server could not be reached. Check your connection and try again.",
  timeout: "The server took too long to answer. Try again in a moment.",
  unexpected: "Something went wrong. Try again in a moment.",
};

/** The category of each problem type. An unknown type is a technical failure (CON-22). */
const categoryByProblemType: Readonly<Record<ProblemType, FailureCategory>> = {
  unauthenticated: "session_expired",
  forbidden: "permission_denied",
  not_found: "not_found",
  invalid_request: "invalid_request",
  idempotency_key_reused: "conflict",
  login_name_taken: "conflict",
  not_ready: "unavailable",
  internal_error: "unexpected",
  authority_required: "authority_required",
  invalid_ticket_state: "invalid_state",
  suggestion_pending: "suggestion_pending",
  suggestion_superseded: "suggestion_superseded",
  unknown: "unexpected",
};

/** The category of each failure that has no response to read. */
const categoryByKindWithoutResponse: Readonly<
  Record<Exclude<RequestFailure["kind"], "problem" | "ingress">, FailureCategory>
> = {
  network: "network",
  timeout: "timeout",
  invalid_response: "unexpected",
};

const ingressCategoryByStatus: ReadonlyMap<number, FailureCategory> = new Map([
  [413, "too_large"],
  [429, "rate_limited"],
  [502, "unavailable"],
  [503, "unavailable"],
  [504, "unavailable"],
]);

/** What kind of failure happened, as the UI needs to know it. */
export type FailureCategory =
  | "session_expired"
  | "permission_denied"
  | "not_found"
  | "invalid_request"
  | "conflict"
  | "authority_required"
  | "invalid_state"
  | "suggestion_pending"
  | "suggestion_superseded"
  | "unavailable"
  | "too_large"
  | "rate_limited"
  | "network"
  | "timeout"
  | "unexpected";

/** A failure as the UI shows it. */
export type FailureDescription = {
  readonly category: FailureCategory;
  /** A plain-language sentence: what happened and what to do next. */
  readonly message: string;
  /** The copyable trace ID, when `backend` sent one (UI-25). */
  readonly traceId?: string;
};

/**
 * Choose the category of any failure.
 *
 * @param failure - The parsed failure.
 * @returns Its category.
 */
export function categorizeFailure(failure: RequestFailure): FailureCategory {
  if (failure.kind === "problem") {
    return categoryByProblemType[failure.problemType];
  }
  if (failure.kind === "ingress") {
    return ingressCategoryByStatus.get(failure.status) ?? "unexpected";
  }
  return categoryByKindWithoutResponse[failure.kind];
}

/**
 * Describe a failure for people.
 *
 * @param failure - The parsed failure.
 * @returns Its category, its plain-language message, and its trace ID when there is one.
 */
export function describeFailure(failure: RequestFailure): FailureDescription {
  const category = categorizeFailure(failure);
  const message = messageByCategory[category];
  if (failure.kind === "problem" && failure.traceId !== undefined) {
    return { category, message, traceId: failure.traceId };
  }
  return { category, message };
}

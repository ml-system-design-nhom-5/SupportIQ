/**
 * A failed console action as the workspace says it (UI-25; console UI design, Errors and
 * guardrails), whatever the action: plain language and the copyable trace ID, never a status code,
 * a problem type, or an internal name (ERR-07).
 */

/** A failed action in plain language (UI-25). */
export type FailureView = {
  /** The bold first sentence: what happened to the action. */
  readonly lead: string;
  /** Why, and what to do next, in plain language. */
  readonly message: string;
  /** The copyable trace ID, when `backend` sent one. */
  readonly traceId?: string;
};

/**
 * What a failed account change means for the page (admin UI design, Flow and States). The list is
 * paginated, so frontend cannot know the last active manager; `backend` refuses that change and
 * names the reason in `violated_rule`.
 */
import {
  categorizeFailure,
  type FailureCategory,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";

/** The `violated_rule` that has its own banner. */
const LAST_ACTIVE_MANAGER = "last_active_manager";

const kindByCategory: Readonly<Record<FailureCategory, AccountChangeFailureKind>> = {
  invalid_request: "refused",
  not_found: "not_found",
  permission_denied: "permission_denied",
  session_expired: "technical",
  conflict: "technical",
  // The console refusals never answer an account change.
  authority_required: "technical",
  invalid_state: "technical",
  suggestion_pending: "technical",
  suggestion_superseded: "technical",
  unavailable: "technical",
  too_large: "technical",
  rate_limited: "technical",
  network: "technical",
  timeout: "technical",
  unexpected: "technical",
};

/**
 * How the page answers a failed change.
 * `last_active_manager`: the banner that says to make another account a manager first.
 * `refused`: any other `422`, an unknown or absent rule included (CON-22): a banner that asks the
 * admin to reload the list.
 * `not_found`: the account is gone; the list loads again.
 * `permission_denied`: the caller is no longer an admin; the permission-denied state.
 * `outcome_unknown`: the change may have happened; the list loads again.
 * `technical`: a plain-language error with the trace ID when there is one.
 */
export type AccountChangeFailureKind =
  | "last_active_manager"
  | "refused"
  | "not_found"
  | "permission_denied"
  | "outcome_unknown"
  | "technical";

/**
 * Classify a failed change.
 *
 * @param failure - The failure of `changeAccountRole` or `changeAccountStatus`.
 * @returns How the page answers it.
 */
export function classifyChangeFailure(failure: RequestFailure): AccountChangeFailureKind {
  if (failure.kind === "problem" && failure.violatedRule === LAST_ACTIVE_MANAGER) {
    return "last_active_manager";
  }
  const kind = kindByCategory[categorizeFailure(failure)];
  if (kind !== "permission_denied" && isWriteOutcomeUnknown(failure)) {
    return "outcome_unknown";
  }
  return kind;
}

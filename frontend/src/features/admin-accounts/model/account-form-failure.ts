/**
 * What a failed creation or reset means for the Accounts screen (account management design,
 * Create account dialog and Reset password dialog). `401` never stays on screen: it ends the
 * session, which opens sign-in.
 */
import {
  categorizeFailure,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";

/**
 * How the create dialog answers a failed creation.
 * `login_name_taken`: the message at the number field.
 * `refused`: any `422`: a banner in the dialog that asks to check the fields.
 * `permission_denied`: `403`: the permission-denied state of the admin area.
 * `outcome_unknown`: the account may have been created; the list loads again.
 * `technical`: the shared failure banner in the dialog, with the trace ID when there is one.
 */
export type AccountCreationFailureKind =
  "login_name_taken" | "refused" | "permission_denied" | "outcome_unknown" | "technical";

/**
 * How the Accounts screen answers a failed reset.
 * `not_found`: the dialog closes, a page banner says so, and the list loads again.
 * `refused`: any `422`, with any `violated_rule`, an unknown one, or none (CON-22): the dialog
 * closes and a page banner asks to load the list again, because only an outdated list offers it.
 * `permission_denied`: `403`: the permission-denied state of the admin area.
 * `outcome_unknown`: the password may have been reset; the list loads again.
 * `technical`: the shared failure banner in the dialog, with the trace ID when there is one.
 */
export type PasswordResetFailureKind =
  "not_found" | "refused" | "permission_denied" | "outcome_unknown" | "technical";

/**
 * Classify a failed creation.
 *
 * @param failure - The failure of `createAdminAccount`.
 * @returns How the create dialog answers it.
 */
export function classifyCreationFailure(failure: RequestFailure): AccountCreationFailureKind {
  if (failure.kind === "problem" && failure.problemType === "login_name_taken") {
    return "login_name_taken";
  }
  return classifyFormFailure(failure);
}

/**
 * Classify a failed reset.
 *
 * @param failure - The failure of `resetAccountPassword`.
 * @returns How the Accounts screen answers it.
 */
export function classifyResetFailure(failure: RequestFailure): PasswordResetFailureKind {
  return categorizeFailure(failure) === "not_found" ? "not_found" : classifyFormFailure(failure);
}

/**
 * Classify the failures that both dialogs answer the same way.
 *
 * @param failure - The failure of a creation or a reset.
 * @returns `refused`, `permission_denied`, `outcome_unknown`, or `technical`.
 */
function classifyFormFailure(
  failure: RequestFailure,
): "refused" | "permission_denied" | "outcome_unknown" | "technical" {
  const category = categorizeFailure(failure);
  if (category === "invalid_request") {
    return "refused";
  }
  if (category === "permission_denied") {
    return "permission_denied";
  }
  return isWriteOutcomeUnknown(failure) ? "outcome_unknown" : "technical";
}

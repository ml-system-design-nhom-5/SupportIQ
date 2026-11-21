/**
 * The own password change of `/change-password` (account management design, Change password page):
 * the checks that frontend makes before sending, what a failure means for the page, and its texts.
 * frontend alone checks that the two new entries match; `backend` checks the current password.
 */
import {
  categorizeFailure,
  isWriteOutcomeUnknown,
  type RequestFailure,
} from "@/features/backend-requests";
import { classifyPasswordLength, PASSWORD_TOO_LONG_TEXT } from "@/features/session/model/password";

/** The path of the page, shared by every role (console UI design, Screens). */
export const CHANGE_PASSWORD_PATH = "/change-password";

/** The `violated_rule` of a current password that `backend` did not accept. */
const CURRENT_PASSWORD_INCORRECT = "current_password_incorrect";

/** The texts of the page, from the account management design. */
export const passwordChangeText = {
  currentPasswordMissing: "Enter your current password.",
  newPasswordMissing: "Enter a new password.",
  confirmationMissing: "Enter the new password again.",
  confirmationDifferent: "The two new passwords are different.",
  currentPasswordIncorrect: "The current password is not correct.",
  notChanged: "The password was not changed.",
  checkFields: "Check the fields and try again.",
  mayHaveChanged: "The password may have been changed.",
  submitAgain: "Select Change password again without editing the fields to find out.",
  changed: "Your password was changed.",
  otherSessionsSignedOut: "Your other sessions were signed out.",
} as const;

/** The fields of the form. The passwords are Secret: they exist only in the open form. */
export type PasswordChangeFields = {
  readonly currentPassword: string;
  readonly newPassword: string;
  /** The new password, typed again. */
  readonly confirmation: string;
  readonly isSignedOutElsewhere: boolean;
};

/** A field of the form that can show an error. */
export type PasswordChangeField = "currentPassword" | "newPassword" | "confirmation";

/** The error of each field that has one. */
export type PasswordChangeFieldErrors = Readonly<Partial<Record<PasswordChangeField, string>>>;

/** A change that may be sent: what `changeOwnPassword` takes, without the key. */
export type PasswordChange = Omit<PasswordChangeFields, "confirmation">;

/** The fields as a change to send, or the error of each field that has one. */
export type PasswordChangeCheck =
  | { readonly kind: "valid"; readonly change: PasswordChange }
  | { readonly kind: "invalid"; readonly errors: PasswordChangeFieldErrors };

/**
 * How the page answers a failed change.
 * `current_password_incorrect`: the message at the first field, which is cleared and focused.
 * `refused`: any other `422`, an unknown or absent rule included (CON-22).
 * `outcome_unknown`: the password may have been changed; the same fields can be sent again.
 * `technical`: the shared failure banner, with the trace ID when there is one.
 */
export type PasswordChangeFailureKind =
  "current_password_incorrect" | "refused" | "outcome_unknown" | "technical";

/**
 * Check the fields before anything is sent: a field is empty, the new password is too long, or
 * the two new entries differ.
 *
 * @param fields - The fields of the form.
 * @returns The change to send, or the message of each field with an error.
 */
export function parsePasswordChange(fields: PasswordChangeFields): PasswordChangeCheck {
  const newPasswordLength = classifyPasswordLength(fields.newPassword);
  const errors: PasswordChangeFieldErrors = {
    ...(classifyPasswordLength(fields.currentPassword) === "empty"
      ? { currentPassword: passwordChangeText.currentPasswordMissing }
      : {}),
    ...(newPasswordLength === "empty"
      ? { newPassword: passwordChangeText.newPasswordMissing }
      : {}),
    ...(newPasswordLength === "too_long" ? { newPassword: PASSWORD_TOO_LONG_TEXT } : {}),
    ...findConfirmationError(fields),
  };
  if (Object.keys(errors).length > 0) {
    return { kind: "invalid", errors };
  }
  const { currentPassword, newPassword, isSignedOutElsewhere } = fields;
  return { kind: "valid", change: { currentPassword, newPassword, isSignedOutElsewhere } };
}

/**
 * Classify a failed change.
 *
 * @param failure - The failure of `changeOwnPassword`.
 * @returns How the page answers it.
 */
export function classifyPasswordChangeFailure(failure: RequestFailure): PasswordChangeFailureKind {
  if (failure.kind === "problem" && failure.violatedRule === CURRENT_PASSWORD_INCORRECT) {
    return "current_password_incorrect";
  }
  if (categorizeFailure(failure) === "invalid_request") {
    return "refused";
  }
  return isWriteOutcomeUnknown(failure) ? "outcome_unknown" : "technical";
}

/**
 * Find the error of the confirmation.
 *
 * @param fields - The fields of the form.
 * @returns The message when the confirmation is empty or differs from the new password.
 */
function findConfirmationError(fields: PasswordChangeFields): PasswordChangeFieldErrors {
  if (fields.confirmation === "") {
    return { confirmation: passwordChangeText.confirmationMissing };
  }
  return fields.confirmation === fields.newPassword
    ? {}
    : { confirmation: passwordChangeText.confirmationDifferent };
}

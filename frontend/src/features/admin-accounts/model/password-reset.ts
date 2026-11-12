/**
 * The reset dialog (account management design, Reset password dialog): the fields and the check
 * that frontend makes before sending. The create dialog checks its password the same way.
 */
import { accountFormText } from "@/features/admin-accounts/model/account-form-text";
import { assertNever } from "@/features/backend-requests";
import { classifyPasswordLength, PASSWORD_TOO_LONG_TEXT } from "@/features/session";

/** The fields of the reset dialog. The password is Secret: it exists only in the open dialog. */
export type PasswordResetFields = {
  readonly password: string;
  /** True ends every session of the account; false keeps them. */
  readonly isSignedOutEverywhere: boolean;
};

/** The fields as a reset to send, or the error of the password. */
export type PasswordResetCheck =
  | { readonly kind: "valid"; readonly reset: PasswordResetFields }
  | { readonly kind: "invalid"; readonly passwordError: string };

/**
 * Check the fields before anything is sent.
 *
 * @param fields - The fields of the reset dialog.
 * @returns The reset to send, or the message of the password field.
 */
export function parsePasswordReset(fields: PasswordResetFields): PasswordResetCheck {
  const passwordError = findNewPasswordError(fields.password);
  return passwordError === undefined
    ? { kind: "valid", reset: fields }
    : { kind: "invalid", passwordError };
}

/**
 * Find the error of a password that an admin sets.
 *
 * @param password - The password, exactly as typed.
 * @returns "Enter a password." when it is empty, the length message when it is too long, or
 *   undefined.
 */
export function findNewPasswordError(password: string): string | undefined {
  const length = classifyPasswordLength(password);
  switch (length) {
    case "valid":
      return undefined;
    case "empty":
      return accountFormText.passwordMissing;
    case "too_long":
      return PASSWORD_TOO_LONG_TEXT;
    default:
      assertNever(length);
  }
}

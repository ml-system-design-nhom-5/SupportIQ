/**
 * The texts of the create and reset dialogs and of their banners (account management design,
 * Create account dialog and Reset password dialog). The limits in the texts come from the
 * constants that the checks use, so they cannot disagree.
 */
import type { Account } from "@/features/admin-accounts/model/account";
import {
  DISPLAY_NAME_MAX_LENGTH,
  DISPLAY_NAME_MIN_LENGTH,
  LOGIN_NUMBER_MAX,
  LOGIN_NUMBER_MIN,
} from "@/features/admin-accounts/model/account-limits";

/** The texts that do not name an account. */
export const accountFormText = {
  createTitle: "Create an account",
  createLabel: "Create account",
  roleLegend: "Role",
  loginNameLabel: "Login name",
  loginNumberPlaceholder: "next free number",
  loginNumberHint: `Leave empty for the next free number, or enter ${String(LOGIN_NUMBER_MIN)} to ${String(LOGIN_NUMBER_MAX)}.`,
  loginNumberInvalid: `Enter a whole number from ${String(LOGIN_NUMBER_MIN)} to ${String(LOGIN_NUMBER_MAX)}, or leave it empty.`,
  displayNameLabel: "Display name",
  displayNameHint: `The name that appears in SupportIQ, ${String(DISPLAY_NAME_MIN_LENGTH)} to ${String(DISPLAY_NAME_MAX_LENGTH)} characters.`,
  displayNameMissing: "Enter a display name.",
  displayNameTooLong: `Use at most ${String(DISPLAY_NAME_MAX_LENGTH)} characters.`,
  displayNameEdgeSpaces: "Remove the spaces at the start and the end.",
  displayNameControlCharacters: "Remove line breaks and tabs.",
  passwordLabel: "Password",
  passwordMissing: "Enter a password.",
  createPasswordHint:
    "A suggested password. You can type another. Give it to the account's owner and ask them to change it.",
  copyPassword: "Copy password",
  passwordCopied: "Password copied.",
  passwordNotCopied: "The password could not be copied. Select it to copy it.",
  checkFields: "Check the fields and try again.",
  accountNotCreated: "The account was not created.",
  accountMayHaveBeenCreated: "The account may have been created.",
  createAgain: "Select Create account again without editing the fields to find out.",
  resetLabel: "Reset password",
  resetSessionsHint: "Sessions that you keep stay signed in.",
  stillDeactivated: "The account stays deactivated until an admin reactivates it.",
  passwordMayHaveBeenReset: "The password may have been reset.",
  resetAgain: "Select Reset password again without editing the fields to find out.",
  listLoadedAgain: "The list was loaded again.",
  loadListAgain: "Load the list again.",
} as const;

/** The texts of the reset dialog that name the account. */
export type ResetDialogText = {
  readonly title: string;
  readonly description: string;
  readonly passwordHint: string;
  readonly signOutEverywhere: string;
};

/** The texts of the banners of a reset that name the account. */
export type ResetOutcomeText = {
  readonly reset: string;
  readonly signedOutEverywhere: string;
  readonly notReset: string;
  readonly notFound: string;
};

/**
 * Write the message of a login name that is already in use.
 *
 * @param loginName - The login name that the request composed, such as `staff-4`.
 * @returns The message at the number field.
 */
export function buildLoginNameTakenText(loginName: string): string {
  return `${loginName} is already in use. Enter another number, or leave the field empty.`;
}

/**
 * Write the banner of a created account, with the login name of the response.
 *
 * @param displayName - The display name of the new account.
 * @param loginName - Its login name, as `backend` composed it.
 * @returns For example "Account created: Lan Do, login name staff-5."
 */
export function buildAccountCreatedText(displayName: string, loginName: string): string {
  return `Account created: ${displayName}, login name ${loginName}.`;
}

/**
 * Write the texts of the reset dialog that name the account.
 *
 * @param account - The account whose password is reset.
 * @returns The title, the text, which also says that a deactivated account stays deactivated, the
 *   password hint, and the sessions checkbox.
 */
export function buildResetDialogText(account: Account): ResetDialogText {
  const { displayName, loginName } = account;
  const description = `${displayName} (${loginName}) will sign in with the new password. The current password stops working at once.`;
  return {
    title: `Reset the password of ${displayName}?`,
    description: account.isActive
      ? description
      : `${description} ${accountFormText.stillDeactivated}`,
    passwordHint: `A suggested password. You can type another. Give it to ${displayName} and ask them to change it.`,
    signOutEverywhere: `Sign ${displayName} out of every session`,
  };
}

/**
 * Write the texts of the banners of a reset that name the account.
 *
 * @param displayName - The display name of the account.
 * @returns The lead of a reset, a refused reset, and a missing account, and the sessions sentence.
 */
export function buildResetOutcomeText(displayName: string): ResetOutcomeText {
  return {
    reset: `The password of ${displayName} was reset.`,
    signedOutEverywhere: `${displayName} was signed out of every session.`,
    notReset: `The password of ${displayName} was not reset.`,
    notFound: `${displayName} was not found.`,
  };
}

/**
 * The create dialog (account management design, Create account dialog): the fields, the checks
 * that frontend makes before sending, and the login name that `backend` composes. The request
 * carries the role and an optional number, never a login name (account management design, Login
 * names). Values are checked exactly as typed and never trimmed or repaired (SEC-21).
 */
import { classifyCreationFailure } from "@/features/admin-accounts/model/account-form-failure";
import { accountFormText } from "@/features/admin-accounts/model/account-form-text";
import {
  DISPLAY_NAME_MAX_LENGTH,
  DISPLAY_NAME_MIN_LENGTH,
  LOGIN_NUMBER_MAX,
  LOGIN_NUMBER_MIN,
} from "@/features/admin-accounts/model/account-limits";
import { findNewPasswordError } from "@/features/admin-accounts/model/password-reset";
import { countContractCharacters, type RequestFailure } from "@/features/backend-requests";

/** Digits only: a whole number without a sign, a decimal point, an exponent, or spaces. */
const wholeNumberPattern = /^\d+$/u;

/** A control character of Unicode category Cc, which the contract refuses. */
const controlCharacterPattern = /\p{Cc}/u;

/** Whitespace at the start or the end, which the contract refuses. */
const edgeWhitespacePattern = /^\s|\s$/u;

/** The checks of a display name, in the order in which their messages win. */
const displayNameChecks: readonly {
  readonly isBroken: (displayName: string) => boolean;
  readonly error: string;
}[] = [
  {
    isBroken: (displayName) => countContractCharacters(displayName) < DISPLAY_NAME_MIN_LENGTH,
    error: accountFormText.displayNameMissing,
  },
  {
    isBroken: (displayName) => countContractCharacters(displayName) > DISPLAY_NAME_MAX_LENGTH,
    error: accountFormText.displayNameTooLong,
  },
  {
    isBroken: (displayName) => controlCharacterPattern.test(displayName),
    error: accountFormText.displayNameControlCharacters,
  },
  {
    isBroken: (displayName) => edgeWhitespacePattern.test(displayName),
    error: accountFormText.displayNameEdgeSpaces,
  },
];

/** A role that an admin can give a new account (`AssignableAccountRole`). */
export type AssignableRole = "staff" | "manager";

/** The fields of the create dialog. The password is Secret: it exists only in the open dialog. */
export type AccountCreationFields = {
  readonly role: AssignableRole;
  /** The number as typed; empty means the next free number. */
  readonly loginNumber: string;
  readonly displayName: string;
  readonly password: string;
};

/** A field of the create dialog that can show an error. */
export type AccountCreationField = "loginNumber" | "displayName" | "password";

/** The error of each field that has one. */
export type AccountCreationFieldErrors = Readonly<Partial<Record<AccountCreationField, string>>>;

/** A creation that may be sent: what `createAdminAccount` takes, without the key. */
export type AccountCreation = {
  readonly role: AssignableRole;
  /** Absent for the next free number. */
  readonly loginNumber?: number;
  readonly displayName: string;
  readonly password: string;
};

/** The fields as a creation to send, or the error of each field that has one. */
export type AccountCreationCheck =
  | { readonly kind: "valid"; readonly creation: AccountCreation }
  | { readonly kind: "invalid"; readonly errors: AccountCreationFieldErrors };

/** The number field: empty, a whole number in the range, or anything else. */
type LoginNumberChoice =
  | { readonly kind: "next_free" }
  | { readonly kind: "chosen"; readonly number: number }
  | { readonly kind: "invalid" };

/**
 * Check the fields before anything is sent.
 *
 * @param fields - The fields of the create dialog.
 * @returns The creation to send, or the message of each field with an error.
 */
export function parseAccountCreation(fields: AccountCreationFields): AccountCreationCheck {
  const loginNumber = parseLoginNumber(fields.loginNumber);
  const displayNameError = displayNameChecks.find((check) => check.isBroken(fields.displayName));
  const passwordError = findNewPasswordError(fields.password);
  const errors: AccountCreationFieldErrors = {
    ...(loginNumber.kind === "invalid" ? { loginNumber: accountFormText.loginNumberInvalid } : {}),
    ...(displayNameError === undefined ? {} : { displayName: displayNameError.error }),
    ...(passwordError === undefined ? {} : { password: passwordError }),
  };
  if (Object.keys(errors).length > 0) {
    return { kind: "invalid", errors };
  }
  const { role, displayName, password } = fields;
  return {
    kind: "valid",
    creation: {
      role,
      displayName,
      password,
      ...(loginNumber.kind === "chosen" ? { loginNumber: loginNumber.number } : {}),
    },
  };
}

/**
 * Write the fixed prefix of the login names of a role.
 *
 * @param role - The role of the new account.
 * @returns For example `staff-`.
 */
export function buildLoginNamePrefix(role: AssignableRole): string {
  return `${role}-`;
}

/**
 * Find the login name that `backend` said is taken, for the message at the number field.
 *
 * @param failure - The failure of the last creation, if any.
 * @param creation - The last creation that was sent, if any.
 * @returns The login name for `409 login-name-taken` of a creation with a number. Otherwise
 *   undefined: without a number, the dialog shows the shared failure banner instead.
 */
export function findTakenLoginName(
  failure: RequestFailure | undefined,
  creation: AccountCreation | undefined,
): string | undefined {
  const isTaken = failure !== undefined && classifyCreationFailure(failure) === "login_name_taken";
  if (!isTaken || creation?.loginNumber === undefined) {
    return undefined;
  }
  return `${buildLoginNamePrefix(creation.role)}${String(creation.loginNumber)}`;
}

/**
 * Parse the number field.
 *
 * @param text - The number as typed.
 * @returns The next free number for an empty field, the number for a whole number in the range,
 *   or `invalid`.
 */
function parseLoginNumber(text: string): LoginNumberChoice {
  if (text === "") {
    return { kind: "next_free" };
  }
  const number = Number(text);
  const isInRange = number >= LOGIN_NUMBER_MIN && number <= LOGIN_NUMBER_MAX;
  return wholeNumberPattern.test(text) && isInRange
    ? { kind: "chosen", number }
    : { kind: "invalid" };
}

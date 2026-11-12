/**
 * The rule of every password that an account owner or an admin sets: the `Password` schema of the
 * backend contract, from 1 to 128 characters counted in Unicode code points, the limits of sign-in
 * (account management design, Passwords). No other rule applies. frontend checks the length before
 * sending as a convenience; `backend` enforces it with `422`.
 */
import { countContractCharacters } from "@/features/backend-requests";

/** The `minLength` of `Password` (contracts/backend.openapi.yaml). */
export const PASSWORD_MIN_LENGTH = 1;

/** The `maxLength` of `Password` (contracts/backend.openapi.yaml). */
export const PASSWORD_MAX_LENGTH = 128;

/** The message at a password field whose password is too long. */
export const PASSWORD_TOO_LONG_TEXT = `Use at most ${String(PASSWORD_MAX_LENGTH)} characters.`;

/** How a password meets the limits: `empty` below the minimum, `too_long` above the maximum. */
export type PasswordLength = "valid" | "empty" | "too_long";

/**
 * Classify the length of a password as the contract counts it.
 *
 * @param password - The password, exactly as typed: it is never trimmed (SEC-21).
 * @returns `valid`, `empty`, or `too_long`.
 */
export function classifyPasswordLength(password: string): PasswordLength {
  const length = countContractCharacters(password);
  if (length < PASSWORD_MIN_LENGTH) {
    return "empty";
  }
  return length > PASSWORD_MAX_LENGTH ? "too_long" : "valid";
}

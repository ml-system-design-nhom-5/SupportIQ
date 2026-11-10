/**
 * The refusal of a sign-in: an unknown login name, a wrong password, a deactivated account, or a
 * throttled attempt all get the same answer (ADR-0009, statement 8).
 */

/** Thrown by sign-in for its `401`, so it is never mistaken for an expired session. */
export class InvalidCredentialsError extends Error {
  override readonly name = "InvalidCredentialsError";

  constructor() {
    super("The login name or the password is not correct.");
  }
}

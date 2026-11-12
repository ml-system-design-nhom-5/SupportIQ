/**
 * What the Accounts screen says after a create or reset dialog closed with an outcome (account
 * management design, Create account dialog and Reset password dialog). Cancel closes a dialog
 * without one.
 */
import type { Account } from "@/features/admin-accounts/model/account";
import { classifyResetFailure } from "@/features/admin-accounts/model/account-form-failure";
import { assertNever, type RequestFailure } from "@/features/backend-requests";

/**
 * The outcome of a dialog, shown on the page.
 * `created` and `password_reset`: the success banners.
 * `reset_not_found` and `reset_refused`: the page banners of a reset that did not happen.
 * `permission_denied`: the caller is no longer an admin; the permission-denied state.
 */
export type AccountNotice =
  | { readonly kind: "created"; readonly account: Account }
  | {
      readonly kind: "password_reset";
      readonly account: Account;
      readonly isSignedOutEverywhere: boolean;
    }
  | {
      readonly kind: "reset_not_found" | "reset_refused";
      readonly account: Account;
      readonly failure: RequestFailure;
    }
  | { readonly kind: "permission_denied"; readonly failure: RequestFailure };

/**
 * Choose what the page says after a failed reset, when the dialog closes for it.
 *
 * @param account - The account whose password was not reset.
 * @param failure - The failure of `resetAccountPassword`.
 * @returns The notice for `404`, `422`, and `403`, or undefined when the dialog stays open with its
 *   own banner.
 */
export function toResetFailureNotice(
  account: Account,
  failure: RequestFailure,
): AccountNotice | undefined {
  const kind = classifyResetFailure(failure);
  switch (kind) {
    case "not_found":
      return { kind: "reset_not_found", account, failure };
    case "refused":
      return { kind: "reset_refused", account, failure };
    case "permission_denied":
      return { kind: "permission_denied", failure };
    case "outcome_unknown":
    case "technical":
      return undefined;
    default:
      assertNever(kind);
  }
}

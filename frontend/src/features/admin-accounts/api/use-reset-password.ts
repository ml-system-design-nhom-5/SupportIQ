/**
 * Reset the password of a `staff` or `manager` account (`resetAccountPassword`). Automatic retries
 * reuse the `Idempotency-Key`, and so does sending the same fields again after a failure (TS-29;
 * account management design, Idempotency). The password is Secret: the write leaves the mutation
 * cache when it settles, so it exists only in the open dialog and in the request. The list loads
 * again after a reset, when the account is gone, and when the outcome is unknown.
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { accountQueryKeys } from "@/features/admin-accounts/api/account-query-keys";
import { type Account, toAccount } from "@/features/admin-accounts/model/account";
import {
  classifyResetFailure,
  type PasswordResetFailureKind,
} from "@/features/admin-accounts/model/account-form-failure";
import type { PasswordResetFields } from "@/features/admin-accounts/model/password-reset";
import {
  buildIdempotentWriteKey,
  forgetWrites,
  getRequestFailure,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";

const resetPasswordKey = buildIdempotentWriteKey("resetAccountPassword");

/** The failures after which the rows on screen may be out of date. */
const failuresThatReload: ReadonlySet<PasswordResetFailureKind> = new Set([
  "not_found",
  "outcome_unknown",
]);

/** One submission of the reset dialog. */
export type PasswordReset = PasswordResetFields & {
  readonly accountId: string;
  /** Stays while the fields stay the same (account management design, Shared behavior). */
  readonly idempotencyKey: string;
};

/**
 * Reset a password.
 *
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
export function useResetPassword(): UseMutationResult<Account, Error, PasswordReset> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadAccounts = () =>
    queryClient.invalidateQueries({ queryKey: accountQueryKeys.accounts() });
  return useMutation({
    mutationKey: resetPasswordKey,
    mutationFn: (reset: PasswordReset) =>
      sendAttempt(reset.idempotencyKey, () => resetPassword(client, reset)),
    onSuccess: () => {
      void reloadAccounts();
    },
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && failuresThatReload.has(classifyResetFailure(failure))) {
        void reloadAccounts();
      }
    },
    onSettled: () => {
      forgetWrites(queryClient, resetPasswordKey);
    },
  });
}

/**
 * Send the reset.
 *
 * @param client - The backend client.
 * @param reset - The account, the password, the sessions choice, and the key.
 * @returns The account after the reset.
 */
function resetPassword(client: BackendClient, reset: PasswordReset): Promise<Account> {
  return requestData(
    () =>
      client.POST("/v1/admin/accounts/{account_id}/password-resets", {
        params: {
          path: { account_id: reset.accountId },
          header: { "Idempotency-Key": reset.idempotencyKey },
        },
        body: { password: reset.password, is_signed_out_everywhere: reset.isSignedOutEverywhere },
      }),
    toAccount,
  );
}

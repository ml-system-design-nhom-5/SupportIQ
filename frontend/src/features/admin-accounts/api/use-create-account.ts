/**
 * Create a `staff` or `manager` account (`createAdminAccount`). Automatic retries reuse the
 * `Idempotency-Key`, and so does sending the same fields again after a failure (TS-29; account
 * management design, Idempotency). The password is Secret: the write leaves the mutation cache
 * when it settles, so it exists only in the open dialog and in the request. The list loads again
 * after a creation, and after a failure whose outcome is unknown.
 */
import { useMutation, type UseMutationResult, useQueryClient } from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { accountQueryKeys } from "@/features/admin-accounts/api/account-query-keys";
import { type Account, toAccount } from "@/features/admin-accounts/model/account";
import type { AccountCreation } from "@/features/admin-accounts/model/account-creation";
import { classifyCreationFailure } from "@/features/admin-accounts/model/account-form-failure";
import {
  buildIdempotentWriteKey,
  forgetWrites,
  getRequestFailure,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";

const createAccountKey = buildIdempotentWriteKey("createAdminAccount");

/** One submission of the create dialog. */
export type NewAccount = AccountCreation & {
  /** Stays while the fields stay the same (account management design, Shared behavior). */
  readonly idempotencyKey: string;
};

/**
 * Create an account.
 *
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
export function useCreateAccount(): UseMutationResult<Account, Error, NewAccount> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadAccounts = () =>
    queryClient.invalidateQueries({ queryKey: accountQueryKeys.accounts() });
  return useMutation({
    mutationKey: createAccountKey,
    mutationFn: (newAccount: NewAccount) =>
      sendAttempt(newAccount.idempotencyKey, () => createAccount(client, newAccount)),
    onSuccess: () => {
      void reloadAccounts();
    },
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && classifyCreationFailure(failure) === "outcome_unknown") {
        void reloadAccounts();
      }
    },
    onSettled: () => {
      forgetWrites(queryClient, createAccountKey);
    },
  });
}

/**
 * Send the creation.
 *
 * @param client - The backend client.
 * @param newAccount - The fields and the key.
 * @returns The new account with the login name that `backend` composed.
 */
function createAccount(client: BackendClient, newAccount: NewAccount): Promise<Account> {
  return requestData(
    () =>
      client.POST("/v1/admin/accounts", {
        params: { header: { "Idempotency-Key": newAccount.idempotencyKey } },
        body: {
          role: newAccount.role,
          display_name: newAccount.displayName,
          password: newAccount.password,
          ...(newAccount.loginNumber === undefined ? {} : { login_number: newAccount.loginNumber }),
        },
      }),
    toAccount,
  );
}

/**
 * Change an account (`changeAccountRole`, `changeAccountStatus`). Automatic retries reuse the
 * `Idempotency-Key`, and so does confirming the same change again after a failure (TS-29, ERR-15).
 * After a success the row shows the answer of `backend` at once, and the list loads again. It also
 * loads again when the account is gone, or when the change may have happened.
 */
import {
  type QueryClient,
  useMutation,
  type UseMutationResult,
  useQueryClient,
} from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { accountQueryKeys } from "@/features/admin-accounts/api/account-query-keys";
import type { AccountListData } from "@/features/admin-accounts/api/use-accounts";
import {
  type Account,
  type AccountChange,
  replaceAccount,
  toAccount,
} from "@/features/admin-accounts/model/account";
import {
  type AccountChangeFailureKind,
  classifyChangeFailure,
} from "@/features/admin-accounts/model/account-change-failure";
import {
  assertNever,
  buildIdempotentWriteKey,
  getRequestFailure,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";

/** The failures after which the rows on screen may be out of date. */
const failuresThatReload: ReadonlySet<AccountChangeFailureKind> = new Set([
  "not_found",
  "outcome_unknown",
]);

/** One confirmation of a change. */
export type AccountChangeRequest = {
  readonly change: AccountChange;
  /** Stays when the admin confirms the same change again after a failure (admin UI design). */
  readonly idempotencyKey: string;
};

/**
 * Change an account.
 *
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
export function useChangeAccount(): UseMutationResult<Account, Error, AccountChangeRequest> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  const reloadAccounts = () =>
    queryClient.invalidateQueries({ queryKey: accountQueryKeys.accounts() });
  return useMutation({
    mutationKey: buildIdempotentWriteKey("changeAccount"),
    mutationFn: (request: AccountChangeRequest) =>
      sendAttempt(request.idempotencyKey, () => sendAccountChange(client, request)),
    onSuccess: (changed) => {
      updateCachedAccount(queryClient, changed);
      void reloadAccounts();
    },
    onError: (error) => {
      const failure = getRequestFailure(error);
      if (failure !== undefined && failuresThatReload.has(classifyChangeFailure(failure))) {
        // TODO(#7): after `not_found` or an unknown outcome, the reload can remove or replace the
        // button that holds the focus, and the focus falls to the page (UI-30).
        void reloadAccounts();
      }
    },
  });
}

/**
 * Send a role change.
 *
 * @param client - The backend client.
 * @param request - The change and its key.
 * @param role - The new role.
 * @returns The account after the change.
 */
function sendRoleChange(
  client: BackendClient,
  request: AccountChangeRequest,
  role: "staff" | "manager",
): Promise<Account> {
  return requestData(
    () =>
      client.POST("/v1/admin/accounts/{account_id}/role-changes", {
        params: {
          path: { account_id: request.change.account.accountId },
          header: { "Idempotency-Key": request.idempotencyKey },
        },
        body: { role },
      }),
    toAccount,
  );
}

/**
 * Send a status change.
 *
 * @param client - The backend client.
 * @param request - The change and its key.
 * @param isActive - The new status.
 * @returns The account after the change.
 */
function sendStatusChange(
  client: BackendClient,
  request: AccountChangeRequest,
  isActive: boolean,
): Promise<Account> {
  return requestData(
    () =>
      client.POST("/v1/admin/accounts/{account_id}/status-changes", {
        params: {
          path: { account_id: request.change.account.accountId },
          header: { "Idempotency-Key": request.idempotencyKey },
        },
        body: { is_active: isActive },
      }),
    toAccount,
  );
}

/**
 * Send the operation of a change.
 *
 * @param client - The backend client.
 * @param request - The change and its key.
 * @returns The account after the change.
 */
function sendAccountChange(client: BackendClient, request: AccountChangeRequest): Promise<Account> {
  switch (request.change.kind) {
    case "make_manager":
      return sendRoleChange(client, request, "manager");
    case "make_staff":
      return sendRoleChange(client, request, "staff");
    case "deactivate":
      return sendStatusChange(client, request, false);
    case "reactivate":
      return sendStatusChange(client, request, true);
    default:
      assertNever(request.change.kind);
  }
}

/**
 * Show the changed account in the cached list.
 *
 * @param queryClient - The query client.
 * @param changed - The account after the change.
 */
function updateCachedAccount(queryClient: QueryClient, changed: Account): void {
  queryClient.setQueryData<AccountListData>(accountQueryKeys.accounts(), (cachedAccounts) =>
    cachedAccounts === undefined
      ? undefined
      : {
          ...cachedAccounts,
          pages: cachedAccounts.pages.map((page) => ({
            ...page,
            accounts: replaceAccount(page.accounts, changed),
          })),
        },
  );
}

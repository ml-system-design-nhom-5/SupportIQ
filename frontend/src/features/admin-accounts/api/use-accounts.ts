/**
 * Read the internal accounts page by page (`listAdminAccounts`, CON-14), ordered by display name.
 */
import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { accountQueryKeys } from "@/features/admin-accounts/api/account-query-keys";
import { type AccountPage, toAccountPage } from "@/features/admin-accounts/model/account";
import { requestData } from "@/features/backend-requests";

/** The data of the cached account list. */
export type AccountListData = InfiniteData<AccountPage, string | undefined>;

/** The infinite query of the account list. */
export type AccountListQuery = UseInfiniteQueryResult<AccountListData>;

/**
 * Read the pages of the account list.
 *
 * @returns The infinite query; `fetchNextPage` follows `next_cursor` while there is one.
 */
export function useAccounts(): AccountListQuery {
  const client = useBackendClient();
  return useInfiniteQuery({
    queryKey: accountQueryKeys.accounts(),
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      requestData(
        () =>
          client.GET("/v1/admin/accounts", {
            params: { query: pageParam === undefined ? {} : { cursor: pageParam } },
            signal,
          }),
        toAccountPage,
      ),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}

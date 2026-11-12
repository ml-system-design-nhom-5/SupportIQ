/**
 * The account list of the Accounts screen: the table, its loading state, and Show more accounts
 * while there is a next page (CON-14, admin UI design: 20 accounts per page).
 */

import { LoadMoreButton, Skeleton, Stack, VisuallyHidden } from "@/design-system";
import type { AccountListQuery } from "@/features/admin-accounts/api/use-accounts";
import {
  AccountsTable,
  type RowActionHandlers,
} from "@/features/admin-accounts/components/accounts-table";
import type { Account } from "@/features/admin-accounts/model/account";
import { collectPageItems, FailureBanner, getRequestFailure } from "@/features/backend-requests";
import { useSignedInAccountId } from "@/features/session";

/** Props of {@link AccountList}. */
export type AccountListProps = RowActionHandlers & {
  readonly query: AccountListQuery;
};

/**
 * Render the account list.
 *
 * @param props - The query of the list and the handlers of the row actions.
 * @returns Skeleton rows, or the table with Show more accounts.
 */
export function AccountList({ query, ...handlers }: AccountListProps) {
  const callerAccountId = useSignedInAccountId();

  if (query.data === undefined) {
    return (
      <Stack gap="3">
        <p role="status">
          <VisuallyHidden>Loading the accounts…</VisuallyHidden>
        </p>
        <Skeleton width="full" height="block" />
        <Skeleton width="full" height="block" />
      </Stack>
    );
  }
  const accounts = collectPageItems(
    query.data.pages.map((page) => page.accounts),
    (account: Account) => account.accountId,
  );
  const loadMoreFailure = query.isFetchNextPageError ? getRequestFailure(query.error) : undefined;

  return (
    <>
      <AccountsTable accounts={accounts} callerAccountId={callerAccountId} {...handlers} />
      {loadMoreFailure === undefined ? null : (
        <FailureBanner lead="More accounts could not be loaded." failure={loadMoreFailure} />
      )}
      {query.hasNextPage ? (
        <LoadMoreButton
          label="Show more accounts"
          size="md"
          isLoading={query.isFetchingNextPage}
          onLoadMore={() => {
            void query.fetchNextPage();
          }}
        />
      ) : null}
    </>
  );
}

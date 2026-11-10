/**
 * The Accounts screen (`/admin/accounts`, admin UI design): the internal accounts with their
 * actions. Every change opens a confirmation that names the account and the change (UI-45), and
 * sends an `Idempotency-Key`, which stays when the same change is confirmed again after a failure
 * (TS-29, admin UI design, Flow).
 */
import { useState } from "react";

import { buildRowHeaderId, ConfirmDialog, PageHeader, Stack, Text } from "@/design-system";
import { useAccounts } from "@/features/admin-accounts/api/use-accounts";
import { useChangeAccount } from "@/features/admin-accounts/api/use-change-account";
import { AccountChangeBanner } from "@/features/admin-accounts/components/account-change-banner";
import { AccountList } from "@/features/admin-accounts/components/account-list";
import type { ChosenAccountChange } from "@/features/admin-accounts/components/accounts-table";
import { type AccountChange, isSameChange } from "@/features/admin-accounts/model/account";
import { classifyChangeFailure } from "@/features/admin-accounts/model/account-change-failure";
import { buildChangeConfirmation } from "@/features/admin-accounts/model/account-change-text";
import {
  describeFailure,
  getRequestFailure,
  type RequestFailure,
  useCreateIdempotencyKey,
} from "@/features/backend-requests";
import { AreaLoadFailure, AreaPermissionDenied } from "@/features/session";

/** Props of {@link AccountChangeDialog}. */
type AccountChangeDialogProps = {
  readonly chosen: ChosenAccountChange;
  readonly isPending: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
};

/**
 * Render the Accounts screen.
 *
 * @returns The screen in the state of its data.
 */
export function AccountsPage() {
  const accountsQuery = useAccounts();
  const changeAccount = useChangeAccount();
  const createIdempotencyKey = useCreateIdempotencyKey();
  const [chosenChange, setChosenChange] = useState<ChosenAccountChange | null>(null);
  const loadFailure = getRequestFailure(accountsQuery.error);
  const changeFailure = getRequestFailure(changeAccount.error);

  if (accountsQuery.data === undefined && loadFailure !== undefined) {
    return (
      <AreaLoadFailure
        area="admin"
        title="The accounts could not be loaded"
        failure={loadFailure}
        headingLevel={1}
        isRetrying={accountsQuery.isFetching}
        onRetry={() => {
          void accountsQuery.refetch();
        }}
      />
    );
  }
  if (changeFailure !== undefined && classifyChangeFailure(changeFailure) === "permission_denied") {
    return <ChangePermissionDenied failure={changeFailure} />;
  }

  const handleConfirm = (change: AccountChange) => {
    const failedRequest = changeAccount.isError ? changeAccount.variables : undefined;
    changeAccount.mutate(
      {
        change,
        idempotencyKey:
          failedRequest !== undefined && isSameChange(failedRequest.change, change)
            ? failedRequest.idempotencyKey
            : createIdempotencyKey(),
      },
      {
        onSettled: () => {
          setChosenChange(null);
        },
      },
    );
  };

  return (
    <Stack gap="4">
      <title>Accounts · SupportIQ Admin</title>
      <PageHeader
        title="Accounts"
        density="compact"
        action={
          <Text tone="muted">Internal accounts only. Customer accounts are never listed.</Text>
        }
      />
      {changeFailure === undefined || changeAccount.variables === undefined ? null : (
        <AccountChangeBanner
          change={changeAccount.variables.change}
          failure={changeFailure}
          onReload={() => {
            // TODO(#7): this removes the banner with its focused Reload list button, and the
            // focus falls to the page (UI-30).
            changeAccount.reset();
            void accountsQuery.refetch();
          }}
        />
      )}
      <AccountList query={accountsQuery} onChooseChange={setChosenChange} />
      {chosenChange === null ? null : (
        <AccountChangeDialog
          chosen={chosenChange}
          isPending={changeAccount.isPending}
          onConfirm={() => {
            handleConfirm(chosenChange.change);
          }}
          onCancel={() => {
            setChosenChange(null);
          }}
        />
      )}
    </Stack>
  );
}

/**
 * Render the confirmation of a change. The focus returns to the button that opened it, or to the
 * row when the change replaced that button (UI-30).
 *
 * @param props - The chosen change, the pending state, and the handlers.
 * @returns The dialog.
 */
function AccountChangeDialog({ chosen, isPending, onConfirm, onCancel }: AccountChangeDialogProps) {
  const { change, opener } = chosen;
  const { tone, ...text } = buildChangeConfirmation(change);
  return (
    <ConfirmDialog
      isOpen
      text={text}
      returnFocus={{ opener, fallbackId: buildRowHeaderId(change.account.accountId) }}
      tone={tone}
      isPending={isPending}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

/**
 * Render the permission-denied state of a change that `backend` answered with `403`.
 *
 * @param props - The failure of the change.
 * @returns The state, with the trace ID when there is one.
 */
function ChangePermissionDenied({ failure }: { readonly failure: RequestFailure }) {
  const { traceId } = describeFailure(failure);
  return <AreaPermissionDenied area="admin" {...(traceId === undefined ? {} : { traceId })} />;
}

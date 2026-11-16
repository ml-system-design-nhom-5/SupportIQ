/**
 * The Accounts screen (`/admin/accounts`, admin UI design): the internal accounts with their
 * actions, and Create account. Every change opens a confirmation that names the account and the
 * change (UI-45), and sends an `Idempotency-Key`, which stays when the same change is confirmed
 * again after a failure (TS-29, admin UI design, Flow). Create account and Reset password open
 * form dialogs (account management design, Create account dialog and Reset password dialog), whose
 * outcome the page shows in a banner.
 */
import { UserPlus } from "lucide-react";
import { useState } from "react";

import { buildRowHeaderId, Button, ConfirmDialog, PageHeader, Stack, Text } from "@/design-system";
import { useAccounts } from "@/features/admin-accounts/api/use-accounts";
import { useChangeAccount } from "@/features/admin-accounts/api/use-change-account";
import { AccountChangeBanner } from "@/features/admin-accounts/components/account-change-banner";
import { AccountList } from "@/features/admin-accounts/components/account-list";
import { AccountNoticeBanner } from "@/features/admin-accounts/components/account-notice-banner";
import type {
  ChosenAccountChange,
  ChosenPasswordReset,
} from "@/features/admin-accounts/components/accounts-table";
import { CreateAccountDialog } from "@/features/admin-accounts/components/create-account-dialog";
import { ResetPasswordDialog } from "@/features/admin-accounts/components/reset-password-dialog";
import { type AccountChange, isSameChange } from "@/features/admin-accounts/model/account";
import { classifyChangeFailure } from "@/features/admin-accounts/model/account-change-failure";
import { buildChangeConfirmation } from "@/features/admin-accounts/model/account-change-text";
import { accountFormText } from "@/features/admin-accounts/model/account-form-text";
import type { AccountNotice } from "@/features/admin-accounts/model/account-notice";
import {
  describeFailure,
  getRequestFailure,
  type RequestFailure,
  useCreateIdempotencyKey,
} from "@/features/backend-requests";
import { AreaLoadFailure, AreaPermissionDenied, DevModeDetailsPanel } from "@/features/session";

/** The stable ID of Create account, which gets the focus back when its dialog closes (UI-30). */
const CREATE_ACCOUNT_BUTTON_ID = "create-account";

/** The form dialog that is open, with the button that opened it. */
type OpenFormDialog =
  | { readonly kind: "create"; readonly opener: HTMLElement }
  | ({ readonly kind: "reset" } & ChosenPasswordReset);

/** Props of {@link AccountChangeDialog}. */
type AccountChangeDialogProps = {
  readonly chosen: ChosenAccountChange;
  readonly isPending: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
};

/** Props of {@link PageBanners}. */
type PageBannersProps = {
  /** What the last form dialog closed with. */
  readonly notice: AccountNotice | null;
  /** The last change, when it failed. */
  readonly failedChange:
    { readonly change: AccountChange; readonly failure: RequestFailure } | undefined;
  readonly onReloadAfterNotice: () => void;
  readonly onReloadAfterChange: () => void;
};

/** Props of {@link AccountFormDialog}. */
type AccountFormDialogProps = {
  readonly dialog: OpenFormDialog;
  readonly onNotice: (notice: AccountNotice) => void;
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
  const [formDialog, setFormDialog] = useState<OpenFormDialog | null>(null);
  const [notice, setNotice] = useState<AccountNotice | null>(null);
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
  const denial = findPermissionDenial(changeFailure, notice);
  if (denial !== undefined) {
    return <ChangePermissionDenied failure={denial} />;
  }

  const handleConfirm = (change: AccountChange) => {
    setNotice(null);
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

  const openFormDialog = (dialog: OpenFormDialog) => {
    setNotice(null);
    setFormDialog(dialog);
  };

  return (
    <Stack gap="4">
      <title>Accounts · SupportIQ Admin</title>
      <PageHeader
        title="Accounts"
        density="compact"
        action={
          <Stack direction="row" gap="4" align="center">
            <Text tone="muted">Internal accounts only. Customer accounts are never listed.</Text>
            <Button
              id={CREATE_ACCOUNT_BUTTON_ID}
              variant="primary"
              leadingIcon={UserPlus}
              onClick={(event) => {
                openFormDialog({ kind: "create", opener: event.currentTarget });
              }}
            >
              {accountFormText.createLabel}
            </Button>
          </Stack>
        }
      />
      <PageBanners
        notice={notice}
        failedChange={
          changeFailure === undefined || changeAccount.variables === undefined
            ? undefined
            : { change: changeAccount.variables.change, failure: changeFailure }
        }
        onReloadAfterNotice={() => {
          setNotice(null);
          void accountsQuery.refetch();
        }}
        onReloadAfterChange={() => {
          // TODO(#7): this removes the banner with its focused Reload list button, and the
          // focus falls to the page (UI-30).
          changeAccount.reset();
          void accountsQuery.refetch();
        }}
      />
      <AccountList
        query={accountsQuery}
        onChooseChange={setChosenChange}
        onChooseReset={(chosen) => {
          openFormDialog({ kind: "reset", ...chosen });
        }}
      />
      <DevModeDetailsPanel />
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
      {formDialog === null ? null : (
        <AccountFormDialog
          dialog={formDialog}
          onNotice={(newNotice) => {
            setFormDialog(null);
            setNotice(newNotice);
          }}
          onCancel={() => {
            setFormDialog(null);
          }}
        />
      )}
    </Stack>
  );
}

/**
 * Find the `403` that replaces the screen with the permission-denied state: the caller is no
 * longer an admin.
 *
 * @param changeFailure - The failure of the last change, if any.
 * @param notice - What the last form dialog closed with, if anything.
 * @returns The failure of the `403`, or undefined.
 */
function findPermissionDenial(
  changeFailure: RequestFailure | undefined,
  notice: AccountNotice | null,
): RequestFailure | undefined {
  if (notice?.kind === "permission_denied") {
    return notice.failure;
  }
  const isChangeDenied =
    changeFailure !== undefined && classifyChangeFailure(changeFailure) === "permission_denied";
  return isChangeDenied ? changeFailure : undefined;
}

/**
 * Render the banners of the page: the outcome of the last form dialog, and the last change that
 * failed.
 *
 * @param props - The notice, the failed change, and the reload handlers.
 * @returns The banners that apply.
 */
function PageBanners({
  notice,
  failedChange,
  onReloadAfterNotice,
  onReloadAfterChange,
}: PageBannersProps) {
  return (
    <>
      {notice === null ? null : (
        <AccountNoticeBanner notice={notice} onReload={onReloadAfterNotice} />
      )}
      {failedChange === undefined ? null : (
        <AccountChangeBanner
          change={failedChange.change}
          failure={failedChange.failure}
          onReload={onReloadAfterChange}
        />
      )}
    </>
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
 * Render the open form dialog. The focus returns to the button that opened it, or to the row
 * header when that button was replaced (UI-30).
 *
 * @param props - The open dialog and the handlers of an outcome and of Cancel.
 * @returns The create dialog or the reset dialog.
 */
function AccountFormDialog({ dialog, onNotice, onCancel }: AccountFormDialogProps) {
  if (dialog.kind === "create") {
    return (
      <CreateAccountDialog
        returnFocus={{ opener: dialog.opener, fallbackId: CREATE_ACCOUNT_BUTTON_ID }}
        onNotice={onNotice}
        onCancel={onCancel}
      />
    );
  }
  return (
    <ResetPasswordDialog
      account={dialog.account}
      returnFocus={{
        opener: dialog.opener,
        fallbackId: buildRowHeaderId(dialog.account.accountId),
      }}
      onNotice={onNotice}
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

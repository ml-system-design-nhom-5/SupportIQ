/**
 * The accounts table (admin UI design, Accounts): the display name, the login name in the
 * monospace font, the role, the status, and the actions of each row. In dev mode, a column shows
 * the raw `role` and `is_active` as `backend` sent them (admin UI design, Developer details in the
 * admin area). The table shows no email, password, password hash, session data, or `account_id`
 * (SEC-41).
 */
import {
  Button,
  DataTable,
  type DataTableColumn,
  type DataTableRow,
  Identifier,
  presentationByAccountStatus,
  presentationByInternalRole,
  Stack,
  StatusBadge,
  Text,
  VisuallyHidden,
} from "@/design-system";
import {
  type Account,
  type AccountAction,
  type AccountChange,
  getAvailableActions,
} from "@/features/admin-accounts/model/account";
import { getChangeLabel } from "@/features/admin-accounts/model/account-change-text";
import { accountFormText } from "@/features/admin-accounts/model/account-form-text";
import { useDevMode } from "@/features/session";

const accountColumns: readonly DataTableColumn<AccountColumn>[] = [
  { key: "account", label: "Account", isRowHeader: true },
  { key: "loginName", label: "Login name" },
  { key: "role", label: "Role" },
  { key: "status", label: "Status" },
  { key: "actions", label: "Actions", align: "end" },
];

/** The columns in dev mode: the raw values come before the actions. */
const devModeColumns: readonly DataTableColumn<AccountColumn>[] = [
  ...accountColumns.slice(0, -1),
  { key: "rawValues", label: "Raw values" },
  ...accountColumns.slice(-1),
];

/** The columns of the table. */
type AccountColumn = "account" | "loginName" | "role" | "status" | "rawValues" | "actions";

/** A change that the admin chose, with the button that asked for it. */
export type ChosenAccountChange = {
  readonly change: AccountChange;
  /** Gets the focus back when the confirmation closes (UI-30). */
  readonly opener: HTMLElement;
};

/** An account whose password the admin chose to reset, with the button that asked for it. */
export type ChosenPasswordReset = {
  readonly account: Account;
  /** Gets the focus back when the reset dialog closes (UI-30). */
  readonly opener: HTMLElement;
};

/** The handlers of the row actions. */
export type RowActionHandlers = {
  /** Opens the confirmation of a change. */
  readonly onChooseChange: (chosen: ChosenAccountChange) => void;
  /** Opens the reset dialog. */
  readonly onChooseReset: (chosen: ChosenPasswordReset) => void;
};

/** Props of {@link AccountsTable}. */
export type AccountsTableProps = RowActionHandlers & {
  readonly accounts: readonly Account[];
  /** The `account_id` of the signed-in admin, which marks the caller's own row. */
  readonly callerAccountId: string | undefined;
};

/** What renders the actions of a row. */
type RowActionsProps = RowActionHandlers & {
  readonly account: Account;
  readonly actions: readonly AccountAction[];
  readonly isOwnAccount: boolean;
};

/**
 * Render the accounts table.
 *
 * @param props - The accounts, the caller's ID, and the handler.
 * @returns The table.
 */
export function AccountsTable({ accounts, ...rowProps }: AccountsTableProps) {
  const devMode = useDevMode();
  return (
    <DataTable
      caption="Internal accounts"
      columns={devMode.isOn ? devModeColumns : accountColumns}
      rows={accounts.map((account) => buildRow(account, rowProps))}
    />
  );
}

/**
 * Render the actions of a row, with the note that explains a missing action.
 *
 * @param props - The account, its actions, whether it is the caller's, and the handlers.
 * @returns The note, the buttons, or both.
 */
function RowActions({
  account,
  actions,
  isOwnAccount,
  onChooseChange,
  onChooseReset,
}: RowActionsProps) {
  if (isOwnAccount) {
    return (
      <Text tone="muted" size="xs">
        You cannot change your own account
      </Text>
    );
  }
  return (
    <Stack direction="row" gap="2" align="center" justify="end">
      {account.role === "admin" ? (
        <Text tone="muted" size="xs">
          The admin role cannot be changed
        </Text>
      ) : null}
      {actions.map((action) => (
        <Button
          key={action}
          size="sm"
          onClick={(event) => {
            const opener = event.currentTarget;
            if (action === "reset_password") {
              onChooseReset({ account, opener });
              return;
            }
            onChooseChange({ change: { kind: action, account }, opener });
          }}
        >
          {action === "reset_password" ? accountFormText.resetLabel : getChangeLabel(action)}
          <VisuallyHidden>: {account.displayName}</VisuallyHidden>
        </Button>
      ))}
    </Stack>
  );
}

/**
 * Build the row of an account.
 *
 * @param account - The account.
 * @param props - The caller's ID and the handlers.
 * @returns The table row.
 */
function buildRow(
  account: Account,
  { callerAccountId, ...handlers }: Omit<AccountsTableProps, "accounts">,
): DataTableRow<AccountColumn> {
  const isOwnAccount = account.accountId === callerAccountId;
  return {
    id: account.accountId,
    cells: {
      account: (
        <>
          {account.displayName}
          {isOwnAccount ? <Text tone="muted"> (you)</Text> : null}
        </>
      ),
      loginName: <Identifier>{account.loginName}</Identifier>,
      role: <StatusBadge presentation={presentationByInternalRole[account.role]} />,
      status: (
        <StatusBadge
          presentation={presentationByAccountStatus[account.isActive ? "active" : "deactivated"]}
        />
      ),
      rawValues: (
        <Identifier>{`role: ${account.rawRole} · is_active: ${String(account.isActive)}`}</Identifier>
      ),
      actions: (
        <RowActions
          account={account}
          actions={getAvailableActions(account, callerAccountId)}
          isOwnAccount={isOwnAccount}
          {...handlers}
        />
      ),
    },
  };
}

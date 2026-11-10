/**
 * The accounts table (admin UI design, Accounts): the display name, the role, the status, and the
 * actions of each row. The table shows no email, password hash, or session data (SEC-41).
 */
import {
  Button,
  DataTable,
  type DataTableColumn,
  type DataTableRow,
  presentationByAccountStatus,
  presentationByInternalRole,
  Stack,
  StatusBadge,
  Text,
  VisuallyHidden,
} from "@/design-system";
import {
  type Account,
  type AccountChange,
  type AccountChangeKind,
  getAvailableChanges,
} from "@/features/admin-accounts/model/account";
import { getChangeLabel } from "@/features/admin-accounts/model/account-change-text";

const accountColumns: readonly DataTableColumn<AccountColumn>[] = [
  { key: "account", label: "Account", isRowHeader: true },
  { key: "role", label: "Role" },
  { key: "status", label: "Status" },
  { key: "actions", label: "Actions", align: "end" },
];

/** The columns of the table. */
type AccountColumn = "account" | "role" | "status" | "actions";

/** A change that the admin chose, with the button that asked for it. */
export type ChosenAccountChange = {
  readonly change: AccountChange;
  /** Gets the focus back when the confirmation closes (UI-30). */
  readonly opener: HTMLElement;
};

/** Props of {@link AccountsTable}. */
export type AccountsTableProps = {
  readonly accounts: readonly Account[];
  /** The `account_id` of the signed-in admin, which marks the caller's own row. */
  readonly callerAccountId: string | undefined;
  /** Opens the confirmation of a change. */
  readonly onChooseChange: (chosen: ChosenAccountChange) => void;
};

/** What renders the actions of a row. */
type RowActionsProps = {
  readonly account: Account;
  readonly changes: readonly AccountChangeKind[];
  readonly isOwnAccount: boolean;
  readonly onChooseChange: (chosen: ChosenAccountChange) => void;
};

/**
 * Render the accounts table.
 *
 * @param props - The accounts, the caller's ID, and the handler.
 * @returns The table.
 */
export function AccountsTable({ accounts, callerAccountId, onChooseChange }: AccountsTableProps) {
  return (
    <DataTable
      caption="Internal accounts"
      columns={accountColumns}
      rows={accounts.map((account) => buildRow(account, { callerAccountId, onChooseChange }))}
    />
  );
}

/**
 * Render the actions of a row, with the note that explains a missing action.
 *
 * @param props - The account, its changes, whether it is the caller's, and the handler.
 * @returns The note, the buttons, or both.
 */
function RowActions({ account, changes, isOwnAccount, onChooseChange }: RowActionsProps) {
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
      {changes.map((kind) => (
        <Button
          key={kind}
          size="sm"
          onClick={(event) => {
            onChooseChange({ change: { kind, account }, opener: event.currentTarget });
          }}
        >
          {getChangeLabel(kind)}
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
 * @param props - The caller's ID and the handler.
 * @returns The table row.
 */
function buildRow(
  account: Account,
  { callerAccountId, onChooseChange }: Omit<AccountsTableProps, "accounts">,
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
      role: <StatusBadge presentation={presentationByInternalRole[account.role]} />,
      status: (
        <StatusBadge
          presentation={presentationByAccountStatus[account.isActive ? "active" : "deactivated"]}
        />
      ),
      actions: (
        <RowActions
          account={account}
          changes={getAvailableChanges(account, callerAccountId)}
          isOwnAccount={isOwnAccount}
          onChooseChange={onChooseChange}
        />
      ),
    },
  };
}

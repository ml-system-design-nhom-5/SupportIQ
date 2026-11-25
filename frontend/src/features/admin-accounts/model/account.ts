/**
 * The view models of internal accounts and the changes an admin can ask for (admin UI design,
 * Accounts). `backend` enforces every rule; the UI hides an action only when the contract makes it
 * impossible for every caller or when it concerns the caller's own account (UI-40, SEC-20).
 */
import type { InternalRoleName } from "@/design-system";
import type {
  AdminAccountContract,
  AdminAccountPageContract,
} from "@/features/admin-accounts/api/contract-types";
import { assertNever, requireMembers } from "@/features/backend-requests";

const knownRoles: ReadonlySet<string> = new Set(["staff", "manager", "admin"]);

/** An internal account: display name, login name, role, and status only (SEC-41). */
export type Account = {
  /** Used for requests and to find the caller's row; never shown. */
  readonly accountId: string;
  /** Internal, such as `staff-4`: it names a role and a number, never a person (ADR-0015). */
  readonly loginName: string;
  /** Confidential: shown, never logged or stored (admin UI design, Security and privacy). */
  readonly displayName: string;
  readonly role: InternalRoleName;
  /** The `role` as `backend` sent it, also one that this version does not know (UI-35). */
  readonly rawRole: string;
  readonly isActive: boolean;
};

/** One page of internal accounts (CON-14). */
export type AccountPage = {
  readonly accounts: readonly Account[];
  readonly nextCursor?: string;
};

/** A change that an admin can ask for. */
export type AccountChangeKind = "make_manager" | "make_staff" | "deactivate" | "reactivate";

/** An action of a row: a change that a confirmation sends, or Reset password, which a form sends. */
export type AccountAction = AccountChangeKind | "reset_password";

/** A change of one account. */
export type AccountChange = {
  readonly kind: AccountChangeKind;
  readonly account: Account;
};

/**
 * Map a role from `backend`.
 *
 * @param value - The `role` of an `AdminAccountView`.
 * @returns The role, or `unknown`, which the contract treats as a role that cannot be changed.
 */
export function toInternalRole(value: string): InternalRoleName {
  return isKnownRole(value) ? value : "unknown";
}

/**
 * Map a contract account.
 *
 * @param account - An `AdminAccountView`.
 * @returns The view model.
 */
export function toAccount(account: AdminAccountContract): Account {
  requireMembers(account, ["account_id", "login_name", "display_name", "role", "is_active"]);
  return {
    accountId: account.account_id,
    loginName: account.login_name,
    displayName: account.display_name,
    role: toInternalRole(account.role),
    rawRole: account.role,
    isActive: account.is_active,
  };
}

/**
 * Map a page of `listAdminAccounts`.
 *
 * @param page - An `AdminAccountPage`.
 * @returns The accounts and the cursor of the next page.
 */
export function toAccountPage(page: AdminAccountPageContract): AccountPage {
  const accounts = page.items.map(toAccount);
  return page.next_cursor === undefined ? { accounts } : { accounts, nextCursor: page.next_cursor };
}

/**
 * List the actions that a row offers (admin UI design, Accounts).
 *
 * @param account - The account of the row.
 * @param callerAccountId - The `account_id` of the signed-in admin.
 * @returns Nothing for the caller's own account, otherwise the role change, Reset password, then
 *   the status change. Reset password is offered on `staff` and `manager` accounts, active or
 *   deactivated.
 */
export function getAvailableActions(
  account: Account,
  callerAccountId: string | undefined,
): readonly AccountAction[] {
  if (account.accountId === callerAccountId) {
    return [];
  }
  const statusChange: AccountChangeKind = account.isActive ? "deactivate" : "reactivate";
  return [...getRoleActions(account.role), statusChange];
}

/**
 * Tell whether two changes ask for the same thing.
 *
 * @param change - A change.
 * @param otherChange - Another change.
 * @returns True for the same kind of change of the same account.
 */
export function isSameChange(change: AccountChange, otherChange: AccountChange): boolean {
  return (
    change.kind === otherChange.kind && change.account.accountId === otherChange.account.accountId
  );
}

/**
 * Apply a successful change to the accounts of a cached page.
 *
 * @param accounts - The accounts of a page.
 * @param changed - The account after the change, as `backend` returned it.
 * @returns The accounts with the changed one replaced.
 */
export function replaceAccount(accounts: readonly Account[], changed: Account): readonly Account[] {
  return accounts.map((account) => (account.accountId === changed.accountId ? changed : account));
}

/**
 * Tell whether a contract value is a role that this version knows.
 *
 * @param value - The `role` of an `AdminAccountView`.
 * @returns True for `staff`, `manager`, and `admin`.
 */
function isKnownRole(value: string): value is Exclude<InternalRoleName, "unknown"> {
  return knownRoles.has(value);
}

/**
 * List the actions that depend on the role of an account: the change to the one other role, and
 * Reset password.
 *
 * @param role - The account's role.
 * @returns The actions, or nothing for `admin` and for a role that this version does not know.
 */
function getRoleActions(role: InternalRoleName): readonly AccountAction[] {
  switch (role) {
    case "staff":
      return ["make_manager", "reset_password"];
    case "manager":
      return ["make_staff", "reset_password"];
    case "admin":
    case "unknown":
      return [];
    default:
      assertNever(role);
  }
}

/**
 * The signed-in account and the area of the app that its role opens (ADR-0009, ADR-0012).
 *
 * The contract says which area each role uses (`getCurrentSession`). The UI only chooses where to
 * go; `backend` enforces every permission (UI-40, SEC-20).
 */
import { assertNever, requireMembers } from "@/features/backend-requests";
import type { SessionViewContract } from "@/features/session/api/contract-types";

/** The root path of each area. */
export const rootPathByArea: Readonly<Record<Exclude<AppArea, "none">, string>> = {
  shop: "/shop",
  console: "/console",
  admin: "/admin",
};

const knownRoles: ReadonlySet<string> = new Set(["customer", "staff", "manager", "admin"]);

const labelByRole: Readonly<Record<AccountRole, string>> = {
  customer: "Customer",
  staff: "Staff",
  manager: "Manager",
  admin: "Admin",
  unknown: "Unknown role",
};

/** A role of the contract, or `unknown` for a role added later (CON-22). */
export type AccountRole = "customer" | "staff" | "manager" | "admin" | "unknown";

/** The signed-in account. The display name is Confidential: it is shown, never logged. */
export type Session = {
  readonly accountId: string;
  readonly displayName: string;
  readonly role: AccountRole;
};

/** Why nobody is signed in: the person signed out, or there was no valid session. */
export type SignedOutReason = "signed_out_by_user" | "no_valid_session";

/** What the app knows about the session. */
export type SessionState =
  | { readonly kind: "signed_in"; readonly session: Session }
  | { readonly kind: "signed_out"; readonly reason: SignedOutReason };

/** An area of the app; `none` for a role that has no area in this version. */
export type AppArea = "shop" | "console" | "admin" | "none";

/**
 * Map a role from `backend`.
 *
 * @param value - The `role` of `SessionView`.
 * @returns The role, or `unknown`: "a role without any area" (contract, `AccountRole`).
 */
export function toAccountRole(value: string): AccountRole {
  return isKnownRole(value) ? value : "unknown";
}

/**
 * Map the contract's `SessionView` to the view model.
 *
 * @param view - The body of `createSession` or `getCurrentSession`.
 * @returns The session.
 */
export function toSession(view: SessionViewContract): Session {
  requireMembers(view, ["account_id", "display_name", "role"]);
  return {
    accountId: view.account_id,
    displayName: view.display_name,
    role: toAccountRole(view.role),
  };
}

/**
 * Choose the area of a role, as the description of `getCurrentSession` says.
 *
 * @param role - The role of the session.
 * @returns `shop` for customers, `console` for staff and managers, `admin` for admins.
 */
export function getRoleArea(role: AccountRole): AppArea {
  switch (role) {
    case "customer":
      return "shop";
    case "staff":
    case "manager":
      return "console";
    case "admin":
      return "admin";
    case "unknown":
      return "none";
    default:
      assertNever(role);
  }
}

/**
 * Name a role for the app bar.
 *
 * @param role - The role.
 * @returns The label, for example "Staff".
 */
export function getRoleLabel(role: AccountRole): string {
  return labelByRole[role];
}

/**
 * Tell whether a contract value is a role that this version knows.
 *
 * @param value - The `role` from `backend`.
 * @returns True for `customer`, `staff`, `manager`, and `admin`.
 */
function isKnownRole(value: string): value is Exclude<AccountRole, "unknown"> {
  return knownRoles.has(value);
}

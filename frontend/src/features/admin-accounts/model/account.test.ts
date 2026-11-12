import { describe, expect, it } from "vitest";

import {
  type Account,
  type AccountChange,
  getAvailableActions,
  isSameChange,
  replaceAccount,
  toAccount,
  toAccountPage,
  toInternalRole,
} from "@/features/admin-accounts/model/account";
import { readOperationExample } from "@/test/contract-examples";

const CALLER_ID = "caller";

/**
 * Build an account.
 *
 * @param overrides - The fields that a test changes.
 * @returns The account.
 */
function buildAccount(overrides: Partial<Account> = {}): Account {
  return {
    accountId: "other",
    loginName: "staff-1",
    displayName: "Mai Nguyen",
    role: "staff",
    isActive: true,
    ...overrides,
  };
}

describe("toAccount", () => {
  it("maps AdminAccountView to the view model, with no other field (SEC-41)", () => {
    const account = toAccount(readOperationExample("changeAccountRole", 201, "made-manager"));

    expect(account).toEqual({
      accountId: "9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12",
      loginName: "staff-1",
      displayName: "Mai Nguyen",
      role: "manager",
      isActive: true,
    });
  });
});

describe("toAccountPage", () => {
  it("keeps the cursor of the next page", () => {
    const page = toAccountPage(readOperationExample("listAdminAccounts", 200, "first-page"));

    expect(page.accounts.map((account) => account.displayName)).toEqual(["Hoa Pham", "Mai Nguyen"]);
    expect(page.nextCursor).toBe("eyJhIjoyfQ");
  });

  it("has no cursor on the last page", () => {
    expect(
      toAccountPage(readOperationExample("listAdminAccounts", 200, "last-page")),
    ).not.toHaveProperty("nextCursor");
  });
});

describe("toInternalRole", () => {
  it.each(["staff", "manager", "admin"])("keeps the role %s", (role) => {
    expect(toInternalRole(role)).toBe(role);
  });

  it.each(["customer", "auditor", ""])("maps %j to unknown (CON-22)", (role) => {
    expect(toInternalRole(role)).toBe("unknown");
  });
});

describe("getAvailableActions (admin UI design, Accounts)", () => {
  it.each([
    [
      "an active staff account",
      { role: "staff" },
      ["make_manager", "reset_password", "deactivate"],
    ],
    ["an active manager", { role: "manager" }, ["make_staff", "reset_password", "deactivate"]],
    [
      "a deactivated staff account",
      { role: "staff", isActive: false },
      ["make_manager", "reset_password", "reactivate"],
    ],
    ["an active admin", { role: "admin" }, ["deactivate"]],
    ["a deactivated admin", { role: "admin", isActive: false }, ["reactivate"]],
    ["a role this version does not know", { role: "unknown" }, ["deactivate"]],
  ] as const)("offers the actions of %s", (_case, overrides, actions) => {
    expect(getAvailableActions(buildAccount(overrides), CALLER_ID)).toEqual(actions);
  });

  it("offers nothing on the caller's own account", () => {
    expect(getAvailableActions(buildAccount({ accountId: CALLER_ID }), CALLER_ID)).toEqual([]);
  });

  it("still offers the actions while the caller is not known yet", () => {
    expect(getAvailableActions(buildAccount(), undefined)).toEqual([
      "make_manager",
      "reset_password",
      "deactivate",
    ]);
  });
});

describe("isSameChange", () => {
  const mai = buildAccount({ accountId: "1" });
  const hoa = buildAccount({ accountId: "2" });

  it.each<[string, AccountChange, boolean]>([
    ["the same kind on the same account", { kind: "make_manager", account: mai }, true],
    ["the same kind on another account", { kind: "make_manager", account: hoa }, false],
    ["another kind on the same account", { kind: "deactivate", account: mai }, false],
    ["another kind on another account", { kind: "deactivate", account: hoa }, false],
  ])("compares with %s", (_case, otherChange, isSame) => {
    expect(isSameChange({ kind: "make_manager", account: mai }, otherChange)).toBe(isSame);
  });
});

describe("replaceAccount", () => {
  it("replaces the changed account and keeps the others", () => {
    const first = buildAccount({ accountId: "a" });
    const second = buildAccount({ accountId: "b" });
    const changed = { ...second, role: "manager" as const };

    expect(replaceAccount([first, second], changed)).toEqual([first, changed]);
  });
});

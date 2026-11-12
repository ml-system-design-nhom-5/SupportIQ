import { describe, expect, it } from "vitest";

import type { Account } from "@/features/admin-accounts/model/account";
import { buildResetDialogText } from "@/features/admin-accounts/model/account-form-text";

const minh: Account = {
  accountId: "0b2d4f6a-8c1e-4a3b-9d5f-7e9a1c3e5b18",
  loginName: "staff-2",
  displayName: "Minh Le",
  role: "staff",
  isActive: true,
};

const description =
  "Minh Le (staff-2) will sign in with the new password. The current password stops working at once.";

describe("buildResetDialogText (account management design, Reset password dialog)", () => {
  it.each([
    ["an active account", true, description],
    [
      "a deactivated account",
      false,
      `${description} The account stays deactivated until an admin reactivates it.`,
    ],
  ])("writes the text for %s", (_case, isActive, text) => {
    expect(buildResetDialogText({ ...minh, isActive }).description).toBe(text);
  });
});

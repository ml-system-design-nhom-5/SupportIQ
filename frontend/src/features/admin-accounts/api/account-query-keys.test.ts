import { describe, expect, it } from "vitest";

import { accountQueryKeys } from "@/features/admin-accounts/api/account-query-keys";

describe("accountQueryKeys", () => {
  it("builds the key of the list under the feature's root key (TS-19)", () => {
    expect(accountQueryKeys.accounts()).toEqual(["admin-accounts", "accounts"]);
  });
});

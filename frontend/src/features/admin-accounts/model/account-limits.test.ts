import { describe, expect, it } from "vitest";

import { LOGIN_NUMBER_MAX, LOGIN_NUMBER_MIN } from "@/features/admin-accounts/model/account-limits";
import { readBackendSchema } from "@/test/contract-schemas";

describe("LOGIN_NUMBER_MIN and LOGIN_NUMBER_MAX", () => {
  it("are the range of login_number in the contract (account management design, Login names)", () => {
    const schema = readBackendSchema("CreateAdminAccountRequest");

    expect(schema).toContain(`minimum: ${String(LOGIN_NUMBER_MIN)}\n`);
    expect(schema).toContain(`maximum: ${String(LOGIN_NUMBER_MAX)}\n`);
  });
});

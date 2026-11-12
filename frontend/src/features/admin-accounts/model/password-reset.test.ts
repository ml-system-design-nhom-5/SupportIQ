import { describe, expect, it } from "vitest";

import {
  parsePasswordReset,
  type PasswordResetCheck,
} from "@/features/admin-accounts/model/password-reset";

describe("parsePasswordReset (account management design, Reset password dialog)", () => {
  it.each<[string, string, PasswordResetCheck]>([
    ["an empty password", "", { kind: "invalid", passwordError: "Enter a password." }],
    [
      "a password over 128 characters",
      "a".repeat(129),
      { kind: "invalid", passwordError: "Use at most 128 characters." },
    ],
    [
      "the suggested password",
      "test-test-test",
      { kind: "valid", reset: { password: "test-test-test", isSignedOutEverywhere: true } },
    ],
  ])("checks %s", (_case, password, check) => {
    expect(parsePasswordReset({ password, isSignedOutEverywhere: true })).toEqual(check);
  });
});

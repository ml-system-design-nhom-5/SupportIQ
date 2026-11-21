import { describe, expect, it } from "vitest";

import type { Account } from "@/features/admin-accounts/model/account";
import { toResetFailureNotice } from "@/features/admin-accounts/model/account-notice";
import type { RequestFailure } from "@/features/backend-requests";

const minh: Account = {
  accountId: "0b2d4f6a-8c1e-4a3b-9d5f-7e9a1c3e5b18",
  loginName: "staff-2",
  displayName: "Minh Le",
  role: "staff",
  rawRole: "staff",
  isActive: false,
};

describe("toResetFailureNotice (account management design, Reset password dialog)", () => {
  it.each<[string, RequestFailure, string | undefined]>([
    ["404", { kind: "problem", status: 404, problemType: "not_found" }, "reset_not_found"],
    ["422", { kind: "problem", status: 422, problemType: "invalid_request" }, "reset_refused"],
    ["403", { kind: "problem", status: 403, problemType: "forbidden" }, "permission_denied"],
    ["a timeout, which keeps the dialog open", { kind: "timeout" }, undefined],
    [
      "500, which keeps the dialog open",
      { kind: "problem", status: 500, problemType: "internal_error" },
      undefined,
    ],
  ])("closes the dialog with a notice for %s: %s", (_case, failure, kind) => {
    expect(toResetFailureNotice(minh, failure)?.kind).toBe(kind);
  });
});

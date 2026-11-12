import { describe, expect, it } from "vitest";

import type { RequestFailure } from "@/features/backend-requests";
import {
  classifyPasswordChangeFailure,
  parsePasswordChange,
  type PasswordChangeCheck,
  type PasswordChangeFields,
} from "@/features/session/model/password-change";

const NEW_PASSWORD = "not-the-new-password";

/** Fields that pass every check. */
const validFields: PasswordChangeFields = {
  currentPassword: "not-the-old-password",
  newPassword: NEW_PASSWORD,
  confirmation: NEW_PASSWORD,
  isSignedOutElsewhere: true,
};

/** Each row of the checks table of the design, and what the check returns. */
const checkCases: readonly [string, Partial<PasswordChangeFields>, PasswordChangeCheck][] = [
  [
    "every field empty",
    { currentPassword: "", newPassword: "", confirmation: "" },
    {
      kind: "invalid",
      errors: {
        currentPassword: "Enter your current password.",
        newPassword: "Enter a new password.",
        confirmation: "Enter the new password again.",
      },
    },
  ],
  [
    "a new password over 128 characters",
    { newPassword: "a".repeat(129), confirmation: "a".repeat(129) },
    { kind: "invalid", errors: { newPassword: "Use at most 128 characters." } },
  ],
  [
    "two different new passwords",
    { confirmation: "another-password" },
    { kind: "invalid", errors: { confirmation: "The two new passwords are different." } },
  ],
  [
    "valid fields, sent without the confirmation",
    { isSignedOutElsewhere: false },
    {
      kind: "valid",
      change: {
        currentPassword: "not-the-old-password",
        newPassword: NEW_PASSWORD,
        isSignedOutElsewhere: false,
      },
    },
  ],
];

/** The failure of a `422` that names no rule. */
const refusal: RequestFailure = { kind: "problem", status: 422, problemType: "invalid_request" };

/** Each failure of `changeOwnPassword`, and how the page answers it. */
const failureCases: readonly [string, RequestFailure, string][] = [
  [
    "current_password_incorrect",
    { ...refusal, violatedRule: "current_password_incorrect" },
    "current_password_incorrect",
  ],
  ["another violated_rule", { ...refusal, violatedRule: "own_account" }, "refused"],
  ["an unknown violated_rule (CON-22)", { ...refusal, violatedRule: "a_later_rule" }, "refused"],
  ["no violated_rule", refusal, "refused"],
  ["a timeout", { kind: "timeout" }, "outcome_unknown"],
  ["a 504 from the ingress", { kind: "ingress", status: 504 }, "outcome_unknown"],
  [
    "a reused key",
    { kind: "problem", status: 409, problemType: "idempotency_key_reused" },
    "technical",
  ],
  ["a refused origin", { kind: "problem", status: 403, problemType: "forbidden" }, "technical"],
  ["503", { kind: "problem", status: 503, problemType: "not_ready" }, "technical"],
];

describe("classifyPasswordChangeFailure (account management design, Change password page)", () => {
  it.each(failureCases)("answers %s with %s", (_case, failure, kind) => {
    expect(classifyPasswordChangeFailure(failure)).toBe(kind);
  });
});

describe("parsePasswordChange (account management design, Change password page)", () => {
  it.each(checkCases)("checks %s", (_case, changedFields, check) => {
    expect(parsePasswordChange({ ...validFields, ...changedFields })).toEqual(check);
  });
});

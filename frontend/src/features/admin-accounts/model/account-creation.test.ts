import { describe, expect, it } from "vitest";

import {
  type AccountCreation,
  type AccountCreationCheck,
  type AccountCreationFields,
  findTakenLoginName,
  parseAccountCreation,
} from "@/features/admin-accounts/model/account-creation";
import type { RequestFailure } from "@/features/backend-requests";

const PASSWORD = "test-test-test";

/** Fields that pass every check, with the next free number. */
const validFields: AccountCreationFields = {
  role: "staff",
  loginNumber: "",
  displayName: "Lan Do",
  password: PASSWORD,
};

/** The creation that {@link validFields} sends. */
const validCreation: AccountCreation = { role: "staff", displayName: "Lan Do", password: PASSWORD };

const NUMBER_ERROR = "Enter a whole number from 1 to 9999, or leave it empty.";

/** Each row of the checks table of the design, and what the check returns. */
const checkCases: readonly [string, Partial<AccountCreationFields>, AccountCreationCheck][] = [
  ["the next free number", {}, { kind: "valid", creation: validCreation }],
  [
    "a chosen number at the top of the range",
    { role: "manager", loginNumber: "9999" },
    {
      kind: "valid",
      creation: { role: "manager", loginNumber: 9999, displayName: "Lan Do", password: PASSWORD },
    },
  ],
  [
    "the number 0",
    { loginNumber: "0" },
    { kind: "invalid", errors: { loginNumber: NUMBER_ERROR } },
  ],
  [
    "the number 10000",
    { loginNumber: "10000" },
    { kind: "invalid", errors: { loginNumber: NUMBER_ERROR } },
  ],
  [
    "a decimal number",
    { loginNumber: "4.5" },
    { kind: "invalid", errors: { loginNumber: NUMBER_ERROR } },
  ],
  [
    "a number with a space",
    { loginNumber: " 4" },
    { kind: "invalid", errors: { loginNumber: NUMBER_ERROR } },
  ],
  [
    "an empty display name",
    { displayName: "" },
    { kind: "invalid", errors: { displayName: "Enter a display name." } },
  ],
  [
    "a display name of 101 characters",
    { displayName: "N".repeat(101) },
    { kind: "invalid", errors: { displayName: "Use at most 100 characters." } },
  ],
  [
    "a display name with a space at the end, never trimmed",
    { displayName: "Lan Do " },
    { kind: "invalid", errors: { displayName: "Remove the spaces at the start and the end." } },
  ],
  [
    "a display name with a tab",
    { displayName: "Lan\tDo" },
    { kind: "invalid", errors: { displayName: "Remove line breaks and tabs." } },
  ],
  [
    "an empty password",
    { password: "" },
    { kind: "invalid", errors: { password: "Enter a password." } },
  ],
  [
    "a password over 128 characters",
    { password: "a".repeat(129) },
    { kind: "invalid", errors: { password: "Use at most 128 characters." } },
  ],
];

describe("parseAccountCreation (account management design, Create account dialog)", () => {
  it.each(checkCases)("checks %s", (_case, changedFields, check) => {
    expect(parseAccountCreation({ ...validFields, ...changedFields })).toEqual(check);
  });
});

describe("findTakenLoginName", () => {
  const taken: RequestFailure = { kind: "problem", status: 409, problemType: "login_name_taken" };
  const refusal: RequestFailure = { kind: "problem", status: 422, problemType: "invalid_request" };
  const withNumber: AccountCreation = { ...validCreation, loginNumber: 4 };

  it.each<
    [string, { readonly failure?: RequestFailure; readonly creation?: AccountCreation }, unknown]
  >([
    ["a taken number", { failure: taken, creation: withNumber }, "staff-4"],
    ["a taken name without a number", { failure: taken, creation: validCreation }, undefined],
    ["another failure", { failure: refusal, creation: withNumber }, undefined],
    ["no creation yet", {}, undefined],
  ])("names the login name for %s", (_case, last, loginName) => {
    expect(findTakenLoginName(last.failure, last.creation)).toBe(loginName);
  });
});

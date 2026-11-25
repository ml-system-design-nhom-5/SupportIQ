import { describe, expect, it } from "vitest";

import {
  classifyCreationFailure,
  classifyResetFailure,
} from "@/features/admin-accounts/model/account-form-failure";
import type { RequestFailure } from "@/features/backend-requests";

/** The failure of a `422` that names no rule. */
const refusal: RequestFailure = { kind: "problem", status: 422, problemType: "invalid_request" };

const forbidden: RequestFailure = { kind: "problem", status: 403, problemType: "forbidden" };

describe("classifyCreationFailure (account management design, Create account dialog)", () => {
  it.each<[string, RequestFailure, string]>([
    [
      "409 login-name-taken",
      { kind: "problem", status: 409, problemType: "login_name_taken" },
      "login_name_taken",
    ],
    ["422", refusal, "refused"],
    ["403", forbidden, "permission_denied"],
    ["a lost connection", { kind: "network" }, "outcome_unknown"],
    [
      "409 idempotency-key-reused",
      { kind: "problem", status: 409, problemType: "idempotency_key_reused" },
      "technical",
    ],
    ["500", { kind: "problem", status: 500, problemType: "internal_error" }, "technical"],
    ["429 from the ingress", { kind: "ingress", status: 429 }, "technical"],
  ])("answers %s with %s", (_case, failure, kind) => {
    expect(classifyCreationFailure(failure)).toBe(kind);
  });
});

describe("classifyResetFailure (account management design, Reset password dialog)", () => {
  it.each<[string, RequestFailure, string]>([
    ["own_account", { ...refusal, violatedRule: "own_account" }, "refused"],
    [
      "admin_password_unresettable",
      { ...refusal, violatedRule: "admin_password_unresettable" },
      "refused",
    ],
    ["an unknown violated_rule (CON-22)", { ...refusal, violatedRule: "a_later_rule" }, "refused"],
    ["no violated_rule", refusal, "refused"],
    ["404", { kind: "problem", status: 404, problemType: "not_found" }, "not_found"],
    ["403", forbidden, "permission_denied"],
    ["a 2xx with an unreadable body", { kind: "invalid_response" }, "outcome_unknown"],
    ["503", { kind: "problem", status: 503, problemType: "not_ready" }, "technical"],
  ])("answers %s with %s", (_case, failure, kind) => {
    expect(classifyResetFailure(failure)).toBe(kind);
  });
});

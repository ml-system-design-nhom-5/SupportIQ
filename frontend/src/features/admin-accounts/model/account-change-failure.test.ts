import { describe, expect, it } from "vitest";

import { classifyChangeFailure } from "@/features/admin-accounts/model/account-change-failure";
import type { RequestFailure } from "@/features/backend-requests";

/** The failure of a `422` that names no rule. */
const refusal: RequestFailure = { kind: "problem", status: 422, problemType: "invalid_request" };

describe("classifyChangeFailure", () => {
  it("gives last_active_manager its own banner", () => {
    expect(classifyChangeFailure({ ...refusal, violatedRule: "last_active_manager" })).toBe(
      "last_active_manager",
    );
  });

  it.each([
    "own_account",
    "admin_role_unchangeable",
    "role_unchanged",
    "status_unchanged",
    "a_rule_of_a_later_version",
  ])("asks to reload the list for the rule %s", (violatedRule) => {
    expect(classifyChangeFailure({ ...refusal, violatedRule })).toBe("refused");
  });

  it("asks to reload the list when the 422 names no rule", () => {
    expect(classifyChangeFailure(refusal)).toBe("refused");
  });
});

describe("classifyChangeFailure, other failures", () => {
  it.each<[RequestFailure, string]>([
    [{ kind: "problem", status: 404, problemType: "not_found" }, "not_found"],
    [{ kind: "problem", status: 403, problemType: "forbidden" }, "permission_denied"],
    [{ kind: "problem", status: 503, problemType: "not_ready" }, "technical"],
    [{ kind: "problem", status: 409, problemType: "idempotency_key_reused" }, "technical"],
    [{ kind: "ingress", status: 503 }, "technical"],
    [{ kind: "problem", status: 500, problemType: "internal_error" }, "technical"],
    [{ kind: "invalid_response" }, "outcome_unknown"],
    [
      { kind: "problem", status: 403, problemType: "forbidden", isAfterUnknownOutcome: true },
      "permission_denied",
    ],
    [
      { kind: "problem", status: 503, problemType: "not_ready", isAfterUnknownOutcome: true },
      "outcome_unknown",
    ],
    [{ kind: "ingress", status: 502 }, "outcome_unknown"],
    [{ kind: "ingress", status: 504 }, "outcome_unknown"],
    [{ kind: "network" }, "outcome_unknown"],
    [{ kind: "timeout" }, "outcome_unknown"],
  ])("classifies %j as %s", (failure, kind) => {
    expect(classifyChangeFailure(failure)).toBe(kind);
  });
});

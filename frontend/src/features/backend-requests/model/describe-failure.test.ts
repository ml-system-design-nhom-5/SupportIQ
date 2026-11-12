import { describe, expect, it } from "vitest";

import {
  categorizeFailure,
  describeFailure,
} from "@/features/backend-requests/model/describe-failure";
import {
  parseFailureResponse,
  type RequestFailure,
} from "@/features/backend-requests/model/request-failure";
import { readExample } from "@/test/contract-examples";

describe("categorizeFailure", () => {
  it.each([
    ["unauthenticated", 401, "session_expired"],
    ["forbidden-role", 403, "permission_denied"],
    ["not-found", 404, "not_found"],
    ["invalid-request", 422, "invalid_request"],
    ["idempotency-key-reused", 409, "conflict"],
    ["login-name-taken", 409, "conflict"],
    ["not-ready", 503, "unavailable"],
    ["internal-error", 500, "unexpected"],
  ])("puts the %s problem in %s", (example, status, category) => {
    const failure = parseFailureResponse(status, readExample("problems", example));

    expect(categorizeFailure(failure)).toBe(category);
  });

  it.each<[RequestFailure, string]>([
    [{ kind: "ingress", status: 413 }, "too_large"],
    [{ kind: "ingress", status: 429 }, "rate_limited"],
    [{ kind: "ingress", status: 502 }, "unavailable"],
    [{ kind: "ingress", status: 503 }, "unavailable"],
    [{ kind: "ingress", status: 504 }, "unavailable"],
    [{ kind: "ingress", status: 418 }, "unexpected"],
    [{ kind: "network" }, "network"],
    [{ kind: "timeout" }, "timeout"],
    [{ kind: "invalid_response" }, "unexpected"],
    [{ kind: "problem", status: 403, problemType: "unknown" }, "unexpected"],
  ])("puts %j in %s", (failure, category) => {
    expect(categorizeFailure(failure)).toBe(category);
  });
});

describe("describeFailure", () => {
  it("gives a plain-language message and the trace ID of a Problem Details failure", () => {
    const failure = parseFailureResponse(503, readExample("problems", "not-ready"));

    const description = describeFailure(failure);

    expect(description).toEqual({
      category: "unavailable",
      message: "The service is not available right now. Try again in a moment.",
      traceId: "1c80319c0af7651916cd43dd8448eb21",
    });
  });

  it("has no trace ID for a failure without Problem Details", () => {
    const description = describeFailure({ kind: "network" });

    expect(description).toEqual({
      category: "network",
      message: "The server could not be reached. Check your connection and try again.",
    });
  });

  it("never shows a status code, a problem type, or the detail of backend (UI-25)", () => {
    const failure = parseFailureResponse(500, readExample("problems", "internal-error"));

    const { message } = describeFailure(failure);

    expect(message).not.toMatch(/500|internal|urn:|unexpected error occurred/i);
  });
});

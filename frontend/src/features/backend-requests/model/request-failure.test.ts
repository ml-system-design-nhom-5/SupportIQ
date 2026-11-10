import { describe, expect, it } from "vitest";

import {
  getRequestFailure,
  isRefusedByBackend,
  isUnauthenticatedError,
  isWriteOutcomeUnknown,
  parseFailureResponse,
  type RequestFailure,
  RequestFailureError,
  toProblemType,
} from "@/features/backend-requests/model/request-failure";
import { readExample, readExampleWith } from "@/test/contract-examples";

describe("toProblemType", () => {
  it.each([
    ["urn:supportiq:problem:invalid-request", "invalid_request"],
    ["urn:supportiq:problem:unauthenticated", "unauthenticated"],
    ["urn:supportiq:problem:forbidden", "forbidden"],
    ["urn:supportiq:problem:not-found", "not_found"],
    ["urn:supportiq:problem:idempotency-key-reused", "idempotency_key_reused"],
    ["urn:supportiq:problem:not-ready", "not_ready"],
    ["urn:supportiq:problem:internal-error", "internal_error"],
  ])("maps %s to %s", (urn, problemType) => {
    expect(toProblemType(urn)).toBe(problemType);
  });

  it("maps a problem type that the contract does not list to unknown (CON-22)", () => {
    expect(toProblemType("urn:supportiq:problem:authority-required")).toBe("unknown");
  });
});

describe("parseFailureResponse", () => {
  it("parses a Problem Details body with its trace ID", () => {
    const failure = parseFailureResponse(404, readExample("problems", "not-found"));

    expect(failure).toEqual({
      kind: "problem",
      status: 404,
      problemType: "not_found",
      traceId: "c80319c0af7651916cd43dd8448eb211",
    });
  });

  it("keeps the violated rule of a refused admin change", () => {
    const failure = parseFailureResponse(422, readExample("problems", "last-active-manager"));

    expect(failure).toMatchObject({
      problemType: "invalid_request",
      violatedRule: "last_active_manager",
    });
  });

  it("drops a trace ID that is not 32 lowercase hexadecimal characters", () => {
    const body = readExampleWith("problems", "internal-error", { trace_id: "not-a-trace" });

    const failure = parseFailureResponse(500, body);

    expect(failure).toEqual({ kind: "problem", status: 500, problemType: "internal_error" });
  });

  it.each([
    ["an HTML page of the ingress", 502, "<html><body>Bad Gateway</body></html>"],
    ["an empty body", 504, undefined],
    ["JSON that is not Problem Details", 429, { message: "slow down" }],
    ["null", 413, null],
  ])("treats %s as an ingress failure", (_case, status, body) => {
    expect(parseFailureResponse(status, body)).toEqual({ kind: "ingress", status });
  });
});

describe("getRequestFailure", () => {
  it("returns the failure of a RequestFailureError", () => {
    const error = new RequestFailureError({ kind: "network" });

    expect(getRequestFailure(error)).toEqual({ kind: "network" });
  });

  it("returns undefined for any other error", () => {
    expect(getRequestFailure(new Error("boom"))).toBeUndefined();
  });
});

describe("isUnauthenticatedError", () => {
  it("is true for a 401 Problem Details failure", () => {
    const error = new RequestFailureError(
      parseFailureResponse(401, readExample("problems", "unauthenticated")),
    );

    expect(isUnauthenticatedError(error)).toBe(true);
  });

  it.each([
    [
      "a 403",
      new RequestFailureError(parseFailureResponse(403, readExample("problems", "forbidden-role"))),
    ],
    [
      "an ingress 401 without Problem Details",
      new RequestFailureError({ kind: "ingress", status: 401 }),
    ],
    ["a plain error", new Error("boom")],
  ])("is false for %s", (_case, error) => {
    expect(isUnauthenticatedError(error)).toBe(false);
  });
});

describe("isRefusedByBackend", () => {
  it.each<[RequestFailure, boolean]>([
    [{ kind: "problem", status: 422, problemType: "invalid_request" }, true],
    [{ kind: "problem", status: 404, problemType: "not_found" }, true],
    [{ kind: "problem", status: 401, problemType: "unauthenticated" }, false],
    [{ kind: "problem", status: 403, problemType: "forbidden" }, false],
    [{ kind: "problem", status: 409, problemType: "idempotency_key_reused" }, false],
    [{ kind: "problem", status: 500, problemType: "internal_error" }, false],
    [{ kind: "problem", status: 503, problemType: "not_ready" }, false],
    [{ kind: "ingress", status: 429 }, false],
    [{ kind: "network" }, false],
  ])("answers for %j: %s", (failure, isRefused) => {
    expect(isRefusedByBackend(failure)).toBe(isRefused);
  });
});

describe("isWriteOutcomeUnknown", () => {
  it.each<[RequestFailure, boolean]>([
    [{ kind: "timeout" }, true],
    [{ kind: "network" }, true],
    [{ kind: "ingress", status: 502 }, true],
    [{ kind: "ingress", status: 504 }, true],
    [{ kind: "problem", status: 504, problemType: "unknown" }, true],
    [{ kind: "ingress", status: 503 }, false],
    [{ kind: "ingress", status: 413 }, false],
    [{ kind: "ingress", status: 429 }, false],
    [{ kind: "problem", status: 500, problemType: "internal_error" }, false],
    [{ kind: "problem", status: 503, problemType: "not_ready" }, false],
    [{ kind: "invalid_response" }, true],
    [{ kind: "ingress", status: 429, isAfterUnknownOutcome: true }, true],
  ])("answers for %j: %s", (failure, isUnknown) => {
    expect(isWriteOutcomeUnknown(failure)).toBe(isUnknown);
  });
});

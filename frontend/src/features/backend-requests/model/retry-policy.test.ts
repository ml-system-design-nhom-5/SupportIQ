import { describe, expect, it } from "vitest";

import {
  type RequestFailure,
  RequestFailureError,
} from "@/features/backend-requests/model/request-failure";
import {
  computeRetryDelayMs,
  isRetryableFailure,
  shouldRetryRequest,
} from "@/features/backend-requests/model/retry-policy";

describe("isRetryableFailure", () => {
  it.each<[RequestFailure, boolean]>([
    [{ kind: "network" }, true],
    [{ kind: "timeout" }, true],
    [{ kind: "ingress", status: 429 }, true],
    [{ kind: "ingress", status: 502 }, true],
    [{ kind: "ingress", status: 503 }, true],
    [{ kind: "ingress", status: 504 }, true],
    [{ kind: "problem", status: 503, problemType: "not_ready" }, true],
    [{ kind: "ingress", status: 413 }, false],
    [{ kind: "ingress", status: 500 }, false],
    [{ kind: "problem", status: 500, problemType: "internal_error" }, false],
    [{ kind: "problem", status: 422, problemType: "invalid_request" }, false],
    [{ kind: "problem", status: 401, problemType: "unauthenticated" }, false],
    [{ kind: "problem", status: 409, problemType: "idempotency_key_reused" }, false],
    [{ kind: "invalid_response" }, false],
  ])("decides that %j is retryable: %s (ERR-12)", (failure, isRetryable) => {
    expect(isRetryableFailure(failure)).toBe(isRetryable);
  });
});

describe("shouldRetryRequest", () => {
  const timeout = new RequestFailureError({ kind: "timeout" });

  it.each([
    [0, true],
    [1, true],
    [2, false],
  ])("after %i retries of a timeout with a bound of 2, retries again: %s", (count, shouldRetry) => {
    expect(shouldRetryRequest(count, timeout, 2)).toBe(shouldRetry);
  });

  it("never retries when the bound is 0", () => {
    expect(shouldRetryRequest(0, timeout, 0)).toBe(false);
  });

  it("never retries an error that is not a request failure", () => {
    expect(shouldRetryRequest(0, new Error("defect"), 2)).toBe(false);
  });
});

describe("computeRetryDelayMs", () => {
  it.each([
    [0, 0, 250],
    [0, 0.999, 500],
    [1, 0, 500],
    [2, 0.5, 1500],
  ])("waits for attempt %i with random share %f: %i ms", (attempt, randomShare, delayMs) => {
    expect(computeRetryDelayMs(attempt, 500, randomShare)).toBe(delayMs);
  });
});

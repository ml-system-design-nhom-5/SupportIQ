import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createAppDependencies } from "@/app/composition-root";
import { buildIdempotentWriteKey, RequestFailureError } from "@/features/backend-requests";
import { fixedRandomBytes, TEST_BASE_URL, testNow } from "@/test/render-app";

const RETRY_MAX_COUNT = 2;

const RETRY_BASE_DELAY_MS = 100;

const ENOUGH_TIME_FOR_EVERY_RETRY_MS = 10_000;

const timeoutError = new RequestFailureError({ kind: "timeout" });

const invalidRequestError = new RequestFailureError({
  kind: "problem",
  status: 422,
  problemType: "invalid_request",
});

/**
 * Create the dependencies with two retries.
 *
 * @returns The query client of the app.
 */
function createQueryClient() {
  return createAppDependencies({
    settings: {
      requestTimeoutMs: 1000,
      requestRetryMaxCount: RETRY_MAX_COUNT,
      requestRetryBaseDelayMs: RETRY_BASE_DELAY_MS,
      isDevModeAvailable: false,
      backendWakeTimeoutMs: 90_000,
      viteSettings: [],
    },
    baseUrl: TEST_BASE_URL,
    fetch: () => Promise.reject(new Error("not used")),
    random: () => 0,
    clock: () => testNow,
    createIdempotencyKey: () => "00000000-0000-4000-8000-000000000000",
    randomBytes: fixedRandomBytes,
    preferenceStorage: undefined,
  }).queryClient;
}

describe("createAppDependencies, read retries", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("retries a read that timed out up to the bound (ERR-12, ERR-13)", async () => {
    const queryClient = createQueryClient();
    const queryFn = vi.fn(() => Promise.reject(timeoutError));

    const query = queryClient.query({ queryKey: ["read"], queryFn });
    const assertion = expect(query).rejects.toBe(timeoutError);
    await vi.advanceTimersByTimeAsync(ENOUGH_TIME_FOR_EVERY_RETRY_MS);

    await assertion;
    expect(queryFn).toHaveBeenCalledTimes(1 + RETRY_MAX_COUNT);
  });

  it("never retries a read that backend refused with 422", async () => {
    const queryClient = createQueryClient();
    const queryFn = vi.fn(() => Promise.reject(invalidRequestError));

    const query = queryClient.query({ queryKey: ["read"], queryFn });
    const assertion = expect(query).rejects.toBe(invalidRequestError);
    await vi.advanceTimersByTimeAsync(ENOUGH_TIME_FOR_EVERY_RETRY_MS);

    await assertion;
    expect(queryFn).toHaveBeenCalledTimes(1);
  });
});

describe("createAppDependencies, write retries", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("never retries a write without an Idempotency-Key, such as sign-in (TS-29)", async () => {
    const queryClient = createQueryClient();
    const mutationFn = vi.fn(() => Promise.reject(timeoutError));
    const mutation = queryClient.getMutationCache().build(queryClient, { mutationFn });

    const execution = mutation.execute(undefined);
    const assertion = expect(execution).rejects.toBe(timeoutError);
    await vi.advanceTimersByTimeAsync(ENOUGH_TIME_FOR_EVERY_RETRY_MS);

    await assertion;
    expect(mutationFn).toHaveBeenCalledTimes(1);
  });

  it("retries a write with an Idempotency-Key, with the same variables (TS-29)", async () => {
    const queryClient = createQueryClient();
    const mutationFn = vi.fn<(variables: { readonly idempotencyKey: string }) => Promise<void>>(
      () => Promise.reject(timeoutError),
    );
    const mutation = queryClient.getMutationCache().build(queryClient, {
      mutationKey: buildIdempotentWriteKey("createShopTicket"),
      mutationFn,
    });

    const execution = mutation.execute({ idempotencyKey: "key-of-one-action" });
    const assertion = expect(execution).rejects.toBe(timeoutError);
    await vi.advanceTimersByTimeAsync(ENOUGH_TIME_FOR_EVERY_RETRY_MS);

    await assertion;
    expect(mutationFn.mock.calls.map(([variables]) => variables.idempotencyKey)).toEqual([
      "key-of-one-action",
      "key-of-one-action",
      "key-of-one-action",
    ]);
  });
});

describe("createAppDependencies, expired session", () => {
  it("ends the session when any request answers 401", async () => {
    const queryClient = createQueryClient();
    const unauthenticated = new RequestFailureError({
      kind: "problem",
      status: 401,
      problemType: "unauthenticated",
    });
    queryClient.setQueryData(["session", "current"], { kind: "signed_in" });

    await expect(
      queryClient.query({
        queryKey: ["shop-orders", "order", "ORD-1"],
        queryFn: () => Promise.reject(unauthenticated),
      }),
    ).rejects.toBe(unauthenticated);

    expect(queryClient.getQueryData(["session", "current"])).toEqual({
      kind: "signed_out",
      reason: "no_valid_session",
    });
  });

  it("does not end the session for another failure", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(["session", "current"], { kind: "signed_in" });

    await expect(
      queryClient.query({ queryKey: ["read"], queryFn: () => Promise.reject(invalidRequestError) }),
    ).rejects.toBe(invalidRequestError);

    expect(queryClient.getQueryData(["session", "current"])).toEqual({ kind: "signed_in" });
  });
});

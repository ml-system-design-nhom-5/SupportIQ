import { afterEach, describe, expect, it, vi } from "vitest";

import { createBackendWaker } from "@/features/backend-requests/api/wake-backend";

const WAKE_ORIGIN = "https://backend.example.test";
/** The default of `VITE_BACKEND_WAKE_TIMEOUT_MS` (backend wake-up design, Data and contracts). */
const WAKE_TIMEOUT_MS = 90_000;

afterEach(() => {
  vi.useRealTimers();
});

describe("The wake request (backend wake-up design, rules 1 and 2)", () => {
  it("is GET /health/live on the Render origin, without cookie, referrer, body, or header", () => {
    const fake = createFakeFetch();

    void createWaker(fake.fetch)();

    const request = fake.received(0);
    expect(request.method).toBe("GET");
    expect(request.url).toBe(`${WAKE_ORIGIN}/health/live`);
    expect(request.mode).toBe("no-cors");
    expect(request.credentials).toBe("omit");
    expect(request.referrerPolicy).toBe("no-referrer");
    expect(request.body).toBeNull();
    expect([...request.headers.keys()]).toEqual([]);
    expect(request.signal.aborted).toBe(false);
  });

  it("is never sent without a wake origin (rule 9)", () => {
    const fake = createFakeFetch();
    const wake = createBackendWaker({ origin: undefined, timeoutMs: 1, fetch: fake.fetch });

    expect(wake()).toBeUndefined();
    expect(fake.fetch).not.toHaveBeenCalled();
  });
});

describe("The wake request in flight (rule 5)", () => {
  it("sends one request for two triggers in a row, and another once the first settles", async () => {
    const fake = createFakeFetch();
    const wake = createWaker(fake.fetch);

    const first = wake();
    expect(wake()).toBeUndefined();
    expect(fake.fetch).toHaveBeenCalledTimes(1);

    fake.settle(0, "answer");
    await first;
    void wake();
    expect(fake.fetch).toHaveBeenCalledTimes(2);
  });

  it("ignores a rejected wake request, and the next trigger sends a new one (rule 3)", async () => {
    const fake = createFakeFetch();
    const wake = createWaker(fake.fetch);

    const first = wake();
    fake.settle(0, "reject");

    await expect(first).resolves.toBeUndefined();
    void wake();
    expect(fake.fetch).toHaveBeenCalledTimes(2);
  });
});

describe("The wake timeout (rule 6)", () => {
  it("aborts the wake request after the wake timeout, and the next trigger sends a new one", async () => {
    vi.useFakeTimers();
    const fake = createFakeFetch();
    const wake = createBackendWaker({ origin: WAKE_ORIGIN, timeoutMs: 2500, fetch: fake.fetch });

    const first = wake();
    await vi.advanceTimersByTimeAsync(2499);
    expect(fake.received(0).signal.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(fake.received(0).signal.aborted).toBe(true);

    await expect(first).resolves.toBeUndefined();
    void wake();
    expect(fake.fetch).toHaveBeenCalledTimes(2);
  });
});

/**
 * Create a waker with the default wake timeout.
 *
 * @param fetch - The fake fetch.
 * @returns The waker.
 */
function createWaker(fetch: (request: Request) => Promise<Response>) {
  return createBackendWaker({ origin: WAKE_ORIGIN, timeoutMs: WAKE_TIMEOUT_MS, fetch });
}

/**
 * Create a fake fetch whose answers the test settles, one by one. A request that is aborted
 * rejects, as the browser's fetch does.
 *
 * @returns The fetch, the requests it received, and how to settle each one.
 */
function createFakeFetch() {
  const requests: Request[] = [];
  const settlers: ((outcome: "answer" | "reject") => void)[] = [];
  const fetch = vi.fn(
    (request: Request) =>
      new Promise<Response>((resolve, reject) => {
        requests.push(request);
        settlers.push((outcome) => {
          if (outcome === "answer") {
            resolve(new Response(null, { status: 204 }));
          } else {
            reject(new TypeError("Failed to fetch"));
          }
        });
        request.signal.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      }),
  );
  return {
    fetch,
    received(index: number): Request {
      const request = requests[index];
      if (request === undefined) {
        throw new Error(`No wake request ${String(index)} was sent.`);
      }
      return request;
    },
    settle(index: number, outcome: "answer" | "reject"): void {
      settlers[index]?.(outcome);
    },
  };
}

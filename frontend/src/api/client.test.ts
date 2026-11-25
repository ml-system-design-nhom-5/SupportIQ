import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type BackendClient, createBackendClient, RequestTimeoutError } from "@/api/client";
import { createFakeBackend, exampleAnswer, type FakeAnswer } from "@/test/fake-backend";
import { TEST_BASE_URL } from "@/test/render-app";

const sessionRoute = { method: "GET", path: "/v1/sessions/current" } as const;
const TIMEOUT_MS = 10_000;

/**
 * Create a client whose fake backend answers the session route.
 *
 * @param answer - What the fake backend answers.
 * @returns The client and the fake backend.
 */
function createClientAnswering(answer: FakeAnswer) {
  const backend = createFakeBackend();
  backend.answer(sessionRoute, answer);
  const client: BackendClient = createBackendClient({
    baseUrl: TEST_BASE_URL,
    requestTimeoutMs: TIMEOUT_MS,
    fetch: backend.fetch,
  });
  return { backend, client };
}

describe("createBackendClient", () => {
  it("sends requests to the base URL and returns the example body", async () => {
    const { backend, client } = createClientAnswering(
      exampleAnswer(200, "getCurrentSession", "customer"),
    );

    const { data: session } = await client.GET("/v1/sessions/current");

    expect(session).toMatchObject({ role: "customer", display_name: "Lan Tran" });
    expect(backend.requests[0]?.path).toBe("/v1/sessions/current");
  });
});

describe("createBackendClient, timeout and cancellation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stops waiting after the request timeout (ERR-09)", async () => {
    const { client } = createClientAnswering({ kind: "no_answer" });

    const request = client.GET("/v1/sessions/current");
    const assertion = expect(request).rejects.toBeInstanceOf(RequestTimeoutError);
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS);

    await assertion;
  });

  it("stops waiting when the body of a response stops arriving (ERR-09, ERR-21)", async () => {
    const client = createBackendClient({
      baseUrl: TEST_BASE_URL,
      requestTimeoutMs: TIMEOUT_MS,
      fetch: () => Promise.resolve(new Response(new ReadableStream({ start: () => undefined }))),
    });

    const request = client.GET("/v1/sessions/current");
    const assertion = expect(request).rejects.toBeInstanceOf(RequestTimeoutError);
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS);

    await assertion;
  });

  it("keeps waiting just before the request timeout", async () => {
    const { client } = createClientAnswering({ kind: "no_answer" });
    const onSettled = vi.fn();

    void client.GET("/v1/sessions/current").then(onSettled, onSettled);
    await vi.advanceTimersByTimeAsync(TIMEOUT_MS - 1);

    expect(onSettled).not.toHaveBeenCalled();
  });

  it("lets the caller cancel a request with its own signal", async () => {
    const { client } = createClientAnswering({ kind: "no_answer" });
    const controller = new AbortController();

    const request = client.GET("/v1/sessions/current", { signal: controller.signal });
    controller.abort();

    await expect(request).rejects.toMatchObject({ name: "AbortError" });
  });
});

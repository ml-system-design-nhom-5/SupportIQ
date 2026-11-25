import { afterEach, describe, expect, it, vi } from "vitest";

import { type BackendClient, createBackendClient } from "@/api/client";
import { requestData, requestNoContent } from "@/features/backend-requests/api/request-backend";
import { RequestFailureError } from "@/features/backend-requests/model/request-failure";
import {
  createFakeBackend,
  exampleAnswer,
  type FakeAnswer,
  type FakeBackend,
  noContentAnswer,
} from "@/test/fake-backend";
import { TEST_BASE_URL } from "@/test/render-app";

const sessionRoute = { method: "GET", path: "/v1/sessions/current" } as const;
const signOutRoute = { method: "DELETE", path: "/v1/sessions/current" } as const;
const TIMEOUT_MS = 10_000;

/**
 * Create a client over a fake backend.
 *
 * @param backend - The fake backend.
 * @returns The client.
 */
function createClient(backend: FakeBackend): BackendClient {
  return createBackendClient({
    baseUrl: TEST_BASE_URL,
    requestTimeoutMs: TIMEOUT_MS,
    fetch: backend.fetch,
  });
}

/**
 * Keep a body as it is, for the tests about the request itself.
 *
 * @param body - The body.
 * @returns The same body.
 */
function keepBody<Body>(body: Body): Body {
  return body;
}

/**
 * Read the session through requestData with one answer.
 *
 * @param answer - What the fake backend answers.
 * @returns The promise of requestData.
 */
function readSessionWith(answer: FakeAnswer): Promise<unknown> {
  const backend = createFakeBackend();
  backend.answer(sessionRoute, answer);
  const client = createClient(backend);
  return requestData(() => client.GET("/v1/sessions/current"), keepBody);
}

describe("requestData", () => {
  it("returns the body of a success response", async () => {
    const session = await readSessionWith(exampleAnswer(200, "getCurrentSession", "staff"));

    expect(session).toMatchObject({ role: "staff" });
  });
});

describe("requestData, the mapping of the body", () => {
  it("returns what the mapping makes of the body", async () => {
    const backend = createFakeBackend();
    backend.answer(sessionRoute, exampleAnswer(200, "getCurrentSession", "staff"));
    const client = createClient(backend);

    const role = await requestData(
      () => client.GET("/v1/sessions/current"),
      (view) => view.role,
    );

    expect(role).toBe("staff");
  });

  it("throws an invalid-response failure with the cause when the body cannot be mapped", async () => {
    const backend = createFakeBackend();
    backend.answer(sessionRoute, exampleAnswer(200, "getCurrentSession", "staff"));
    const client = createClient(backend);
    const mappingError = new TypeError("The body has no items.");

    const request = requestData(
      () => client.GET("/v1/sessions/current"),
      () => {
        throw mappingError;
      },
    );

    await expect(request).rejects.toMatchObject({
      failure: { kind: "invalid_response" },
      cause: mappingError,
    });
  });
});

describe("requestData, failed responses", () => {
  it("throws a problem failure with the trace ID for a Problem Details response", async () => {
    const request = readSessionWith(exampleAnswer(401, "problems", "unauthenticated"));

    await expect(request).rejects.toEqual(
      new RequestFailureError({
        kind: "problem",
        status: 401,
        problemType: "unauthenticated",
        traceId: "4bf92f3577b34da6a3ce929d0e0e4736",
      }),
    );
  });

  it.each([413, 429, 502, 504])("throws an ingress failure for an HTML %i", async (status) => {
    const request = readSessionWith({ kind: "ingress", status });

    await expect(request).rejects.toMatchObject({ failure: { kind: "ingress", status } });
  });
});

describe("requestData, transport failures", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("throws a network failure when the connection is lost", async () => {
    const request = readSessionWith({ kind: "network_error" });

    await expect(request).rejects.toMatchObject({ failure: { kind: "network" } });
  });

  it("throws a timeout failure when backend does not answer in time", async () => {
    vi.useFakeTimers();
    const request = readSessionWith({ kind: "no_answer" });
    const assertion = expect(request).rejects.toMatchObject({ failure: { kind: "timeout" } });

    await vi.advanceTimersByTimeAsync(TIMEOUT_MS);

    await assertion;
  });

  it("throws an invalid-response failure for a success without a body", async () => {
    const request = readSessionWith({ kind: "no_content", status: 200 });

    await expect(request).rejects.toMatchObject({ failure: { kind: "invalid_response" } });
  });

  it("passes the cancellation of the caller through, which is not a failure", async () => {
    const backend = createFakeBackend();
    backend.answer(sessionRoute, { kind: "no_answer" });
    const client = createClient(backend);
    const controller = new AbortController();

    const request = requestData(
      () => client.GET("/v1/sessions/current", { signal: controller.signal }),
      keepBody,
    );
    controller.abort();

    await expect(request).rejects.not.toBeInstanceOf(RequestFailureError);
  });

  it("rethrows an error that is not a request failure, which is a defect", async () => {
    const defect = new RangeError("defect");

    const request = requestData(() => Promise.reject(defect), keepBody);

    await expect(request).rejects.toBe(defect);
  });
});

describe("requestNoContent", () => {
  it("resolves for a 204 response", async () => {
    const backend = createFakeBackend();
    backend.answer(signOutRoute, noContentAnswer);
    const client = createClient(backend);

    await expect(
      requestNoContent(() => client.DELETE("/v1/sessions/current")),
    ).resolves.toBeUndefined();
  });

  it("throws the failure of an error response", async () => {
    const backend = createFakeBackend();
    backend.answer(signOutRoute, exampleAnswer(403, "problems", "forbidden-origin"));
    const client = createClient(backend);

    const request = requestNoContent(() => client.DELETE("/v1/sessions/current"));

    await expect(request).rejects.toMatchObject({
      failure: { kind: "problem", problemType: "forbidden" },
    });
  });
});

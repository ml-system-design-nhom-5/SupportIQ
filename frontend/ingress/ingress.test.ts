import { afterEach, describe, expect, it, vi } from "vitest";

import { createIngress, type IngressContext, InvalidSettingError, onRequest } from "./ingress.ts";

const BACKEND_ORIGIN = "https://backend.example.test";
const PAGES_ORIGIN = "https://supportiq.example.test";
const settings = { SUPPORTIQ_BACKEND_URL: BACKEND_ORIGIN };
/** The backend contract, section Timeouts: the caller's timeout. */
const CONTRACT_TIMEOUT_MS = 10_000;
/** ADR-0011, Ingress: the largest request body. */
const MAX_BODY_BYTES = 65_536;

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("The ingress, the request to backend (ADR-0016, statement 3)", () => {
  it("forwards the method, path, query, headers, and body unchanged, once", async () => {
    const backend = createFakeBackend(() => Promise.resolve(new Response(null, { status: 201 })));
    const request = new Request(`${PAGES_ORIGIN}/v1/console/tickets/T-1/replies?view=full`, {
      method: "POST",
      headers: {
        Origin: PAGES_ORIGIN,
        Cookie: "supportiq_session=s1",
        "Idempotency-Key": "3f0c2a8e-key",
        traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body: "We call you today." }),
    });
    const sentHeaders = Object.fromEntries(request.headers);

    await createIngress(backend)(contextOf(request));

    expect(backend.fetch).toHaveBeenCalledTimes(1);
    const forwarded = backend.received(0);
    expect(forwarded.url).toBe(`${BACKEND_ORIGIN}/v1/console/tickets/T-1/replies?view=full`);
    expect(forwarded.method).toBe("POST");
    expect(Object.fromEntries(forwarded.headers)).toEqual(sentHeaders);
    expect(await forwarded.text()).toBe(JSON.stringify({ body: "We call you today." }));
  });

  it("forwards a request without a body, such as the health checks", async () => {
    const backend = createFakeBackend(() => Promise.resolve(new Response(null, { status: 204 })));

    await createIngress(backend)(contextOf(get("/health/live")));

    expect(backend.received(0).url).toBe(`${BACKEND_ORIGIN}/health/live`);
    expect(backend.received(0).body).toBeNull();
  });
});

describe("The ingress, the answer of backend (ADR-0016, statement 3)", () => {
  it("returns the answer of backend itself, every Set-Cookie included, without CORS", async () => {
    const headers = new Headers({ "Content-Type": "application/json" });
    headers.append("Set-Cookie", "supportiq_session=s2; Path=/; HttpOnly; SameSite=Strict");
    headers.append("Set-Cookie", "supportiq_csrf=c2; Path=/; SameSite=Strict");
    const answerOfBackend = new Response('{"status":"open"}', { status: 200, headers });
    const backend = createFakeBackend(() => Promise.resolve(answerOfBackend));

    const answer = await createIngress(backend)(contextOf(get("/v1/session")));

    expect(answer).toBe(answerOfBackend);
    expect(answer.headers.getSetCookie()).toEqual([
      "supportiq_session=s2; Path=/; HttpOnly; SameSite=Strict",
      "supportiq_csrf=c2; Path=/; SameSite=Strict",
    ]);
    expect([...answer.headers.keys()].filter((name) => name.startsWith("access-control-"))).toEqual(
      [],
    );
  });

  it("returns a redirect of backend as it is, without following it", async () => {
    const redirect = new Response(null, { status: 303, headers: { Location: "/v1/session" } });
    const backend = createFakeBackend(() => Promise.resolve(redirect));

    const answer = await createIngress(backend)(contextOf(get("/v1/sessions")));

    expect(answer).toBe(redirect);
    expect(backend.received(0).redirect).toBe("manual");
  });
});

describe("The ingress, when backend fails (ADR-0016, statement 4)", () => {
  it("answers 502 with an empty body when backend cannot be reached, and never retries", async () => {
    const backend = createFakeBackend(() => Promise.reject(new TypeError("fetch failed")));

    const answer = await createIngress(backend)(contextOf(get("/v1/session")));

    expect(answer.status).toBe(502);
    expect(await answer.text()).toBe("");
    expect(backend.fetch).toHaveBeenCalledTimes(1);
  });

  it.each([502, 503])("returns a %i of backend unchanged, without a retry", async (status) => {
    const answerOfBackend = new Response(null, { status });
    const backend = createFakeBackend(() => Promise.resolve(answerOfBackend));

    const answer = await createIngress(backend)(contextOf(get("/v1/session")));

    expect(answer).toBe(answerOfBackend);
    expect(backend.fetch).toHaveBeenCalledTimes(1);
  });
});

describe("The ingress, when backend does not answer in time (ADR-0016, statement 4)", () => {
  it("answers 504 with an empty body at the caller's timeout of the contract, once", async () => {
    vi.useFakeTimers();
    const backend = createFakeBackend(waitForAbort);
    const answer = trackSettled(createIngress(backend)(contextOf(get("/v1/session"))));

    await vi.advanceTimersByTimeAsync(CONTRACT_TIMEOUT_MS - 1);
    expect(answer.isSettled()).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    const response = await answer.promise;
    expect(response.status).toBe(504);
    expect(await response.text()).toBe("");
    expect(backend.fetch).toHaveBeenCalledTimes(1);
  });

  it("waits as long as SUPPORTIQ_BACKEND_TIMEOUT_MS says", async () => {
    vi.useFakeTimers();
    const env = { ...settings, SUPPORTIQ_BACKEND_TIMEOUT_MS: "2500" };
    const answer = trackSettled(
      createIngress(createFakeBackend(waitForAbort))(contextOf(get("/v1/session"), env)),
    );

    await vi.advanceTimersByTimeAsync(2499);
    expect(answer.isSettled()).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    expect((await answer.promise).status).toBe(504);
  });
});

describe("The ingress, a body that streams after the headers (ADR-0016, statement 4)", () => {
  it("passes the whole body through, though it ends after the timeout", async () => {
    vi.useFakeTimers();
    const stream = createControlledStream();
    const backend = createFakeBackend((request) => {
      // As the fetch of the runtime does, an abort of the request cuts the body that streams.
      request.signal.addEventListener("abort", () => {
        stream.cut();
      });
      return Promise.resolve(new Response(stream.readable, { status: 200 }));
    });

    const answer = await createIngress(backend)(contextOf(get("/v1/session")));
    await vi.advanceTimersByTimeAsync(CONTRACT_TIMEOUT_MS * 2);
    stream.finish("the late part");

    expect(answer.status).toBe(200);
    expect(await answer.text()).toBe("the late part");
  });
});

describe("The ingress, a client that goes away (ADR-0022, statement 8)", () => {
  it("cancels the request to backend when the client cancels its request", async () => {
    const client = new AbortController();
    const forwarded = Promise.withResolvers<Request>();
    const backend = createFakeBackend((backendRequest) => {
      forwarded.resolve(backendRequest);
      return waitForAbort(backendRequest);
    });
    const request = new Request(`${PAGES_ORIGIN}/v1/session`, { signal: client.signal });

    const answer = createIngress(backend)(contextOf(request));
    const backendRequest = await forwarded.promise;
    client.abort();
    await answer;

    expect(backendRequest.signal.aborted).toBe(true);
  });
});

describe("The ingress, the body limit (ADR-0016, statement 5)", () => {
  it("refuses a body over 64 KiB with 413 before it forwards anything", async () => {
    const backend = createFakeBackend(() => Promise.resolve(new Response(null)));
    const request = post("/v1/shop/tickets", new Uint8Array(MAX_BODY_BYTES + 1));

    const answer = await createIngress(backend)(contextOf(request));

    expect(answer.status).toBe(413);
    expect(await answer.text()).toBe("");
    expect(backend.fetch).not.toHaveBeenCalled();
  });

  it("refuses a chunked body over 64 KiB, which declares no length, with 413", async () => {
    const backend = createFakeBackend(() => Promise.resolve(new Response(null)));
    const request = post("/v1/shop/tickets", streamOf([40_000, 40_000]));

    const answer = await createIngress(backend)(contextOf(request));

    expect(request.headers.get("content-length")).toBeNull();
    expect(answer.status).toBe(413);
    expect(backend.fetch).not.toHaveBeenCalled();
  });

  it("forwards a body of exactly 64 KiB, sent in chunks", async () => {
    const backend = createFakeBackend(() => Promise.resolve(new Response(null, { status: 201 })));
    const request = post("/v1/shop/tickets", streamOf([MAX_BODY_BYTES - 1, 1]));

    await createIngress(backend)(contextOf(request));

    expect((await backend.received(0).arrayBuffer()).byteLength).toBe(MAX_BODY_BYTES);
  });
});

describe("The ingress, its logs (ADR-0016, statement 6)", () => {
  it("logs nothing about a request, whatever the outcome", async () => {
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((method) =>
      vi.spyOn(console, method),
    );
    const answerOk = () => Promise.resolve(new Response(null, { status: 200 }));
    const failToConnect = () => Promise.reject(new TypeError("fetch failed"));
    const tooLarge = post("/v1/shop/tickets", new Uint8Array(MAX_BODY_BYTES + 1));

    await createIngress(createFakeBackend(answerOk))(contextOf(get("/v1/session")));
    await createIngress(createFakeBackend(failToConnect))(contextOf(get("/v1/session")));
    await createIngress(createFakeBackend(answerOk))(contextOf(tooLarge));
    await expect(
      createIngress(createFakeBackend(waitForAbort))(contextOf(get("/v1/session"), {})),
    ).rejects.toThrow(InvalidSettingError);

    for (const spy of consoleSpies) {
      expect(spy).not.toHaveBeenCalled();
    }
  });
});

describe("The ingress, its settings (ARCH-34, CODE-39)", () => {
  it.each([
    ["missing", undefined],
    ["not a URL", "backend"],
    ["http", "http://backend.example.test"],
    ["with a path", "https://backend.example.test/v1"],
    ["with a trailing slash", "https://backend.example.test/"],
  ])("refuses a backend URL that is %s, and forwards nothing", async (_case, value) => {
    const backend = createFakeBackend(waitForAbort);
    const env = value === undefined ? {} : { SUPPORTIQ_BACKEND_URL: value };

    const answer = createIngress(backend)(contextOf(get("/v1/session"), env));

    await expect(answer).rejects.toBeInstanceOf(InvalidSettingError);
    await expect(answer).rejects.toThrow("SUPPORTIQ_BACKEND_URL must be");
    expect(backend.fetch).not.toHaveBeenCalled();
  });

  it.each(["0", "-5", "1.5", "ten"])(
    "refuses the timeout %j, and forwards nothing",
    async (raw) => {
      const backend = createFakeBackend(waitForAbort);
      const env = { ...settings, SUPPORTIQ_BACKEND_TIMEOUT_MS: raw };

      await expect(createIngress(backend)(contextOf(get("/v1/session"), env))).rejects.toThrow(
        "SUPPORTIQ_BACKEND_TIMEOUT_MS must be an integer of at least 1.",
      );
      expect(backend.fetch).not.toHaveBeenCalled();
    },
  );
});

describe("onRequest", () => {
  it("sends the request with the fetch of the runtime", async () => {
    const answerOfBackend = new Response(null, { status: 204 });
    const runtimeFetch = vi.fn(() => Promise.resolve(answerOfBackend));
    vi.stubGlobal("fetch", runtimeFetch);

    const answer = await onRequest(contextOf(get("/health/live")));

    expect(answer).toBe(answerOfBackend);
    expect(runtimeFetch).toHaveBeenCalledTimes(1);
  });
});

/**
 * Create a fake `backend` behind a fake fetch, which keeps every request it receives.
 *
 * @param answer - How the fake answers a request.
 * @returns The fetch, and the requests it received.
 */
function createFakeBackend(answer: (request: Request) => Promise<Response>) {
  const requests: Request[] = [];
  const fetch = vi.fn((request: Request) => {
    requests.push(request);
    return answer(request);
  });
  return {
    fetch,
    received(index: number): Request {
      const request = requests[index];
      if (request === undefined) {
        throw new Error(`backend received no request ${String(index)}.`);
      }
      return request;
    },
  };
}

/**
 * Answer as the fetch of the runtime does when `backend` never sends its headers: it fails once
 * the request is aborted.
 *
 * @param request - The request to `backend`.
 * @returns A promise that rejects when the request is aborted.
 */
function waitForAbort(request: Request): Promise<Response> {
  return new Promise((_resolve, reject) => {
    request.signal.addEventListener("abort", () => {
      reject(new DOMException("The operation was aborted.", "AbortError"));
    });
  });
}

/**
 * Follow whether a promise has settled, so a test can check that an answer is still pending.
 *
 * @param promise - The answer of the ingress.
 * @returns The promise and whether it has settled.
 */
function trackSettled(promise: Promise<Response>) {
  let isSettled = false;
  void promise.finally(() => {
    isSettled = true;
  });
  return { promise, isSettled: () => isSettled };
}

/**
 * Create a body that the test ends, or that an abort cuts.
 *
 * @returns The stream, and how to end it or cut it.
 */
function createControlledStream() {
  let controller: ReadableStreamDefaultController<Uint8Array> | undefined;
  const readable = new ReadableStream<Uint8Array>({
    start(streamController) {
      controller = streamController;
    },
  });
  return {
    readable,
    finish(text: string) {
      controller?.enqueue(new TextEncoder().encode(text));
      controller?.close();
    },
    cut() {
      controller?.error(new DOMException("The operation was aborted.", "AbortError"));
    },
  };
}

/**
 * Create a chunked body of the given chunk sizes.
 *
 * @param sizes - The size of each chunk in bytes.
 * @returns The stream.
 */
function streamOf(sizes: readonly number[]): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const size of sizes) {
        controller.enqueue(new Uint8Array(size));
      }
      controller.close();
    },
  });
}

/**
 * Create a `GET` request of the browser to the Pages origin.
 *
 * @param path - The path and query.
 * @returns The request.
 */
function get(path: string): Request {
  return new Request(`${PAGES_ORIGIN}${path}`, { headers: { Origin: PAGES_ORIGIN } });
}

/**
 * Create a `POST` request of the browser to the Pages origin.
 *
 * @param path - The path.
 * @param body - The body: bytes, or a stream that declares no length.
 * @returns The request.
 */
function post(path: string, body: Uint8Array<ArrayBuffer> | ReadableStream<Uint8Array>): Request {
  // The fetch API needs `duplex` for a body that streams; the DOM types do not list it yet.
  const init: RequestInit & { readonly duplex: "half" } = {
    method: "POST",
    headers: { Origin: PAGES_ORIGIN },
    body,
    duplex: "half",
  };
  return new Request(`${PAGES_ORIGIN}${path}`, init);
}

/**
 * Build what Pages passes to the Function.
 *
 * @param request - The request of the browser.
 * @param env - The settings of the Pages project.
 * @returns The context.
 */
function contextOf(request: Request, env: IngressContext["env"] = settings): IngressContext {
  return { request, env };
}

/**
 * The one configured `backend` client of frontend (TS-05, TS-27).
 *
 * The client is generated from `contracts/backend.openapi.yaml` and created once by the
 * composition root (ARCH-21), which hands it to the feature `api/` layers through
 * {@link BackendClientContext}. Only those layers call it (TS-28).
 */
import createClient, { type Client } from "openapi-fetch";
import { createContext, use } from "react";

import type { paths } from "@/api/generated/backend";

/** Holds the client that the composition root created. */
export const BackendClientContext = createContext<BackendClient | null>(null);

/** The typed client of every `backend` operation. */
export type BackendClient = Client<paths>;

/** What the composition root and the tests pass to {@link createBackendClient}. */
export type BackendClientOptions = {
  /** The origin of `backend`, which is the page's origin (ADR-0009, same-site cookie). */
  readonly baseUrl: string;
  /** How long frontend waits for a response, from the setting `VITE_REQUEST_TIMEOUT_MS`. */
  readonly requestTimeoutMs: number;
  /** The fetch implementation. Tests pass a fake that answers with contract examples. */
  readonly fetch: (request: Request) => Promise<Response>;
};

/** Thrown when `backend` does not answer within the request timeout (ERR-09). */
export class RequestTimeoutError extends Error {
  override readonly name = "RequestTimeoutError";

  /**
   * @param timeoutMs - The timeout that elapsed.
   */
  constructor(readonly timeoutMs: number) {
    super(`No response within ${String(timeoutMs)} ms.`);
  }
}

/**
 * Create the `backend` client.
 *
 * @param options - The base URL, the request timeout, and the fetch implementation.
 * @returns The typed client.
 */
export function createBackendClient(options: BackendClientOptions): BackendClient {
  return createClient<paths>({
    baseUrl: options.baseUrl,
    fetch: withRequestTimeout(options),
  });
}

/**
 * Read the `backend` client in a feature `api/` hook.
 *
 * @returns The client of the nearest {@link BackendClientContext}.
 * @throws Error when no composition root provided a client, which is a wiring defect.
 */
export function useBackendClient(): BackendClient {
  const client = use(BackendClientContext);
  if (client === null) {
    throw new Error("No backend client: wrap the app in BackendClientContext.");
  }
  return client;
}

/**
 * Wait until a signal aborts.
 *
 * @param signal - The signal of the request.
 * @returns A promise that resolves when the signal aborts.
 */
function waitForAbort(signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    signal.addEventListener(
      "abort",
      () => {
        resolve();
      },
      { once: true },
    );
  });
}

/**
 * Read the whole body of a response while the timeout runs, so that a body that stops arriving
 * cannot keep a screen waiting.
 *
 * @param response - The response, with its body not read yet.
 * @param signal - The signal of the request.
 * @returns A copy of the response that holds the whole body.
 * @throws The reason of the abort when the signal aborts first.
 */
async function readWholeResponse(response: Response, signal: AbortSignal): Promise<Response> {
  signal.throwIfAborted();
  const body = await Promise.race([response.arrayBuffer(), waitForAbort(signal)]);
  signal.throwIfAborted();
  return new Response(body === undefined || body.byteLength === 0 ? null : body, response);
}

/**
 * Wrap a fetch implementation so that each request stops after the timeout (ERR-09).
 *
 * The timeout covers the whole response, up to the end of its body. The caller's own abort signal,
 * such as the one TanStack Query passes on cancellation, still works.
 *
 * @param options - The fetch implementation and the timeout.
 * @returns A fetch function that rejects with {@link RequestTimeoutError} after the timeout.
 */
function withRequestTimeout(
  options: Pick<BackendClientOptions, "fetch" | "requestTimeoutMs">,
): (request: Request) => Promise<Response> {
  return async (request) => {
    const timeoutController = new AbortController();
    const timer = setTimeout(() => {
      timeoutController.abort(new RequestTimeoutError(options.requestTimeoutMs));
    }, options.requestTimeoutMs);
    const signal = AbortSignal.any([request.signal, timeoutController.signal]);
    try {
      const response = await options.fetch(new Request(request, { signal }));
      return await readWholeResponse(response, signal);
    } finally {
      clearTimeout(timer);
    }
  };
}

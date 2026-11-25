/**
 * The ingress of the demo deployment: the Pages Function of `/v1/*` and `/health/*` (ADR-0016,
 * statements 2 to 6; ADR-0011, Ingress). It forwards each request to `backend` and returns the
 * answer unchanged. It answers by itself only with `413`, `502`, or `504`, with an empty body,
 * because these answers are not part of the contract. It runs on the Workers runtime, so it imports
 * nothing.
 */

/** ADR-0011, Ingress: the largest request body, 64 KiB. */
const MAX_BODY_BYTES = 65_536;

/** The backend contract, section Timeouts: the caller's timeout, in ms. */
const DEFAULT_TIMEOUT_MS = 10_000;

const BACKEND_URL_SETTING = "SUPPORTIQ_BACKEND_URL";
const BACKEND_TIMEOUT_SETTING = "SUPPORTIQ_BACKEND_TIMEOUT_MS";

/** Thrown when a setting of the Function is missing or invalid, with the setting's name. */
export class InvalidSettingError extends Error {
  override readonly name = "InvalidSettingError";
}

/** What Pages passes to the Function: the request and the settings of the project. */
export type IngressContext = {
  readonly request: Request;
  readonly env: Readonly<Record<string, unknown>>;
};

/**
 * Create the Function.
 *
 * @param runtime - The fetch of the Workers runtime; tests pass a fake.
 * @returns The Function.
 */
export function createIngress(runtime: {
  readonly fetch: (request: Request) => Promise<Response>;
}) {
  return async ({ request, env }: IngressContext): Promise<Response> => {
    const backendOrigin = parseBackendOrigin(env[BACKEND_URL_SETTING]);
    const timeoutMs = parseTimeoutMs(env[BACKEND_TIMEOUT_SETTING]);
    const body = await readBody(request);
    if (body === "too_large") {
      return new Response(null, { status: 413 });
    }
    const { pathname, search } = new URL(request.url);
    const controller = new AbortController();
    // The timer bounds only the wait for the response headers, so a body that streams is never cut.
    const timer = setTimeout(() => {
      controller.abort();
    }, timeoutMs);
    try {
      return await runtime.fetch(
        new Request(`${backendOrigin}${pathname}${search}`, {
          method: request.method,
          headers: request.headers,
          body,
          redirect: "manual",
          // A client that goes away, such as a closed stream, cancels the request (ADR-0022, 8).
          signal: AbortSignal.any([request.signal, controller.signal]),
        }),
      );
    } catch {
      // The failure is the answer, and nothing about the request is logged (statements 4 and 6).
      return new Response(null, { status: controller.signal.aborted ? 504 : 502 });
    } finally {
      clearTimeout(timer);
    }
  };
}

/** The Function of the deployment. */
export const onRequest = createIngress({ fetch: (request) => fetch(request) });

/**
 * Read the `backend` origin, such as `https://<service>.onrender.com` (SEC-28).
 *
 * @param raw - The value of the setting.
 * @returns The origin.
 * @throws InvalidSettingError unless the value is an https origin without a path.
 */
function parseBackendOrigin(raw: unknown): string {
  if (typeof raw === "string" && URL.canParse(raw)) {
    const url = new URL(raw);
    if (url.protocol === "https:" && url.origin === raw) {
      return raw;
    }
  }
  throw new InvalidSettingError(
    `${BACKEND_URL_SETTING} must be an https origin without a path, such as https://host.`,
  );
}

/**
 * Read the timeout.
 *
 * @param raw - The value of the setting.
 * @returns The timeout in ms, or the caller's timeout of the contract when the setting is not set.
 * @throws InvalidSettingError when the value is not an integer of at least 1.
 */
function parseTimeoutMs(raw: unknown): number {
  if (raw === undefined || raw === "") {
    return DEFAULT_TIMEOUT_MS;
  }
  const value = typeof raw === "string" ? Number(raw) : Number.NaN;
  if (!Number.isInteger(value) || value < 1) {
    throw new InvalidSettingError(`${BACKEND_TIMEOUT_SETTING} must be an integer of at least 1.`);
  }
  return value;
}

/**
 * Read the body, and stop as soon as it is larger than the limit. The bytes are counted as they
 * arrive, because a chunked body declares no length.
 *
 * @param request - The request.
 * @returns The bytes, null without a body, or `too_large`.
 */
async function readBody(request: Request): Promise<ArrayBuffer | null | "too_large"> {
  if (request.body === null) {
    return null;
  }
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  for await (const chunk of request.body) {
    size += chunk.byteLength;
    if (size > MAX_BODY_BYTES) {
      return "too_large";
    }
    chunks.push(chunk);
  }
  return new Blob(chunks).arrayBuffer();
}

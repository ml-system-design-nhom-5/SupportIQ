/**
 * The wake request of the backend wake-up design: one `GET /health/live` straight to the Render
 * origin of `backend`, so that a free instance that stopped starts again. It is the only code that
 * calls that origin (rule 8, TS-28).
 */
import type { paths } from "@/api/generated/backend";

/** The path of `checkLiveness` in the backend contract (rule 1). */
const LIVENESS_PATH = "/health/live" satisfies keyof paths;

/** What the wake request needs. */
export type BackendWakerOptions = {
  /** The Render origin of `backend`; undefined when no wake request is sent (rule 9). */
  readonly origin: string | undefined;
  /** How long a wake request may wait, in ms (rule 6). */
  readonly timeoutMs: number;
  readonly fetch: (request: Request) => Promise<Response>;
};

/**
 * Send a wake request, unless one is in flight (rule 5). Returns a promise that settles once the
 * request has ended, never rejecting, or undefined when nothing was sent. Callers need not wait.
 */
export type WakeBackend = () => Promise<void> | undefined;

/**
 * Create the sender of wake requests.
 *
 * @param options - The Render origin, the wake timeout, and the fetch implementation.
 * @returns The sender, which sends nothing without an origin.
 */
export function createBackendWaker({ origin, timeoutMs, fetch }: BackendWakerOptions): WakeBackend {
  if (origin === undefined) {
    return () => undefined;
  }
  let isInFlight = false;
  return () => {
    if (isInFlight) {
      return undefined;
    }
    isInFlight = true;
    return sendWakeRequest(`${origin}${LIVENESS_PATH}`, timeoutMs, fetch).finally(() => {
      isInFlight = false;
    });
  };
}

/**
 * Send one wake request without a cookie, a referrer, a body, or a header (rule 2).
 *
 * @param url - The liveness URL on the Render origin.
 * @param timeoutMs - How long the request may wait.
 * @param fetch - The fetch implementation.
 * @returns A promise that settles when the request has ended, however it ended.
 */
async function sendWakeRequest(
  url: string,
  timeoutMs: number,
  fetch: BackendWakerOptions["fetch"],
): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, timeoutMs);
  try {
    await fetch(
      new Request(url, {
        method: "GET",
        mode: "no-cors",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        signal: controller.signal,
      }),
    );
  } catch {
    // Rule 3 of the backend wake-up design: frontend never acts on the wake request or shows
    // anything about it, so a failed, blocked, or timed-out one is ignored, and the next trigger
    // sends a new one. This is not an error swallowed against ERR-04: a failure that the person
    // needs to see already shows through the request that failed.
  } finally {
    clearTimeout(timer);
  }
}

/**
 * When a request is sent again automatically (ERR-12, ERR-13, TS-29).
 *
 * Only timeouts, lost connections, rate limits, `502`, `503`, and `504` are retried, a bounded
 * number of times, with exponential backoff and jitter. `4xx` answers, `413` included, and `500`
 * are never retried. Sign-in, sign-out, and every write without an `Idempotency-Key` never use
 * this policy.
 */
import { assertNever } from "@/features/backend-requests/model/assert-never";
import {
  getRequestFailure,
  type RequestFailure,
} from "@/features/backend-requests/model/request-failure";

const retryableIngressStatuses: ReadonlySet<number> = new Set([429, 502, 503, 504]);
/** Each retry waits twice as long as the one before. */
const BACKOFF_FACTOR = 2;
/** Jitter keeps between half and all of the computed delay, so clients do not retry together. */
const JITTER_MINIMUM_SHARE = 0.5;

/**
 * Tell whether a failure may be retried (ERR-12).
 *
 * @param failure - The parsed failure.
 * @returns True for a timeout, a lost connection, `429`, `502`, `503`, or `504`.
 */
export function isRetryableFailure(failure: RequestFailure): boolean {
  switch (failure.kind) {
    case "network":
    case "timeout":
      return true;
    case "ingress":
      return retryableIngressStatuses.has(failure.status);
    case "problem":
      return failure.problemType === "not_ready";
    case "invalid_response":
      return false;
    default:
      assertNever(failure);
  }
}

/**
 * Decide whether TanStack Query sends a failed request again.
 *
 * @param failureCount - How many retries were already sent: 0 after the first attempt failed.
 * @param error - The error of the last attempt.
 * @param maxRetryCount - The bound from the settings.
 * @returns True when the failure is retryable and the bound is not reached.
 */
export function shouldRetryRequest(
  failureCount: number,
  error: unknown,
  maxRetryCount: number,
): boolean {
  const failure = getRequestFailure(error);
  return failure !== undefined && isRetryableFailure(failure) && failureCount < maxRetryCount;
}

/**
 * Compute the wait before a retry: exponential backoff with jitter (ERR-13).
 *
 * @param attemptIndex - 0 for the first retry, 1 for the second, and so on.
 * @param baseDelayMs - The first delay, from the settings.
 * @param randomShare - A number in [0, 1) from the caller's random source.
 * @returns The delay in milliseconds.
 */
export function computeRetryDelayMs(
  attemptIndex: number,
  baseDelayMs: number,
  randomShare: number,
): number {
  const backoffMs = baseDelayMs * BACKOFF_FACTOR ** attemptIndex;
  return Math.round(backoffMs * (JITTER_MINIMUM_SHARE + (1 - JITTER_MINIMUM_SHARE) * randomShare));
}

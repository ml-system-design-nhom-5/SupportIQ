/**
 * Every way a `backend` request can fail, parsed once at the boundary (CODE-32).
 *
 * `backend` answers errors with Problem Details (CON-12). The ingress can answer `413`, `429`,
 * `502`, or `504` with a body that is not Problem Details (contracts v1 design, Common elements).
 * The browser reports a lost connection, and the client reports a timeout (ERR-09).
 */
import { assertNever } from "@/features/backend-requests/model/assert-never";

/** The problem types of a write that `backend` looked at and refused. */
const problemTypesOfRefusals: ReadonlySet<ProblemType> = new Set([
  "invalid_request",
  "not_found",
  "login_name_taken",
]);

/** The statuses of a write in flight that the ingress lost (ADR-0011). */
const unknownOutcomeStatuses: ReadonlySet<number> = new Set([502, 504]);

const problemTypeByUrn: ReadonlyMap<string, ProblemType> = new Map([
  ["urn:supportiq:problem:invalid-request", "invalid_request"],
  ["urn:supportiq:problem:unauthenticated", "unauthenticated"],
  ["urn:supportiq:problem:forbidden", "forbidden"],
  ["urn:supportiq:problem:not-found", "not_found"],
  ["urn:supportiq:problem:idempotency-key-reused", "idempotency_key_reused"],
  ["urn:supportiq:problem:login-name-taken", "login_name_taken"],
  ["urn:supportiq:problem:not-ready", "not_ready"],
  ["urn:supportiq:problem:internal-error", "internal_error"],
]);

const traceIdPattern = /^[0-9a-f]{32}$/;

/** The problem types of the `backend` contract, and `unknown` for a type it does not list. */
export type ProblemType =
  | "invalid_request"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "idempotency_key_reused"
  | "login_name_taken"
  | "not_ready"
  | "internal_error"
  | "unknown";

/** A failed request, discriminated by `kind` (TS-12). */
export type RequestFailure = (
  | {
      readonly kind: "problem";
      readonly status: number;
      readonly problemType: ProblemType;
      readonly traceId?: string;
      readonly violatedRule?: string;
    }
  | { readonly kind: "ingress"; readonly status: number }
  | { readonly kind: "network" }
  | { readonly kind: "timeout" }
  | { readonly kind: "invalid_response" }
) & {
  /** True when an earlier attempt with the same key had an unknown outcome. */
  readonly isAfterUnknownOutcome?: true;
};

/** The members of a Problem Details body that frontend reads. */
type ProblemDetailsBody = {
  readonly type: string;
  readonly title: string;
  readonly trace_id?: unknown;
  readonly violated_rule?: unknown;
};

/**
 * Tell whether a write may have happened although it failed. The caller stopped waiting, or lost
 * the answer, while `backend` may still finish it (contract, Timeouts), or `backend` said that it
 * worked in a body that cannot be read. The UI then never says that it did not happen.
 *
 * @param failure - The failure of a write.
 * @returns True for a timeout, a lost connection, `502`, `504`, a `2xx` with an unreadable body,
 *   and any failure that follows one of these with the same key.
 */
export function isWriteOutcomeUnknown(failure: RequestFailure): boolean {
  if (failure.isAfterUnknownOutcome === true) {
    return true;
  }
  switch (failure.kind) {
    case "timeout":
    case "network":
    case "invalid_response":
      return true;
    case "ingress":
    case "problem":
      return unknownOutcomeStatuses.has(failure.status);
    default:
      assertNever(failure);
  }
}

/**
 * Tell whether `backend` looked at a write and refused it. `backend` remembers only a success, and
 * it answers a repeated key with that success (contract, `Idempotency-Key`), so these answers also
 * mean that no earlier attempt with the key succeeded. `409 login-name-taken` comes after the key
 * is claimed (account management design, Creating an account). `401`, `403`, and
 * `409 idempotency-key-reused` do not: they come before `backend` reads the key, or they say that
 * the key was used.
 *
 * @param failure - The failure of a write.
 * @returns True for `422 invalid-request`, `404 not-found`, and `409 login-name-taken`.
 */
export function isRefusedByBackend(failure: RequestFailure): boolean {
  return failure.kind === "problem" && problemTypesOfRefusals.has(failure.problemType);
}

/** Carries a {@link RequestFailure} through TanStack Query, which needs a thrown error. */
export class RequestFailureError extends Error {
  override readonly name = "RequestFailureError";

  /**
   * @param failure - The parsed failure.
   * @param options - The original error, kept as the cause (CODE-40).
   */
  constructor(
    readonly failure: RequestFailure,
    options?: ErrorOptions,
  ) {
    super(`The backend request failed: ${failure.kind}.`, options);
  }
}

/**
 * Map a problem type URN to a {@link ProblemType}.
 *
 * @param urn - The `type` member of a Problem Details body.
 * @returns The problem type, or `unknown` for a value the contract does not list (CON-22).
 */
export function toProblemType(urn: string): ProblemType {
  return problemTypeByUrn.get(urn) ?? "unknown";
}

/**
 * Parse the body of a failed response.
 *
 * @param status - The HTTP status of the response.
 * @param body - The body as openapi-fetch read it: parsed JSON, text, or undefined.
 * @returns A `problem` failure for a Problem Details body, otherwise an `ingress` failure.
 */
export function parseFailureResponse(status: number, body: unknown): RequestFailure {
  if (!isProblemDetailsBody(body)) {
    return { kind: "ingress", status };
  }
  const traceId = body.trace_id;
  const violatedRule = body.violated_rule;
  return {
    kind: "problem",
    status,
    problemType: toProblemType(body.type),
    ...(typeof traceId === "string" && traceIdPattern.test(traceId) ? { traceId } : {}),
    ...(typeof violatedRule === "string" ? { violatedRule } : {}),
  };
}

/**
 * Read the failure carried by an error.
 *
 * @param error - Any thrown value.
 * @returns The failure, or undefined when the error is not a {@link RequestFailureError}.
 */
export function getRequestFailure(error: unknown): RequestFailure | undefined {
  return error instanceof RequestFailureError ? error.failure : undefined;
}

/**
 * Tell whether an error means that the session is missing or expired (`401`).
 *
 * @param error - Any thrown value.
 * @returns True for a Problem Details `unauthenticated` failure.
 */
export function isUnauthenticatedError(error: unknown): boolean {
  const failure = getRequestFailure(error);
  return failure?.kind === "problem" && failure.problemType === "unauthenticated";
}

/**
 * Tell whether a response body is Problem Details (RFC 9457): an object with a string `type` and
 * a string `title`.
 *
 * @param body - The parsed body.
 * @returns True for a Problem Details body.
 */
function isProblemDetailsBody(body: unknown): body is ProblemDetailsBody {
  return (
    typeof body === "object" &&
    body !== null &&
    "type" in body &&
    typeof body.type === "string" &&
    "title" in body &&
    typeof body.title === "string"
  );
}

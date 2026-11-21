/**
 * A fake `backend` for component and feature tests: a fetch function that answers each request
 * with the `value` of a contract example file (TEST-11), records every request, and can simulate
 * the ingress, a lost connection, a missing answer (ERR-21), and an answer that a test holds back.
 */
import { assertNever } from "@/features/backend-requests";
import { readExample } from "@/test/contract-examples";

/** The HTML body of an Nginx error page: what the ingress sends instead of Problem Details. */
const INGRESS_ERROR_BODY = "<html><body><h1>Error</h1><p>nginx</p></body></html>";

const NO_CONTENT_STATUS = 204;

const FIRST_ERROR_STATUS = 400;

/** The `204` answer of an operation without a body. */
export const noContentAnswer: FakeAnswer = { kind: "no_content", status: NO_CONTENT_STATUS };

/** An HTTP method of the backend contract. */
export type FakeMethod = "GET" | "POST" | "DELETE";

/** Which requests an answer is for: a method and an exact path, or a path pattern. */
export type FakeRoute = {
  readonly method: FakeMethod;
  readonly path: string | RegExp;
};

/** What the fake backend answers at once. */
type ImmediateAnswer =
  | {
      readonly kind: "example";
      readonly status: number;
      readonly folder: string;
      readonly name: string;
    }
  | { readonly kind: "body"; readonly status: number; readonly body: unknown }
  | { readonly kind: "no_content"; readonly status: number }
  | { readonly kind: "ingress"; readonly status: number }
  | { readonly kind: "network_error" }
  | { readonly kind: "no_answer" };

/** What the fake backend answers, at once or when a test releases it. */
export type FakeAnswer =
  | ImmediateAnswer
  | { readonly kind: "held"; readonly answer: ImmediateAnswer; readonly released: Promise<void> };

/** An answer that waits until a test releases it. */
type HeldAnswer = {
  readonly answer: FakeAnswer;
  readonly release: () => void;
};

/** A request that the app sent. */
export type RecordedRequest = {
  readonly method: string;
  readonly path: string;
  readonly searchParams: URLSearchParams;
  readonly headers: Headers;
  /** The parsed JSON body, or undefined without a body. */
  readonly body: unknown;
};

/** The fake backend of one test. */
export type FakeBackend = {
  /** The fetch function to give to the app's composition root. */
  readonly fetch: (request: Request) => Promise<Response>;
  /**
   * Register answers for a route. The answers are used in order, and the last one repeats.
   * A later registration for the same route wins.
   */
  readonly answer: (route: FakeRoute, ...answers: readonly FakeAnswer[]) => void;
  /** Every request so far, in order. */
  readonly requests: readonly RecordedRequest[];
  /** The requests to one route, in order. */
  readonly requestsTo: (route: FakeRoute) => readonly RecordedRequest[];
};

/**
 * Create a fake backend.
 *
 * @returns The fake, without any answer yet: an unexpected request fails the test.
 */
export function createFakeBackend(): FakeBackend {
  const registrations: { route: FakeRoute; answers: FakeAnswer[] }[] = [];
  const requests: RecordedRequest[] = [];

  const fetch = async (request: Request): Promise<Response> => {
    const url = new URL(request.url);
    requests.push({
      method: request.method,
      path: url.pathname,
      searchParams: url.searchParams,
      headers: request.headers,
      body: await readJsonBody(request),
    });
    const registration = registrations.findLast(({ route }) =>
      isRouteMatch(route, request.method, url.pathname),
    );
    const answer = registration?.answers[0];
    if (registration === undefined || answer === undefined) {
      throw new Error(`The fake backend has no answer for ${request.method} ${url.pathname}.`);
    }
    if (registration.answers.length > 1) {
      registration.answers.shift();
    }
    return answerWhenReleased(answer, request);
  };

  return {
    fetch,
    answer: (route, ...answers) => {
      registrations.push({ route, answers: [...answers] });
    },
    requests,
    requestsTo: (route) =>
      requests.filter((request) => isRouteMatch(route, request.method, request.path)),
  };
}

/**
 * Answer with an example file.
 *
 * @param status - The HTTP status of the example's response.
 * @param folder - The operation ID, or `problems`.
 * @param name - The example name.
 * @returns The answer.
 */
export function exampleAnswer(status: number, folder: string, name: string): ImmediateAnswer {
  return { kind: "example", status, folder, name };
}

/**
 * Hold an answer back, so that a test can act while the request waits.
 *
 * @param answer - The answer to give once it is released.
 * @returns The answer to register, and the function that releases it.
 */
export function holdAnswer(answer: ImmediateAnswer): HeldAnswer {
  const { promise, resolve } = Promise.withResolvers<undefined>();
  return {
    answer: { kind: "held", answer, released: promise },
    release: () => {
      resolve(undefined);
    },
  };
}

/**
 * Answer an example: Problem Details bodies with their media type, others as JSON.
 *
 * @param status - The HTTP status.
 * @param body - The body.
 * @returns The response.
 */
function toJsonResponse(status: number, body: unknown): Response {
  const contentType =
    status >= FIRST_ERROR_STATUS ? "application/problem+json" : "application/json";
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

/**
 * Wait until a request is aborted, like the browser's fetch when the server never answers.
 *
 * @param signal - The abort signal of the request.
 * @returns A promise that rejects with the abort reason.
 */
function waitForAbort(signal: AbortSignal): Promise<never> {
  const toError = (): Error => {
    const reason: unknown = signal.reason;
    return reason instanceof Error ? reason : new DOMException("Aborted", "AbortError");
  };
  return new Promise((_resolve, reject) => {
    if (signal.aborted) {
      reject(toError());
    }
    signal.addEventListener("abort", () => {
      reject(toError());
    });
  });
}

/**
 * Build the response of an answer, once a test released it when it is held.
 *
 * @param answer - The registered answer.
 * @param request - The request.
 * @returns The response, or a rejection like the browser's fetch.
 */
async function answerWhenReleased(answer: FakeAnswer, request: Request): Promise<Response> {
  if (answer.kind !== "held") {
    return toResponse(answer, request);
  }
  await answer.released;
  return toResponse(answer.answer, request);
}

/**
 * Build the response of an answer.
 *
 * @param answer - The answer.
 * @param request - The request, whose abort signal ends a `no_answer`.
 * @returns The response, or a rejection like the browser's fetch.
 */
async function toResponse(answer: ImmediateAnswer, request: Request): Promise<Response> {
  switch (answer.kind) {
    case "example":
    case "body":
      return toJsonResponse(
        answer.status,
        answer.kind === "body" ? answer.body : readExample(answer.folder, answer.name),
      );
    case "no_content":
      return new Response(null, { status: answer.status });
    case "ingress":
      return new Response(INGRESS_ERROR_BODY, {
        status: answer.status,
        headers: { "Content-Type": "text/html" },
      });
    case "network_error":
      throw new TypeError("Failed to fetch");
    case "no_answer":
      return waitForAbort(request.signal);
    default:
      assertNever(answer);
  }
}

/**
 * Tell whether a route matches a request.
 *
 * @param route - The registered route.
 * @param method - The request method.
 * @param path - The request path, without the query.
 * @returns True when the method and the path match.
 */
function isRouteMatch(route: FakeRoute, method: string, path: string): boolean {
  const isPathMatch = typeof route.path === "string" ? route.path === path : route.path.test(path);
  return route.method === method && isPathMatch;
}

/**
 * Read the JSON body of a request.
 *
 * @param request - The request.
 * @returns The parsed body, or undefined when it has none.
 */
async function readJsonBody(request: Request): Promise<unknown> {
  const text = await request.clone().text();
  return text === "" ? undefined : JSON.parse(text);
}

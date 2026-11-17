// Starts the Prism mock of each contract and checks what consumers rely on: the sign-in flow
// with the session cookie of backend, the service token and the closed request body of
// ai-service, and that Prism serves the example files unchanged.
// Run with `pnpm run check:mock` in contracts/ (README.md, Commands).
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { isDeepStrictEqual } from "node:util";

const STARTUP_TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 250;
const ALLOWED_ORIGIN = "http://localhost:5173";
const CUSTOMER_CREDENTIALS = { login_name: "customer-1", password: "not-a-real-password" };
const SESSION_COOKIE = /^(supportiq_session=[^;]+)/;
const EXAMPLE_ACCOUNT_ID = "c3e5a7b9-1d2f-4a6c-8e0b-2d4f6a8c0e14";
const SERVICE_TOKEN = "EXAMPLE-NOT-A-SERVICE-TOKEN";
const SUGGESTION_REQUEST = {
  message: "Where is the refund for order [ORDER_ID_1]?",
  as_of: "2026-11-05T08:12:30Z",
  order_context: { refund_status: "under_review" },
};

interface Check {
  readonly name: string;
  readonly run: (baseUrl: string) => Promise<void>;
}

interface Mock {
  readonly contract: string;
  readonly port: string;
  readonly checks: readonly Check[];
}

interface DraftCall {
  readonly token?: string;
  readonly prefer?: string;
  readonly body?: unknown;
}

const BACKEND_CHECKS: readonly Check[] = [
  {
    name: "sign-in: createSession sets supportiq_session; getCurrentSession is 401 without it and 200 with it",
    run: async (baseUrl) => {
      const cookie = await signIn(baseUrl);
      expectStatus(await fetch(`${baseUrl}/v1/sessions/current`), 401);
      const signedIn = await fetch(`${baseUrl}/v1/sessions/current`, {
        headers: { Cookie: cookie },
      });
      expectStatus(signedIn, 200);
    },
  },
  {
    name: "Prefer: example=refund-under-review serves examples/getShopOrder/refund-under-review.json",
    run: async (baseUrl) => {
      const response = await fetch(`${baseUrl}/v1/shop/orders/ORD-20931`, {
        headers: { Cookie: await signIn(baseUrl), Prefer: "example=refund-under-review" },
      });
      await expectExample(response, 200, "getShopOrder/refund-under-review.json");
    },
  },
  {
    name: "Prefer: code=422, example=last-active-manager serves examples/problems/last-active-manager.json",
    run: async (baseUrl) => {
      const response = await fetch(
        `${baseUrl}/v1/admin/accounts/${EXAMPLE_ACCOUNT_ID}/role-changes`,
        {
          method: "POST",
          headers: {
            Cookie: await signIn(baseUrl),
            "Content-Type": "application/json",
            "Idempotency-Key": randomUUID(),
            Origin: ALLOWED_ORIGIN,
            Prefer: "code=422, example=last-active-manager",
          },
          body: JSON.stringify({ role: "staff" }),
        },
      );
      await expectExample(response, 422, "problems/last-active-manager.json");
    },
  },
];

const AI_SERVICE_CHECKS: readonly Check[] = [
  {
    name: "service token: createDraft is 401 without Authorization and 200 with a bearer token",
    run: async (baseUrl) => {
      expectStatus(await createDraft(baseUrl, {}), 401);
      const authorized = await createDraft(baseUrl, { token: SERVICE_TOKEN });
      await expectExample(authorized, 200, "createDraft/draft-ready.json");
    },
  },
  {
    name: "Prefer: example=llm-unavailable serves examples/createDraft/llm-unavailable.json",
    run: async (baseUrl) => {
      const response = await createDraft(baseUrl, {
        token: SERVICE_TOKEN,
        prefer: "example=llm-unavailable",
      });
      await expectExample(response, 200, "createDraft/llm-unavailable.json");
    },
  },
  {
    name: "an order_context field outside the allow-list gets 422 (SEC-05)",
    run: async (baseUrl) => {
      const body = { ...SUGGESTION_REQUEST, order_context: { order_id: "ORD-20931" } };
      expectStatus(await createDraft(baseUrl, { token: SERVICE_TOKEN, body }), 422);
    },
  },
  {
    name: "Prefer: code=422, example=unknown-kb-version serves examples/problems/unknown-kb-version.json",
    run: async (baseUrl) => {
      const response = await createDraft(baseUrl, {
        token: SERVICE_TOKEN,
        prefer: "code=422, example=unknown-kb-version",
      });
      await expectExample(response, 422, "problems/unknown-kb-version.json");
    },
  },
];

const MOCKS: readonly Mock[] = [
  { contract: "backend.openapi.yaml", port: "4011", checks: BACKEND_CHECKS },
  { contract: "ai-service.openapi.yaml", port: "4013", checks: AI_SERVICE_CHECKS },
];

process.exitCode = await main();

async function main(): Promise<number> {
  let failures = 0;
  for (const mock of MOCKS) {
    failures += await checkMock(mock);
  }
  return failures === 0 ? 0 : 1;
}

async function checkMock(mock: Mock): Promise<number> {
  const prism = spawn(
    "prism",
    ["mock", "--host", "127.0.0.1", "--port", mock.port, mock.contract],
    {
      cwd: new URL("..", import.meta.url),
      stdio: "ignore",
    },
  );
  const baseUrl = `http://127.0.0.1:${mock.port}`;
  try {
    await waitUntilServing(baseUrl);
    return await runChecks(mock, baseUrl);
  } finally {
    prism.kill();
  }
}

async function runChecks(mock: Mock, baseUrl: string): Promise<number> {
  let failures = 0;
  for (const check of mock.checks) {
    const error = await check.run(baseUrl).then(
      () => undefined,
      (reason: unknown) => String(reason),
    );
    const name = `${mock.contract}: ${check.name}`;
    if (error === undefined) {
      console.log(`ok      ${name}`);
    } else {
      failures += 1;
      console.log(`FAILED  ${name}: ${error}`);
    }
  }
  return failures;
}

async function signIn(baseUrl: string): Promise<string> {
  const response = await fetch(`${baseUrl}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: ALLOWED_ORIGIN },
    body: JSON.stringify(CUSTOMER_CREDENTIALS),
  });
  expectStatus(response, 201);
  const setCookie = response.headers.get("set-cookie") ?? "";
  const cookie = SESSION_COOKIE.exec(setCookie)?.[1];
  if (cookie === undefined) {
    throw new Error(`no supportiq_session cookie in Set-Cookie: "${setCookie}"`);
  }
  return cookie;
}

async function createDraft(baseUrl: string, call: DraftCall): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (call.token !== undefined) {
    headers.Authorization = `Bearer ${call.token}`;
  }
  if (call.prefer !== undefined) {
    headers.Prefer = call.prefer;
  }
  return fetch(`${baseUrl}/v1/drafts`, {
    method: "POST",
    headers,
    body: JSON.stringify(call.body ?? SUGGESTION_REQUEST),
  });
}

function expectStatus(response: Response, expected: number): void {
  if (response.status !== expected) {
    throw new Error(`expected HTTP ${String(expected)}, got ${String(response.status)}`);
  }
}

async function expectExample(response: Response, status: number, path: string): Promise<void> {
  expectStatus(response, status);
  if (!isDeepStrictEqual(await response.json(), await exampleValue(path))) {
    throw new Error(`the body differs from the value of examples/${path}`);
  }
}

async function exampleValue(path: string): Promise<unknown> {
  const text = await readFile(new URL(`../examples/${path}`, import.meta.url), "utf8");
  const file: unknown = JSON.parse(text);
  return typeof file === "object" && file !== null && "value" in file ? file.value : undefined;
}

async function waitUntilServing(baseUrl: string): Promise<void> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const serving = await fetch(`${baseUrl}/health/live`).then(
      (response) => response.status === 204,
      () => false,
    );
    if (serving) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error(`Prism did not answer within ${String(STARTUP_TIMEOUT_MS)} ms`);
}

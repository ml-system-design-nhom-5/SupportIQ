// Starts the Prism mock of backend.openapi.yaml and checks what consumers rely on: the sign-in
// flow with the session cookie, and that Prism serves the example files unchanged.
// Run with `pnpm run check:mock` in contracts/ (README.md, Commands).
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { isDeepStrictEqual } from "node:util";

const PORT = "4011";
const BASE_URL = `http://127.0.0.1:${PORT}`;
const STARTUP_TIMEOUT_MS = 30_000;
const POLL_INTERVAL_MS = 250;
const ALLOWED_ORIGIN = "http://localhost:5173";
const CUSTOMER_CREDENTIALS = { login_name: "customer-1", password: "not-a-real-password" };
const SESSION_COOKIE = /^(supportiq_session=[^;]+)/;
const EXAMPLE_ACCOUNT_ID = "c3e5a7b9-1d2f-4a6c-8e0b-2d4f6a8c0e14";

interface Check {
  readonly name: string;
  readonly run: () => Promise<void>;
}

const checks: readonly Check[] = [
  {
    name: "sign-in: createSession sets supportiq_session; getCurrentSession is 401 without it and 200 with it",
    run: async () => {
      const cookie = await signIn();
      expectStatus(await fetch(`${BASE_URL}/v1/sessions/current`), 401);
      const signedIn = await fetch(`${BASE_URL}/v1/sessions/current`, {
        headers: { Cookie: cookie },
      });
      expectStatus(signedIn, 200);
    },
  },
  {
    name: "Prefer: example=refund-under-review serves examples/getShopOrder/refund-under-review.json",
    run: async () => {
      const response = await fetch(`${BASE_URL}/v1/shop/orders/ORD-20931`, {
        headers: { Cookie: await signIn(), Prefer: "example=refund-under-review" },
      });
      expectStatus(response, 200);
      const expected = await exampleValue("getShopOrder/refund-under-review.json");
      if (!isDeepStrictEqual(await response.json(), expected)) {
        throw new Error("the body differs from the value of the example file");
      }
    },
  },
  {
    name: "Prefer: code=422, example=last-active-manager serves examples/problems/last-active-manager.json",
    run: async () => {
      const response = await fetch(
        `${BASE_URL}/v1/admin/accounts/${EXAMPLE_ACCOUNT_ID}/role-changes`,
        {
          method: "POST",
          headers: {
            Cookie: await signIn(),
            "Content-Type": "application/json",
            "Idempotency-Key": randomUUID(),
            Origin: ALLOWED_ORIGIN,
            Prefer: "code=422, example=last-active-manager",
          },
          body: JSON.stringify({ role: "staff" }),
        },
      );
      expectStatus(response, 422);
      const expected = await exampleValue("problems/last-active-manager.json");
      if (!isDeepStrictEqual(await response.json(), expected)) {
        throw new Error("the body differs from the value of the example file");
      }
    },
  },
];

process.exitCode = await main();

async function main(): Promise<number> {
  const prism = spawn(
    "prism",
    ["mock", "--host", "127.0.0.1", "--port", PORT, "backend.openapi.yaml"],
    {
      cwd: new URL("..", import.meta.url),
      stdio: "ignore",
    },
  );
  try {
    await waitUntilServing();
    const failures = await runChecks();
    return failures === 0 ? 0 : 1;
  } finally {
    prism.kill();
  }
}

async function runChecks(): Promise<number> {
  let failures = 0;
  for (const check of checks) {
    const error = await check.run().then(
      () => undefined,
      (reason: unknown) => String(reason),
    );
    if (error === undefined) {
      console.log(`ok      ${check.name}`);
    } else {
      failures += 1;
      console.log(`FAILED  ${check.name}: ${error}`);
    }
  }
  return failures;
}

async function signIn(): Promise<string> {
  const response = await fetch(`${BASE_URL}/v1/sessions`, {
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

function expectStatus(response: Response, expected: number): void {
  if (response.status !== expected) {
    throw new Error(`expected HTTP ${String(expected)}, got ${String(response.status)}`);
  }
}

async function exampleValue(path: string): Promise<unknown> {
  const text = await readFile(new URL(`../examples/${path}`, import.meta.url), "utf8");
  const file: unknown = JSON.parse(text);
  return typeof file === "object" && file !== null && "value" in file ? file.value : undefined;
}

async function waitUntilServing(): Promise<void> {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const serving = await fetch(`${BASE_URL}/health/live`).then(
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

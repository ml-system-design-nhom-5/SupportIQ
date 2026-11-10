/**
 * The UI flow tests: Playwright against the production build and the Prism mock. These are not the
 * end-to-end tests across every component, which come later (TEST-27). Playwright starts both
 * servers. Automatic reruns stay off, so a flaky test fails (TEST-19).
 */
import { defineConfig, devices } from "@playwright/test";

// TODO(#6): package.json pins Playwright to 1.61.1 so that the browser tests run on macOS 13.
const PREVIEW_ORIGIN = "http://127.0.0.1:4173";
const MOCK_ORIGIN = "http://127.0.0.1:4010";
const SERVER_START_LIMIT_MS = 120_000;
/**
 * The longest flow signs in and runs axe four times. These bounds only stop a stuck flow: a step
 * ends as soon as its condition holds, so they keep a flow from failing on a loaded machine
 * (TEST-19).
 */
const FLOW_LIMIT_MS = 120_000;
const STEP_LIMIT_MS = 15_000;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: process.env["CI"] !== undefined,
  retries: 0,
  timeout: FLOW_LIMIT_MS,
  expect: { timeout: STEP_LIMIT_MS },
  reporter: "list",
  use: { baseURL: PREVIEW_ORIGIN },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } },
    },
    {
      // UI-33: the shop works from 360 px.
      name: "phone",
      use: { ...devices["Desktop Chrome"], viewport: { width: 360, height: 800 } },
      testMatch: "shop-*.spec.ts",
    },
  ],
  webServer: [
    {
      command: "pnpm --dir ../contracts run mock",
      url: `${MOCK_ORIGIN}/health/live`,
      reuseExistingServer: process.env["CI"] === undefined,
      timeout: SERVER_START_LIMIT_MS,
    },
    {
      command:
        "pnpm exec vite build && pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
      url: PREVIEW_ORIGIN,
      reuseExistingServer: process.env["CI"] === undefined,
      timeout: SERVER_START_LIMIT_MS,
    },
  ],
});

/**
 * The wake request in the production build (backend wake-up design, Testing and evaluation). The UI
 * flow build sets `VITE_BACKEND_WAKE_ORIGIN` to the Prism mock origin (playwright.config.ts), so
 * the page sends the wake request straight to the mock, outside the page's origin.
 */
import { expect, test } from "@playwright/test";

import { submitSignIn } from "./support/sign-in.ts";

/** `checkLiveness` on the wake origin of the UI flow build. */
const WAKE_URL = "http://127.0.0.1:4010/health/live";

test("the page sends the wake request when it starts, and the policy allows it", async ({
  page,
}) => {
  const policyViolations: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) {
      policyViolations.push(message.text());
    }
  });
  const wakeResponse = page.waitForResponse(WAKE_URL);

  await page.goto("/sign-in");

  expect((await wakeResponse).status()).toBe(204);
  expect(policyViolations).toEqual([]);
});

test("sign-in succeeds while the wake request gets no answer", async ({ page }) => {
  // The handler never answers, so the wake request waits, as it does while Render starts.
  await page.route(WAKE_URL, () => undefined);

  await page.goto("/sign-in");
  await submitSignIn(page);

  await expect(page).toHaveURL(/\/shop$/);
});

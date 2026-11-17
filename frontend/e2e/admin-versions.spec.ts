/**
 * The Versions screen against the Prism mock (admin UI design, Versions in use): an admin opens it
 * from the navigation and reads the versions of the example. The main failure is an `ai-service`
 * that `backend` cannot reach: the screen says so, shows its versions as unknown, and still shows
 * the build of `backend`. Another role sees the permission-denied state of the admin area.
 */
import { expect, type Page, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const getVersionsRequest = { method: "GET", path: "/v1/admin/versions" } as const;

/** The build of `backend` in both examples of `getAdminVersions`. */
const BACKEND_BUILD = "880b33a";

/** The versions of the example `ai-service-available`, in the order of the rows. */
const availableVersions = [
  "release-2026-11-12-sample",
  "intent-model-sample-1",
  "kb-sample-1",
  "mapping-sample-1",
  "prompts-sample-1",
  "routing-sample-1",
  "index-sample-1",
];

/** The value of each of those rows while `ai-service` cannot be reached. */
const unknownVersions = availableVersions.map(() => "Unknown");

/**
 * Sign in as the admin of the examples and open Versions from the navigation.
 *
 * @param page - The page.
 */
async function openVersionsFromNavigation(page: Page): Promise<void> {
  await preferOutcome(page, getSessionRequest, "example=admin");
  await createSessionCookie(page);
  await page.goto("/admin");
  await expect(page.getByRole("heading", { level: 1, name: "Accounts" })).toBeVisible();

  await page.getByRole("banner").getByRole("link", { name: "Versions" }).click();

  await expect(page).toHaveURL(/\/admin\/versions$/);
  await expect(page.getByRole("heading", { level: 1, name: "Versions in use" })).toBeVisible();
}

test("an admin opens Versions from the navigation and reads the versions in use", async ({
  page,
}) => {
  await openVersionsFromNavigation(page);

  const aiService = page.getByRole("region", { name: "ai-service" });
  await expect(aiService.getByText("Available")).toBeVisible();
  await expect(aiService.getByRole("definition")).toHaveText(availableVersions);
  await expect(page.getByRole("region", { name: "backend" }).getByRole("definition")).toHaveText([
    BACKEND_BUILD,
  ]);
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("banner").getByRole("link", { name: "Versions" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expectNoAccessibilityViolations(page);
});

test("an unreachable ai-service shows Unknown versions and still the backend build", async ({
  page,
}) => {
  await preferOutcome(page, getVersionsRequest, "example=ai-service-unavailable");
  await openVersionsFromNavigation(page);

  await expect(page.getByRole("alert")).toHaveText(
    "ai-service cannot be reached. Its versions are unknown. Reload this page later.",
  );
  const aiService = page.getByRole("region", { name: "ai-service" });
  await expect(aiService.getByText("Unavailable")).toBeVisible();
  await expect(aiService.getByRole("definition")).toHaveText(unknownVersions);
  await expect(page.getByRole("region", { name: "backend" }).getByRole("definition")).toHaveText([
    BACKEND_BUILD,
  ]);
  await expectNoAccessibilityViolations(page);
});

test("another role sees the permission-denied state on Versions", async ({ page }) => {
  await preferOutcome(page, getVersionsRequest, "code=403, example=forbidden-role");
  await createSessionCookie(page);

  await page.goto("/admin/versions");

  await expect(
    page.getByRole("heading", { level: 1, name: "The admin area is for admin accounts" }),
  ).toBeVisible();
  await expect(page.getByRole("main").getByRole("button", { name: "Sign out" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

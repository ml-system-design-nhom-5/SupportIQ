/**
 * The Reports page against the Prism mock (console UI design, Reports; UI-44): a manager opens it
 * from the navigation and reads the figures of the example with their targets. Staff have no link
 * to it, and at its address they see the permission-denied state without a report request. A
 * manager whom `backend` refuses with `403` sees the same state (UI-40). The mock is stateless, so
 * each flow chooses its examples with the `Prefer` header.
 */
import { expect, type Page, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const listTicketsRequest = { method: "GET", path: "/v1/console/tickets" } as const;
const getReportRequest = { method: "GET", path: "/v1/console/reports" } as const;

// The page shows the local dates of the period, and the example's period starts at midnight UTC.
test.use({ timezoneId: "UTC" });

/**
 * Sign in with the session of an example, with the open queue and the given report.
 *
 * @param page - The page.
 * @param session - The `Prefer` value of the session.
 * @param report - The `Prefer` value of the report; the report of a week by default.
 */
async function prepareConsole(
  page: Page,
  session: string,
  report = "example=period-with-activity",
): Promise<void> {
  await preferOutcome(page, getSessionRequest, session);
  await preferOutcome(page, listTicketsRequest, "example=open-queue");
  await preferOutcome(page, getReportRequest, report);
  await createSessionCookie(page);
}

/**
 * Record the path of every report request that the page sends.
 *
 * @param page - The page.
 * @returns The paths, in the order in which the requests go out.
 */
function recordReportRequests(page: Page): readonly string[] {
  const paths: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname === getReportRequest.path) {
      paths.push(pathname);
    }
  });
  return paths;
}

test("a manager opens Reports from the navigation and reads the figures of the week", async ({
  page,
}) => {
  await prepareConsole(page, "example=manager");
  await page.goto("/console");

  await page.getByRole("banner").getByRole("link", { name: "Reports" }).click();

  await expect(page).toHaveURL(/\/console\/reports$/);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
  await expect(main.getByText("1 Nov 2026 – 7 Nov 2026")).toBeVisible();
  const latencyP95 = main
    .getByRole("table", { name: "Speed" })
    .getByRole("row", { name: /^End-to-end latency p95 / });
  await expect(latencyP95).toContainText("9.8 s");
  await expect(latencyP95).toContainText("At most 12 s");
  await expect(
    main.getByRole("table", { name: "Tickets" }).getByRole("row", { name: /^Created, assisted / }),
  ).toContainText("5 tickets");
  // The page scrolls on its own inside the console; at 1280 px it never scrolls sideways (UI-33).
  expect(await main.evaluate((element) => element.scrollWidth - element.clientWidth)).toBe(0);
  await expectNoAccessibilityViolations(page);
});

test("staff have no link to Reports", async ({ page }) => {
  await prepareConsole(page, "example=staff");
  await page.goto("/console");

  const bar = page.getByRole("banner");
  await expect(bar.getByRole("link", { name: "Tickets" })).toBeVisible();
  await expect(bar.getByRole("link", { name: "Reports" })).toHaveCount(0);
});

test("staff who open the address of Reports see the permission-denied state without a request", async ({
  page,
}) => {
  await prepareConsole(page, "example=staff");
  const reportRequests = recordReportRequests(page);

  await page.goto("/console/reports");

  const main = page.getByRole("main");
  await expect(
    main.getByRole("heading", { level: 1, name: "You cannot open this page" }),
  ).toBeVisible();
  await expect(main.getByRole("heading", { name: "Reports" })).toHaveCount(0);
  expect(reportRequests).toEqual([]);
  await expectNoAccessibilityViolations(page);
});

test("a manager whom backend refuses with 403 sees the permission-denied state", async ({
  page,
}) => {
  await prepareConsole(page, "example=manager", "code=403, example=forbidden-role");

  await page.goto("/console/reports");

  const main = page.getByRole("main");
  await expect(
    main.getByRole("heading", { level: 1, name: "You cannot open this page" }),
  ).toBeVisible();
  await expect(main.getByText(/Details: trace/)).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

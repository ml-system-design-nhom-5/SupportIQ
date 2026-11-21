/**
 * The console columns against the Prism mock (console UI design, Column controls): the splitters
 * resize the inbox and the AI sidebar within their limits in px and collapse each to a 48 px rail,
 * the rail of a collapsed AI sidebar marks a staff note, and the browser keeps the layout of the
 * account across tickets and reloads. The desktop project runs these flows at 1280 px, the least
 * width of the console. The mock is stateless, so each ticket ID gets an example of its own.
 */
import { expect, type Locator, type Page, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const listTicketsRequest = { method: "GET", path: "/v1/console/tickets" } as const;

/** The sizes of the console columns in px, at every window width (console UI design). */
const INBOX_DEFAULT_WIDTH = 272;
const INBOX_MIN_WIDTH = 200;
const INBOX_MAX_WIDTH = 400;
const AI_DETAILS_DEFAULT_WIDTH = 340;
const RAIL_WIDTH = 48;
const SPLITTER_WIDTH = 16;
/** The padding of the workspace on both sides of its columns together. */
const WORKSPACE_PADDING = 32;
/** A window wider than the 1280 px of the desktop project, with the same height. */
const wideWindow = { width: 1600, height: 900 } as const;
/**
 * Arrow presses that take the inbox past either end of its range. Each press moves the splitter
 * by 5% of the console (react-resizable-panels), 63.2 px at 1280 px, so four presses go from
 * 272 px past 400 px, and from 400 px past 200 px.
 */
const PRESSES_PAST_A_LIMIT = 4;
const STAFF_NOTE_MARK = "Note for staff in AI details";

/** The `Prefer` value of the workspace of each ticket, by ticket ID. */
type TicketExamples = Readonly<Record<string, string>>;

/** A resizable console column, by the names that staff see. */
type ConsoleColumn = {
  /** The name of its landmark, open or collapsed. */
  readonly name: string;
  readonly splitter: string;
  readonly collapseButton: string;
  readonly openButton: string;
  readonly defaultWidth: number;
};

/** The widths in px of the three columns of a ticket. */
type ColumnWidths = {
  readonly inbox: number;
  readonly middle: number;
  readonly aiDetails: number;
};

const inboxColumn: ConsoleColumn = {
  name: "Inbox",
  splitter: "Resize inbox",
  collapseButton: "Collapse inbox",
  openButton: "Open inbox",
  defaultWidth: INBOX_DEFAULT_WIDTH,
};
const aiDetailsColumn: ConsoleColumn = {
  name: "AI details",
  splitter: "Resize AI details",
  collapseButton: "Collapse AI details",
  openButton: "Open AI details",
  defaultWidth: AI_DETAILS_DEFAULT_WIDTH,
};

const draftReady: TicketExamples = { "TCK-1042": "example=draft-ready" };

/**
 * Sign in as staff, choose the example of each ticket, and open one ticket.
 *
 * @param page - The page.
 * @param ticketId - The ticket to open.
 * @param examples - The examples of the tickets of the flow, by ticket ID.
 */
async function openConsoleTicket(
  page: Page,
  ticketId: string,
  examples: TicketExamples,
): Promise<void> {
  await preferOutcome(page, getSessionRequest, "example=staff");
  await preferOutcome(page, listTicketsRequest, "example=open-queue");
  await Promise.all(
    Object.entries(examples).map(([id, prefer]) =>
      preferOutcome(page, { method: "GET", path: `/v1/console/tickets/${id}` }, prefer),
    ),
  );
  await createSessionCookie(page);
  await page.goto(`/console/tickets/${ticketId}`);
  await expect(findTicketHeading(page, ticketId)).toBeVisible();
}

/**
 * Find the heading of a loaded ticket, which the loading workspace does not have.
 *
 * @param page - The page.
 * @param ticketId - The ticket.
 * @returns The level-1 heading of the ticket.
 */
function findTicketHeading(page: Page, ticketId: string): Locator {
  return page.getByRole("heading", { level: 1, name: `Ticket ${ticketId}` });
}

/**
 * Find the landmark of a column, open or collapsed to its rail. The inbox is a navigation
 * landmark; the AI sidebar is a region, and so is its rail.
 *
 * @param page - The page.
 * @param name - The name of the landmark, such as "AI details".
 * @returns The navigation landmark or the region with that name.
 */
function findLandmark(page: Page, name: string): Locator {
  return page
    .getByRole("navigation", { name, exact: true })
    .or(page.getByRole("region", { name, exact: true }));
}

/**
 * Find the column around a landmark: the innermost panel of the layout that holds it.
 *
 * @param page - The page.
 * @param landmark - An element of the column.
 * @returns The panel, whose box is the column with its border.
 */
function findColumn(page: Page, landmark: Locator): Locator {
  const panels = page.locator("[data-panel]");
  return panels.filter({ has: landmark }).filter({ hasNot: panels });
}

/**
 * Read the width of a column.
 *
 * @param column - A column on the screen.
 * @returns Its width in whole px.
 */
async function readWidth(column: Locator): Promise<number> {
  const box = await column.boundingBox();
  if (box === null) {
    throw new Error("The column is not on the screen.");
  }
  return Math.round(box.width);
}

/**
 * Read the widths of the columns of a ticket with a ready draft.
 *
 * @param page - The page.
 * @returns The widths of the inbox, the middle column, and the AI sidebar.
 */
async function readColumnWidths(page: Page): Promise<ColumnWidths> {
  return {
    inbox: await readWidth(findColumn(page, findLandmark(page, inboxColumn.name))),
    middle: await readWidth(findColumn(page, page.getByRole("region", { name: "AI draft" }))),
    aiDetails: await readWidth(findColumn(page, findLandmark(page, aiDetailsColumn.name))),
  };
}

/**
 * Press a key on a splitter several times, as a person does.
 *
 * @param splitter - The splitter, which takes the focus.
 * @param key - The arrow key.
 * @param times - How many presses.
 */
async function pressRepeatedly(
  splitter: Locator,
  key: "ArrowLeft" | "ArrowRight",
  times: number,
): Promise<void> {
  for (let press = 0; press < times; press += 1) {
    await splitter.press(key);
  }
}

/** The widths of the columns at the wide window: the middle column takes the rest. */
const wideWindowWidths: ColumnWidths = {
  inbox: INBOX_DEFAULT_WIDTH,
  middle:
    wideWindow.width -
    INBOX_DEFAULT_WIDTH -
    AI_DETAILS_DEFAULT_WIDTH -
    2 * SPLITTER_WIDTH -
    WORKSPACE_PADDING,
  aiDetails: AI_DETAILS_DEFAULT_WIDTH,
};

test("Arrow keys on Resize inbox resize the inbox, which stops at 400 px and at 200 px", async ({
  page,
}) => {
  await openConsoleTicket(page, "TCK-1042", draftReady);
  const splitter = page.getByRole("separator", { name: inboxColumn.splitter });
  const inbox = findColumn(page, findLandmark(page, inboxColumn.name));

  await pressRepeatedly(splitter, "ArrowRight", PRESSES_PAST_A_LIMIT);
  await expect.poll(() => readWidth(inbox)).toBe(INBOX_MAX_WIDTH);

  await pressRepeatedly(splitter, "ArrowLeft", PRESSES_PAST_A_LIMIT);
  await expect.poll(() => readWidth(inbox)).toBe(INBOX_MIN_WIDTH);
});

for (const column of [inboxColumn, aiDetailsColumn]) {
  test(`Enter on ${column.splitter} collapses the column to its rail, and Enter again restores it`, async ({
    page,
  }) => {
    await openConsoleTicket(page, "TCK-1042", draftReady);
    const splitter = page.getByRole("separator", { name: column.splitter });
    const panel = findColumn(page, findLandmark(page, column.name));

    await splitter.press("Enter");
    await expect(
      page.getByRole("button", { name: column.openButton, expanded: false }),
    ).toBeVisible();
    await expect.poll(() => readWidth(panel)).toBe(RAIL_WIDTH);

    await splitter.press("Enter");
    await expect(
      page.getByRole("button", { name: column.collapseButton, expanded: true }),
    ).toBeVisible();
    await expect.poll(() => readWidth(panel)).toBe(column.defaultWidth);
  });
}

test("a collapsed inbox stays collapsed on the next ticket and after a reload", async ({
  page,
}) => {
  await openConsoleTicket(page, "TCK-1038", {
    "TCK-1038": "example=ai-service-unavailable",
    "TCK-1042": "example=draft-ready",
  });
  await findLandmark(page, inboxColumn.name)
    .getByRole("link", { name: /TCK-1042/ })
    .click();
  await expect(findTicketHeading(page, "TCK-1042")).toBeVisible();
  await page.getByRole("button", { name: inboxColumn.collapseButton }).click();
  const openInbox = page.getByRole("button", { name: inboxColumn.openButton, expanded: false });
  await expect(openInbox).toBeVisible();

  // With the inbox collapsed, staff reach another ticket with Back, without loading the page.
  await page.goBack();

  await expect(findTicketHeading(page, "TCK-1038")).toBeVisible();
  await expect(openInbox).toBeVisible();
  await page.reload();
  await expect(findTicketHeading(page, "TCK-1038")).toBeVisible();
  await expect(openInbox).toBeVisible();
});

test("a resized inbox keeps its width after a reload", async ({ page }) => {
  await openConsoleTicket(page, "TCK-1042", draftReady);
  const inbox = findColumn(page, findLandmark(page, inboxColumn.name));
  await page.getByRole("separator", { name: inboxColumn.splitter }).press("ArrowRight");
  await expect.poll(() => readWidth(inbox)).toBeGreaterThan(INBOX_DEFAULT_WIDTH);
  const resizedWidth = await readWidth(inbox);

  await page.reload();

  await expect(findTicketHeading(page, "TCK-1042")).toBeVisible();
  await expect.poll(() => readWidth(inbox)).toBe(resizedWidth);
});

test("the rail of a collapsed AI sidebar marks the staff note of a ticket that has one", async ({
  page,
}) => {
  await openConsoleTicket(page, "TCK-1042", {
    "TCK-1042": "example=abstained-low-confidence",
    "TCK-1046": "example=authority-required",
  });
  await page.getByRole("button", { name: aiDetailsColumn.collapseButton }).click();
  const rail = findLandmark(page, aiDetailsColumn.name);
  await expect(rail.getByRole("img", { name: STAFF_NOTE_MARK })).toBeVisible();

  // The ticket of the authority-required example has an analysis without a staff note.
  await page.goto("/console/tickets/TCK-1046");

  await expect(findTicketHeading(page, "TCK-1046")).toBeVisible();
  await expect(rail.getByRole("button", { name: aiDetailsColumn.openButton })).toBeVisible();
  await expect(rail.getByRole("img", { name: STAFF_NOTE_MARK })).toHaveCount(0);
});

test("at 1600 px the inbox and the AI sidebar open at their widths, and the middle column takes the rest", async ({
  page,
}) => {
  await page.setViewportSize(wideWindow);

  await openConsoleTicket(page, "TCK-1042", draftReady);

  await expect.poll(() => readColumnWidths(page)).toEqual(wideWindowWidths);
});

test("the inbox and the AI sidebar keep their widths when the window grows to 1600 px", async ({
  page,
}) => {
  await openConsoleTicket(page, "TCK-1042", draftReady);
  await expect
    .poll(() => readColumnWidths(page))
    .toMatchObject({
      inbox: INBOX_DEFAULT_WIDTH,
      aiDetails: AI_DETAILS_DEFAULT_WIDTH,
    });

  await page.setViewportSize(wideWindow);

  await expect.poll(() => readColumnWidths(page)).toEqual(wideWindowWidths);
});

test("the console with both columns collapsed has no accessibility violations", async ({
  page,
}) => {
  await openConsoleTicket(page, "TCK-1042", { "TCK-1042": "example=abstained-low-confidence" });
  await page.getByRole("button", { name: inboxColumn.collapseButton }).click();
  await page.getByRole("button", { name: aiDetailsColumn.collapseButton }).click();
  await expect(page.getByRole("button", { name: inboxColumn.openButton })).toBeVisible();
  await expect(page.getByRole("img", { name: STAFF_NOTE_MARK })).toBeVisible();

  await expectNoAccessibilityViolations(page);
});

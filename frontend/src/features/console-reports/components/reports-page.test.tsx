import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getConsoleReportRoute } from "@/test/backend-routes";
import { readExampleWith, readOperationExample, withoutMembers } from "@/test/contract-examples";
import { exampleAnswer, holdAnswer } from "@/test/fake-backend";
import {
  openReports,
  readFigure,
  readFigures,
  reportExample,
  type ShownFigure,
} from "@/test/reports-screen";

/** The UTC timestamps of the last 7 days at the time of every test, 5 November 2026, 09:00 UTC. */
const lastSevenDays = { startAt: "2026-10-30T00:00:00.000Z", endAt: "2026-11-06T00:00:00.000Z" };

/** The week with activity, with codes and statuses that a later contract version may add. */
const reportWithLaterCodes = readExampleWith("getConsoleReport", "period-with-activity", {
  escalations: {
    escalation_count: 3,
    by_reason: [
      { staff_reason_code: "a_later_staff_reason", escalation_count: 1 },
      { staff_reason_code: "another_later_staff_reason", escalation_count: 2 },
    ],
  },
  ai_outcomes: {
    by_draft_status: [
      { draft_status: "draft_ready", suggestion_count: 2 },
      { draft_status: "a_later_status", suggestion_count: 3 },
      { draft_status: "another_later_status", suggestion_count: 4 },
    ],
    by_reason_code: [
      { reason_code: "a_later_reason", suggestion_count: 1 },
      { reason_code: "another_later_reason", suggestion_count: 2 },
    ],
  },
});

/** The week with activity without `draft_decisions.reject_count`, which the contract requires. */
const reportWithoutRejectCount = readExampleWith("getConsoleReport", "period-with-activity", {
  draft_decisions: withoutMembers(
    readOperationExample("getConsoleReport", 200, "period-with-activity").draft_decisions,
    ["reject_count"],
  ),
});

/** Figures of the week with activity: the section, then the label, value, and target. */
const weekFigureCases: readonly (readonly [string, ShownFigure])[] = [
  ["Speed", { label: "End-to-end latency p50", value: "3.6 s", target: "At most 4 s" }],
  ["Speed", { label: "End-to-end latency p95", value: "9.8 s", target: "At most 12 s" }],
  [
    "Speed",
    {
      label: "Handling time p50, assisted",
      value: "17 min 30 s",
      target: "At least 20% shorter than manual",
    },
  ],
  ["Tickets", { label: "Created, assisted", value: "5 tickets", target: "No target" }],
  [
    "AI health and cost",
    {
      label: "LLM cost per suggestion that called the LLM",
      value: "$0.00021",
      target: "No target",
    },
  ],
];

/**
 * Read the rows of a section as the label and the value of each figure.
 *
 * @param section - The title of the section.
 * @returns The rows, in order.
 */
async function readRows(section: string): Promise<readonly (readonly string[])[]> {
  return (await readFigures(section)).map(({ label, value }) => [label, value]);
}

describe("The Reports page of a manager", () => {
  it("shows the title and the dates of the period that backend returned", async () => {
    openReports();

    expect(await screen.findByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    expect(await screen.findByText("1 Nov 2026 – 7 Nov 2026")).toBeVisible();
  });

  it.each(weekFigureCases)(
    "shows a figure of %s with its unit and its target: %o (UI-44)",
    async (section, figure) => {
      openReports();

      expect(await readFigures(section)).toContainEqual(figure);
    },
  );

  it("names the browser tab", async () => {
    openReports();

    await screen.findByRole("heading", { level: 1, name: "Reports" });
    expect(document.title).toBe("Reports · Console · SupportIQ");
  });

  it("asks for the last 7 days of the local calendar first", async () => {
    const { backend } = openReports();

    await screen.findByRole("table", { name: "Tickets" });
    const [request] = backend.requestsTo(getConsoleReportRoute);
    expect(request?.searchParams.get("start_at")).toBe(lastSevenDays.startAt);
    expect(request?.searchParams.get("end_at")).toBe(lastSevenDays.endAt);
  });

  it("loads the report of the period that the manager chooses", async () => {
    const { user, backend } = openReports();
    await screen.findByRole("table", { name: "Tickets" });

    await user.click(screen.getByRole("button", { name: "Report period: Last 7 days" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "Last month" }));

    expect(await screen.findByRole("button", { name: "Report period: Last month" })).toBeVisible();
    await waitFor(() => {
      expect(backend.requestsTo(getConsoleReportRoute)).toHaveLength(2);
    });
    const lastRequest = backend.requestsTo(getConsoleReportRoute).at(-1);
    expect(lastRequest?.searchParams.get("start_at")).toBe("2026-10-01T00:00:00.000Z");
    expect(lastRequest?.searchParams.get("end_at")).toBe("2026-11-01T00:00:00.000Z");
  });

  it("shows No data for every share, percentile, and average of a period without records", async () => {
    openReports({ report: [reportExample("empty-period")] });

    expect(await screen.findByText("1 Dec 2026 – 7 Dec 2026")).toBeVisible();
    expect((await readFigure("Speed", "End-to-end latency p50")).value).toBe("No data");
    expect((await readFigure("Speed", "Handling time p50, assisted")).value).toBe("No data");
    expect((await readFigure("AI health and cost", "AI error rate")).value).toBe(
      "No data · 0 of 0 suggestions",
    );
    expect((await readFigure("Draft decisions", "Approved")).value).toBe("0 replies · No data");
    expect(screen.getByText("No suggestions were completed in this period.")).toBeVisible();
    expect(screen.queryByRole("table", { name: "AI outcomes" })).not.toBeInTheDocument();
  });

  it("shows placeholder panels while the report loads, and keeps the period menu", async () => {
    const report = holdAnswer(exampleAnswer(200, "getConsoleReport", "period-with-activity"));
    openReports({ report: [report.answer] });

    expect(await screen.findByText("Loading the report…")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Report period: Last 7 days" })).toBeVisible();
    report.release();

    expect(await screen.findByRole("table", { name: "Tickets" })).toBeVisible();
    expect(screen.queryByText("Loading the report…")).not.toBeInTheDocument();
  });

  it("shows one row per code and status that this version does not know, never a sum (CON-22)", async () => {
    openReports({ report: [{ kind: "body", status: 200, body: reportWithLaterCodes }] });

    expect(await readRows("AI outcomes")).toEqual([
      ["Draft ready", "2 suggestions"],
      ["Status unknown", "3 suggestions"],
      ["Status unknown", "4 suggestions"],
    ]);
    expect(await readRows("AI reasons")).toEqual([
      ["Unspecified reason", "1 suggestion"],
      ["Unspecified reason", "2 suggestions"],
    ]);
    expect(await readRows("Escalations by staff reason")).toEqual([
      ["Escalations", "3 escalations"],
      ["Unspecified reason", "1 escalation"],
      ["Unspecified reason", "2 escalations"],
    ]);
  });
});

describe("The Reports page when it could not load", () => {
  it("says to choose another period after a 422, with the trace ID, below the header (UI-25)", async () => {
    openReports({ report: [exampleAnswer(422, "problems", "invalid-period")] });

    expect(
      await screen.findByRole("heading", { level: 2, name: "The report could not be loaded" }),
    ).toBeVisible();
    expect(
      screen.getByText("This period could not be reported. Choose another period."),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Report period: Last 7 days" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("tries again after a 500, and shows the report", async () => {
    const { user } = openReports({
      report: [
        exampleAnswer(500, "problems", "internal-error"),
        reportExample("period-with-activity"),
      ],
    });
    await screen.findByRole("heading", { level: 2, name: "The report could not be loaded" });
    expect(screen.getByText(/Details: trace/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("table", { name: "Tickets" })).toBeVisible();
  });

  it("says that the server could not be reached, without a trace ID it does not have", async () => {
    openReports({ report: [{ kind: "network_error" }] });

    expect(
      await screen.findByText(
        "The server could not be reached. Check your connection and try again.",
      ),
    ).toBeVisible();
    expect(screen.queryByText(/Details: trace/)).not.toBeInTheDocument();
  });

  it("shows the error state instead of figures when a 200 body lacks a required member (CODE-32)", async () => {
    openReports({ report: [{ kind: "body", status: 200, body: reportWithoutRejectCount }] });

    expect(
      await screen.findByRole("heading", { level: 2, name: "The report could not be loaded" }),
    ).toBeVisible();
    expect(screen.getByText("Something went wrong. Try again in a moment.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("The Reports page and the roles (UI-40, UI-44)", () => {
  it("is in the navigation of a manager", async () => {
    openReports();

    const bar = await screen.findByRole("banner");
    expect(within(bar).getByRole("link", { name: "Reports" })).toHaveAttribute(
      "href",
      "/console/reports",
    );
  });

  it("is not in the navigation of staff", async () => {
    openReports({ session: "staff" });

    const bar = await screen.findByRole("banner");
    expect(within(bar).getByRole("link", { name: "Tickets" })).toBeVisible();
    expect(within(bar).queryByRole("link", { name: "Reports" })).not.toBeInTheDocument();
  });

  it("shows staff the permission-denied state at its address, without the header", async () => {
    openReports({ session: "staff" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "You cannot open this page" }),
    ).toBeVisible();
    expect(
      screen.getByText("Your role does not allow it. Ask a manager if you need it."),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Reports" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Report period/ })).not.toBeInTheDocument();
  });

  it("sends no report request for staff", async () => {
    const { backend } = openReports({ session: "staff" });

    await screen.findByRole("heading", { level: 1, name: "You cannot open this page" });
    expect(backend.requestsTo(getConsoleReportRoute)).toHaveLength(0);
  });

  it("shows the same state when backend refuses a manager with 403", async () => {
    openReports({ report: [exampleAnswer(403, "problems", "forbidden-role")] });

    expect(
      await screen.findByRole("heading", { level: 1, name: "You cannot open this page" }),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /^Report period/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("offers Sign out to an account without the console", async () => {
    openReports({ session: "customer" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "The console is for support accounts" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });
});

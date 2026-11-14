import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getConsoleReportRoute } from "@/test/backend-routes";
import { readExampleWith } from "@/test/contract-examples";
import { exampleAnswer, holdAnswer } from "@/test/fake-backend";
import { openReports, readFigure, reportExample } from "@/test/reports-screen";

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

/**
 * Read the rows of a section as the label and the value of each figure.
 *
 * @param section - The title of the section.
 * @returns The rows, in order.
 */
async function readRows(section: string): Promise<string[][]> {
  const table = await screen.findByRole("table", { name: section });
  return within(table)
    .getAllByRole("rowheader")
    .map((header) => [header.textContent, header.nextElementSibling?.textContent ?? ""]);
}

describe("The Reports page of a manager", () => {
  it("shows the figures of the period with their units and their targets (UI-44)", async () => {
    openReports();

    expect(await screen.findByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    expect(await screen.findByText("1 Nov 2026 – 7 Nov 2026")).toBeVisible();
    expect(await readFigure("Speed", "End-to-end latency p50")).toEqual({
      value: "3.6 s",
      target: "At most 4 s",
    });
    expect(await readFigure("Speed", "End-to-end latency p95")).toEqual({
      value: "9.8 s",
      target: "At most 12 s",
    });
    expect(await readFigure("Speed", "Handling time p50, assisted")).toEqual({
      value: "17 min 30 s",
      target: "At least 20% shorter than manual",
    });
    expect(await readFigure("Tickets", "Created, assisted")).toEqual({
      value: "5 tickets",
      target: "No target",
    });
    expect(await readFigure("AI health and cost", "LLM cost per suggestion")).toEqual({
      value: "$0.00021",
      target: "No target",
    });
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
    expect((await readFigure("AI health and cost", "AI error rate")).value).toBe("No data");
    expect((await readFigure("Draft decisions", "Approved")).value).toBe("0 replies");
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
  it("shows a 422 as the error state with the trace ID, below the header (UI-25)", async () => {
    openReports({ report: [exampleAnswer(422, "problems", "invalid-period")] });

    expect(
      await screen.findByRole("heading", { level: 2, name: "The report could not be loaded" }),
    ).toBeVisible();
    expect(
      screen.getByText("The request was not accepted. Check what you entered and try again."),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
    expect(screen.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Report period: Last 7 days" })).toBeVisible();
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

  it("is not in the navigation of staff, who see the permission-denied state at its address", async () => {
    openReports({ session: "staff", report: [exampleAnswer(403, "problems", "forbidden-role")] });

    const bar = await screen.findByRole("banner");
    expect(within(bar).getByRole("link", { name: "Tickets" })).toBeVisible();
    expect(within(bar).queryByRole("link", { name: "Reports" })).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 1, name: "You cannot open this page" }),
    ).toBeVisible();
    expect(
      screen.getByText("Your role does not allow it. Ask a manager if you need it."),
    ).toBeVisible();
    expect(screen.getByText(/Details: trace/)).toBeVisible();
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
    openReports({
      session: "customer",
      report: [exampleAnswer(403, "problems", "forbidden-role")],
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "The console is for support accounts" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
  });
});

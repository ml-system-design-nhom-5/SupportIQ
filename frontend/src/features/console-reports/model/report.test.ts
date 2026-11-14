import { describe, expect, it } from "vitest";

import { type ConsoleReport, toConsoleReport } from "@/features/console-reports/model/report";
import { toCompletedDraftStatus } from "@/features/console-reports/model/report-breakdowns";
import type {
  ReportSection,
  ReportSectionId,
} from "@/features/console-reports/model/report-section";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";
import { readBackendSchema, readEnumValues } from "@/test/contract-schemas";

/** The report of a week with activity: the example `period-with-activity`. */
const weekWithActivity = toConsoleReport(
  readOperationExample("getConsoleReport", 200, "period-with-activity"),
);

/** The report of a period without any record: the example `empty-period`. */
const emptyPeriod = toConsoleReport(readOperationExample("getConsoleReport", 200, "empty-period"));

/** The body of the week with activity, for the cases that change one member of it. */
const weekBody = readOperationExample("getConsoleReport", 200, "period-with-activity");

/** Bodies of the week that each lack one required member: of the report, a part, or a count. */
const bodiesWithoutAMember: readonly (readonly [string, object])[] = [
  ["handling_time", withoutMembers(weekBody, ["handling_time"])],
  [
    "reject_count",
    { ...weekBody, draft_decisions: withoutMembers(weekBody.draft_decisions, ["reject_count"]) },
  ],
  [
    "draft_status",
    {
      ...weekBody,
      ai_outcomes: {
        ...weekBody.ai_outcomes,
        by_draft_status: weekBody.ai_outcomes.by_draft_status.map((statusCount) =>
          withoutMembers(statusCount, ["draft_status"]),
        ),
      },
    },
  ],
];

/** The figures of each section of the week with activity: label, value, and target. */
const weekFigureCases: readonly (readonly [ReportSectionId, readonly (readonly string[])[]])[] = [
  [
    "tickets",
    [
      ["Created, assisted", "5 tickets", "No target"],
      ["Created, manual", "1 ticket", "No target"],
      ["Closed, assisted", "2 tickets", "No target"],
      ["Closed, manual", "0 tickets", "No target"],
    ],
  ],
  [
    "draft_decisions",
    [
      ["Approved", "1 reply · 50%", "No target"],
      ["Edited", "1 reply · 50%", "No target"],
      ["Rejected", "0 replies · 0%", "No target"],
    ],
  ],
  [
    "speed",
    [
      ["End-to-end latency p50", "3.6 s", "At most 4 s"],
      ["End-to-end latency p95", "9.8 s", "At most 12 s"],
      ["Tickets measured for latency", "4 tickets", "No target"],
      ["Handling time p50, assisted", "17 min 30 s", "At least 20% shorter than manual"],
      ["Handling time p50, manual", "No data", "No target"],
      ["Closed tickets measured, assisted", "2 tickets", "No target"],
      ["Closed tickets measured, manual", "0 tickets", "No target"],
    ],
  ],
  [
    "ai_health_and_cost",
    [
      ["AI error rate", "25% · 1 of 4 suggestions", "No target"],
      ["LLM cost, total", "$0.00042", "No target"],
      ["LLM cost per suggestion that called the LLM", "$0.00021", "No target"],
      ["Suggestions that called the LLM", "2 suggestions", "No target"],
    ],
  ],
  [
    "escalations",
    [
      ["Escalations", "1 escalation", "No target"],
      ["Other", "1 escalation", "No target"],
    ],
  ],
  [
    "ai_outcomes",
    [
      ["Draft ready", "2 suggestions", "No target"],
      ["Escalation recommended", "1 suggestion", "No target"],
      ["AI unavailable", "1 suggestion", "No target"],
    ],
  ],
  ["edits_and_rejections", [["Edited: Tone or clarity", "1 reply", "No target"]]],
  [
    "ai_reasons",
    [
      ["Human agent requested", "1 suggestion", "No target"],
      ["Requires authority", "1 suggestion", "No target"],
      ["AI service unavailable", "1 suggestion", "No target"],
    ],
  ],
];

/** The figures of the empty period that backend leaves out: section, label, and value. */
const missingFigureCases: readonly (readonly [ReportSectionId, string, string])[] = [
  ["draft_decisions", "Approved", "0 replies · No data"],
  ["draft_decisions", "Edited", "0 replies · No data"],
  ["draft_decisions", "Rejected", "0 replies · No data"],
  ["speed", "End-to-end latency p50", "No data"],
  ["speed", "End-to-end latency p95", "No data"],
  ["speed", "Handling time p50, assisted", "No data"],
  ["speed", "Handling time p50, manual", "No data"],
  ["ai_health_and_cost", "AI error rate", "No data · 0 of 0 suggestions"],
  ["ai_health_and_cost", "LLM cost per suggestion that called the LLM", "No data"],
];

/**
 * Find a section of a report.
 *
 * @param report - The mapped report.
 * @param id - The section.
 * @returns The section.
 */
function findSection(report: ConsoleReport, id: ReportSectionId): ReportSection {
  const section = report.sections.find((candidate) => candidate.id === id);
  if (section === undefined) {
    throw new Error(`The report has no section ${id}.`);
  }
  return section;
}

/**
 * Read the figures of a section as rows of label, value, and target.
 *
 * @param report - The mapped report.
 * @param id - The section.
 * @returns The rows, in order.
 */
function readFigures(report: ConsoleReport, id: ReportSectionId): readonly string[][] {
  return findSection(report, id).figures.map((figure) => [
    figure.label,
    figure.value,
    figure.target,
  ]);
}

describe("toConsoleReport with a week with activity", () => {
  it("shows the dates of the period that backend returned, up to the last included day", () => {
    expect(weekWithActivity.periodText).toBe("1 Nov 2026 – 7 Nov 2026");
  });

  it("orders the sections as the page shows them", () => {
    expect(weekWithActivity.sections.map((section) => section.title)).toEqual([
      "Tickets",
      "Draft decisions",
      "Speed",
      "AI health and cost",
      "Escalations by staff reason",
      "AI outcomes",
      "Edits and rejections by staff reason",
      "AI reasons",
    ]);
  });

  it.each(weekFigureCases)("maps the section %s with units and targets", (id, figures) => {
    expect(readFigures(weekWithActivity, id)).toEqual(figures);
  });

  it("keys the figures of a breakdown by their raw code (TS-24)", () => {
    expect(findSection(weekWithActivity, "ai_outcomes").figures.map((figure) => figure.id)).toEqual(
      ["status-draft_ready", "status-escalation_recommended", "status-unavailable"],
    );
    expect(findSection(weekWithActivity, "escalations").figures.map((figure) => figure.id)).toEqual(
      ["escalations", "escalation-other"],
    );
  });
});

describe("toConsoleReport with rejections", () => {
  it("lists the rejections by staff reason after the edits, one figure per code", () => {
    // No example has a rejection with a reason yet, so this one is added to the week's example.
    const report = toConsoleReport({
      ...weekBody,
      draft_decisions: {
        ...weekBody.draft_decisions,
        reject_by_reason: [
          { staff_reason_code: "kb_gap", reply_count: 2 },
          { staff_reason_code: "case_exception", reply_count: 1 },
        ],
      },
    });

    expect(readFigures(report, "edits_and_rejections")).toEqual([
      ["Edited: Tone or clarity", "1 reply", "No target"],
      ["Rejected: KB gap", "2 replies", "No target"],
      ["Rejected: Case exception", "1 reply", "No target"],
    ]);
  });
});

describe("toConsoleReport next to a target of at most some time (NFR-08)", () => {
  it("rounds each latency up, so a latency above its target never shows as the target", () => {
    const report = toConsoleReport({
      ...weekBody,
      end_to_end_latency: { ...weekBody.end_to_end_latency, p50_ms: 4010, p95_ms: 12_040 },
    });

    expect(readFigures(report, "speed").slice(0, 2)).toEqual([
      ["End-to-end latency p50", "4.1 s", "At most 4 s"],
      ["End-to-end latency p95", "12.1 s", "At most 12 s"],
    ]);
  });

  it("rounds the handling time to the nearest, because its target is relative (NFR-11)", () => {
    const report = toConsoleReport({
      ...weekBody,
      handling_time: {
        ...weekBody.handling_time,
        assisted: { ...weekBody.handling_time.assisted, p50_ms: 1_050_400 },
      },
    });

    expect(readFigures(report, "speed")[3]).toEqual([
      "Handling time p50, assisted",
      "17 min 30 s",
      "At least 20% shorter than manual",
    ]);
  });
});

describe("toConsoleReport with a period without any record", () => {
  it("shows the dates of the period", () => {
    expect(emptyPeriod.periodText).toBe("1 Dec 2026 – 7 Dec 2026");
  });

  it.each(missingFigureCases)(
    "shows no share, percentile, or average in %s for %s: %s, never 0",
    (id, label, value) => {
      const figure = findSection(emptyPeriod, id).figures.find(
        (candidate) => candidate.label === label,
      );

      expect(figure?.value).toBe(value);
    },
  );

  it("shows the counts and the total cost of 0 that backend sent", () => {
    expect(readFigures(emptyPeriod, "tickets").map(([, value]) => value)).toEqual([
      "0 tickets",
      "0 tickets",
      "0 tickets",
      "0 tickets",
    ]);
    expect(readFigures(emptyPeriod, "escalations")).toEqual([
      ["Escalations", "0 escalations", "No target"],
    ]);
    expect(readFigures(emptyPeriod, "ai_health_and_cost")[1]).toEqual([
      "LLM cost, total",
      "$0.00",
      "No target",
    ]);
  });
});

describe("toConsoleReport with empty breakdowns", () => {
  it.each<[ReportSectionId, string]>([
    ["ai_outcomes", "No suggestions were completed in this period."],
    ["edits_and_rejections", "No edits or rejections with a reason in this period."],
    ["ai_reasons", "No suggestion carried an AI reason in this period."],
  ])("says what the empty breakdown %s means instead of listing zeros", (id, emptyText) => {
    const section = findSection(emptyPeriod, id);

    expect(section.figures).toEqual([]);
    expect(section.emptyText).toBe(emptyText);
  });
});

describe("toConsoleReport with a body of the wrong shape", () => {
  it.each(bodiesWithoutAMember)(
    "stops at a report without the required member %s (CODE-32)",
    (member, body) => {
      expect(() => {
        Reflect.apply(toConsoleReport, undefined, [body]);
      }).toThrow(`The response has no ${member}.`);
    },
  );
});

describe("toCompletedDraftStatus", () => {
  it.each(readEnumValues(readBackendSchema("CompletedDraftStatus")))(
    "keeps the status %s of the contract",
    (status) => {
      expect(toCompletedDraftStatus(status)).toBe(status);
    },
  );

  it.each(["cancelled", "pending", "a_later_status", ""])(
    "maps %j to unknown (CON-22)",
    (status) => {
      expect(toCompletedDraftStatus(status)).toBe("unknown");
    },
  );
});

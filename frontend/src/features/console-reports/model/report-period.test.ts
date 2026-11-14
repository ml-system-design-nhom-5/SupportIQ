import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildReportPeriod,
  formatReportPeriod,
  reportPeriodOptions,
  type ReportPeriodPreset,
} from "@/features/console-reports/model/report-period";

/** A zone with daylight saving time: CET in winter, CEST from the last Sunday of March. */
const BERLIN = "Europe/Berlin";

/** A zone seven hours ahead of UTC without daylight saving time. */
const HO_CHI_MINH_CITY = "Asia/Ho_Chi_Minh";

afterEach(() => {
  // The unit tests run with TZ=UTC (vite.config.ts); a test that sets another zone gives it back.
  vi.unstubAllEnvs();
});

describe("reportPeriodOptions", () => {
  it("lists the periods in the order of the menu, Last 7 days first", () => {
    expect(reportPeriodOptions.map((option) => option.label)).toEqual([
      "Last 7 days",
      "Last 30 days",
      "This month",
      "Last month",
    ]);
  });
});

/** A period that a preset gives at a time `now`, in UTC unless a test sets a zone. */
type PeriodCase = {
  readonly preset: ReportPeriodPreset;
  readonly now: string;
  readonly startAt: string;
  readonly endAt: string;
};

/** The presets in the middle of a month, at the time of every test (render-app.tsx). */
const midMonthCases: readonly PeriodCase[] = [
  // Last 7 days: today and the 6 days before; the end is the next local midnight.
  {
    preset: "last_7_days",
    now: "2026-11-05T09:00:00Z",
    startAt: "2026-10-30T00:00:00.000Z",
    endAt: "2026-11-06T00:00:00.000Z",
  },
  {
    preset: "last_30_days",
    now: "2026-11-05T09:00:00Z",
    startAt: "2026-10-07T00:00:00.000Z",
    endAt: "2026-11-06T00:00:00.000Z",
  },
  // This month includes today.
  {
    preset: "this_month",
    now: "2026-11-05T09:00:00Z",
    startAt: "2026-11-01T00:00:00.000Z",
    endAt: "2026-12-01T00:00:00.000Z",
  },
  {
    preset: "last_month",
    now: "2026-11-05T09:00:00Z",
    startAt: "2026-10-01T00:00:00.000Z",
    endAt: "2026-11-01T00:00:00.000Z",
  },
];

/** The last second of a month, and the end and the start of a year. */
const monthAndYearEndCases: readonly PeriodCase[] = [
  {
    preset: "last_7_days",
    now: "2026-10-31T23:59:59Z",
    startAt: "2026-10-25T00:00:00.000Z",
    endAt: "2026-11-01T00:00:00.000Z",
  },
  {
    preset: "this_month",
    now: "2026-10-31T23:59:59Z",
    startAt: "2026-10-01T00:00:00.000Z",
    endAt: "2026-11-01T00:00:00.000Z",
  },
  {
    preset: "last_7_days",
    now: "2026-12-31T12:00:00Z",
    startAt: "2026-12-25T00:00:00.000Z",
    endAt: "2027-01-01T00:00:00.000Z",
  },
  {
    preset: "this_month",
    now: "2026-12-31T12:00:00Z",
    startAt: "2026-12-01T00:00:00.000Z",
    endAt: "2027-01-01T00:00:00.000Z",
  },
  {
    preset: "last_7_days",
    now: "2027-01-01T12:00:00Z",
    startAt: "2026-12-26T00:00:00.000Z",
    endAt: "2027-01-02T00:00:00.000Z",
  },
  {
    preset: "last_month",
    now: "2027-01-01T12:00:00Z",
    startAt: "2026-12-01T00:00:00.000Z",
    endAt: "2027-01-01T00:00:00.000Z",
  },
];

/** 29 February 2028, and the day after it. */
const leapDayCases: readonly PeriodCase[] = [
  {
    preset: "last_7_days",
    now: "2028-02-29T10:00:00Z",
    startAt: "2028-02-23T00:00:00.000Z",
    endAt: "2028-03-01T00:00:00.000Z",
  },
  {
    preset: "last_30_days",
    now: "2028-02-29T10:00:00Z",
    startAt: "2028-01-31T00:00:00.000Z",
    endAt: "2028-03-01T00:00:00.000Z",
  },
  {
    preset: "this_month",
    now: "2028-02-29T10:00:00Z",
    startAt: "2028-02-01T00:00:00.000Z",
    endAt: "2028-03-01T00:00:00.000Z",
  },
  {
    preset: "last_month",
    now: "2028-03-01T10:00:00Z",
    startAt: "2028-02-01T00:00:00.000Z",
    endAt: "2028-03-01T00:00:00.000Z",
  },
  {
    preset: "last_7_days",
    now: "2028-03-01T10:00:00Z",
    startAt: "2028-02-24T00:00:00.000Z",
    endAt: "2028-03-02T00:00:00.000Z",
  },
];

/** Today is the 1st: exactly the first local midnight of November. */
const firstOfMonthCases: readonly PeriodCase[] = [
  {
    preset: "last_month",
    now: "2026-11-01T00:00:00Z",
    startAt: "2026-10-01T00:00:00.000Z",
    endAt: "2026-11-01T00:00:00.000Z",
  },
  {
    preset: "this_month",
    now: "2026-11-01T00:00:00Z",
    startAt: "2026-11-01T00:00:00.000Z",
    endAt: "2026-12-01T00:00:00.000Z",
  },
  {
    preset: "last_7_days",
    now: "2026-11-01T00:00:00Z",
    startAt: "2026-10-26T00:00:00.000Z",
    endAt: "2026-11-02T00:00:00.000Z",
  },
];

describe("buildReportPeriod in UTC", () => {
  it.each(midMonthCases)("builds $preset from $now", ({ preset, now, startAt, endAt }) => {
    expect(buildReportPeriod(preset, new Date(now))).toEqual({ startAt, endAt });
  });

  it.each(monthAndYearEndCases)(
    "builds $preset across the end of a month or a year from $now",
    ({ preset, now, startAt, endAt }) => {
      expect(buildReportPeriod(preset, new Date(now))).toEqual({ startAt, endAt });
    },
  );

  it.each(leapDayCases)(
    "counts 29 February for $preset from $now",
    ({ preset, now, startAt, endAt }) => {
      expect(buildReportPeriod(preset, new Date(now))).toEqual({ startAt, endAt });
    },
  );

  it.each(firstOfMonthCases)(
    "builds $preset when today is the 1st",
    ({ preset, now, startAt, endAt }) => {
      expect(buildReportPeriod(preset, new Date(now))).toEqual({ startAt, endAt });
    },
  );
});

describe("buildReportPeriod in a local time zone", () => {
  it("starts the days at the local midnight, not at midnight UTC", () => {
    vi.stubEnv("TZ", HO_CHI_MINH_CITY);
    // 03:00 on 6 November in Ho Chi Minh City, still 5 November in UTC.
    const now = new Date("2026-11-05T20:00:00Z");

    expect(buildReportPeriod("last_7_days", now)).toEqual({
      // Midnight of 31 October and of 7 November in Ho Chi Minh City.
      startAt: "2026-10-30T17:00:00.000Z",
      endAt: "2026-11-06T17:00:00.000Z",
    });
  });

  it("keeps 7 calendar days across the start of daylight saving time (167 hours)", () => {
    vi.stubEnv("TZ", BERLIN);
    // Noon on Sunday 29 March 2026 in Berlin, the day the clocks go from 02:00 to 03:00.
    const now = new Date("2026-03-29T10:00:00Z");

    const period = buildReportPeriod("last_7_days", now);

    expect(period).toEqual({
      // Midnight of Monday 23 March in CET (UTC+1).
      startAt: "2026-03-22T23:00:00.000Z",
      // Midnight of Monday 30 March in CEST (UTC+2).
      endAt: "2026-03-29T22:00:00.000Z",
    });
  });

  it("keeps 7 calendar days across the end of daylight saving time (169 hours)", () => {
    vi.stubEnv("TZ", BERLIN);
    // Noon on Sunday 25 October 2026 in Berlin, the day the clocks go from 03:00 to 02:00.
    const now = new Date("2026-10-25T11:00:00Z");

    expect(buildReportPeriod("last_7_days", now)).toEqual({
      // Midnight of Monday 19 October in CEST (UTC+2).
      startAt: "2026-10-18T22:00:00.000Z",
      // Midnight of Monday 26 October in CET (UTC+1).
      endAt: "2026-10-25T23:00:00.000Z",
    });
  });

  it("builds the month of a daylight saving change from local midnights", () => {
    vi.stubEnv("TZ", BERLIN);
    const now = new Date("2026-03-29T10:00:00Z");

    expect(buildReportPeriod("this_month", now)).toEqual({
      startAt: "2026-02-28T23:00:00.000Z",
      endAt: "2026-03-31T22:00:00.000Z",
    });
  });
});

describe("formatReportPeriod", () => {
  it("shows the first and the last included day, because the end is excluded", () => {
    const period = { startAt: "2026-11-01T00:00:00Z", endAt: "2026-11-08T00:00:00Z" };

    expect(formatReportPeriod(period)).toBe("1 Nov 2026 – 7 Nov 2026");
  });

  it("shows one day twice for a period of one day", () => {
    const period = { startAt: "2026-11-05T00:00:00Z", endAt: "2026-11-06T00:00:00Z" };

    expect(formatReportPeriod(period)).toBe("5 Nov 2026 – 5 Nov 2026");
  });

  it("shows the local dates of a period built from local midnights", async () => {
    vi.stubEnv("TZ", HO_CHI_MINH_CITY);
    // The shared date formatter reads the time zone once, when its module loads, as a browser
    // page does. Load it again in the zone of this test.
    vi.resetModules();
    const periodModule = await import("@/features/console-reports/model/report-period");
    const period = { startAt: "2026-10-30T17:00:00.000Z", endAt: "2026-11-06T17:00:00.000Z" };

    expect(periodModule.formatReportPeriod(period)).toBe("31 Oct 2026 – 6 Nov 2026");
  });
});

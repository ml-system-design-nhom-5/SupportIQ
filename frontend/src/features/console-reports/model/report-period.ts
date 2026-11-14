/**
 * The periods that a manager chooses for a report (console UI design, Reports; UI-44), and the
 * text of the period that `backend` returns.
 *
 * Every boundary is a local midnight in the time zone of the browser. It is built from the
 * calendar date of `now` by adding calendar days or months, never by adding 86 400 000 ms, so a
 * day with a daylight saving change keeps its place in the local calendar. The end is excluded,
 * as `getConsoleReport` defines it.
 */
import { formatDate, type MenuSelectOption } from "@/design-system";

/** The days of "Last 7 days": today and the 6 days before. */
const LAST_7_DAYS_COUNT = 7;

/** The days of "Last 30 days": today and the 29 days before. */
const LAST_30_DAYS_COUNT = 30;

/** The periods, in the order of the menu. */
const reportPeriodPresets = ["last_7_days", "last_30_days", "this_month", "last_month"] as const;

/** The period that the page shows first. */
export const DEFAULT_REPORT_PERIOD_PRESET = "last_7_days" satisfies ReportPeriodPreset;

/** The label of each period. */
const labelByPreset: Readonly<Record<ReportPeriodPreset, string>> = {
  last_7_days: "Last 7 days",
  last_30_days: "Last 30 days",
  this_month: "This month",
  last_month: "Last month",
};

/** The options of the period menu, in the order of {@link reportPeriodPresets}. */
export const reportPeriodOptions: readonly MenuSelectOption<ReportPeriodPreset>[] =
  reportPeriodPresets.map((preset) => ({ value: preset, label: labelByPreset[preset] }));

/** The boundaries of each period, from the calendar date of today. */
const boundariesByPreset: Readonly<
  Record<ReportPeriodPreset, (today: CalendarDate) => PeriodBoundaries>
> = {
  last_7_days: (today) => buildDaysUntilTomorrow(today, LAST_7_DAYS_COUNT),
  last_30_days: (today) => buildDaysUntilTomorrow(today, LAST_30_DAYS_COUNT),
  // This month includes today: from the 1st of this month to the 1st of next month.
  this_month: ({ year, month }) => ({
    start: new Date(year, month, 1),
    end: new Date(year, month + 1, 1),
  }),
  // Last month: from the 1st of last month to the 1st of this month.
  last_month: ({ year, month }) => ({
    start: new Date(year, month - 1, 1),
    end: new Date(year, month, 1),
  }),
};

/** A period that a manager chooses. */
export type ReportPeriodPreset = (typeof reportPeriodPresets)[number];

/** The period of a report request: two UTC RFC 3339 timestamps (CON-17). */
export type ReportPeriod = {
  /** The first local midnight of the period, included. */
  readonly startAt: string;
  /** The local midnight after the last day of the period, excluded. */
  readonly endAt: string;
};

/** A local calendar date; `month` counts from 0, as `Date` does. */
type CalendarDate = {
  readonly year: number;
  readonly month: number;
  readonly day: number;
};

/** The local midnights that bound a period. */
type PeriodBoundaries = {
  readonly start: Date;
  readonly end: Date;
};

/**
 * Build the period of a preset.
 *
 * @param preset - The period that the manager chose.
 * @param now - The current time, from the clock of the caller (CODE-18).
 * @returns The start, included, and the end, excluded, as UTC timestamps of local midnights.
 */
export function buildReportPeriod(preset: ReportPeriodPreset, now: Date): ReportPeriod {
  const today = { year: now.getFullYear(), month: now.getMonth(), day: now.getDate() };
  const { start, end } = boundariesByPreset[preset](today);
  return { startAt: start.toISOString(), endAt: end.toISOString() };
}

/**
 * Write the period of a report as the local dates it covers, from its first day to its last day.
 *
 * @param period - The `start_at`, included, and the `end_at`, excluded, that `backend` returned.
 * @returns For example `1 Nov 2026 – 7 Nov 2026` for 1 November to 8 November, excluded.
 */
export function formatReportPeriod(period: ReportPeriod): string {
  // The last instant of the period, which is one millisecond before the end that is excluded.
  const lastIncludedAt = new Date(Date.parse(period.endAt) - 1).toISOString();
  return `${formatDate(period.startAt)} – ${formatDate(lastIncludedAt)}`;
}

/**
 * Build the days that end with today: from the local midnight of the first day to the local
 * midnight of tomorrow, the start of the next day.
 *
 * @param today - The local date of today.
 * @param dayCount - How many days, today included.
 * @returns The boundaries.
 */
function buildDaysUntilTomorrow(today: CalendarDate, dayCount: number): PeriodBoundaries {
  const { year, month, day } = today;
  return {
    start: new Date(year, month, day - (dayCount - 1)),
    end: new Date(year, month, day + 1),
  };
}

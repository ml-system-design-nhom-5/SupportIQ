import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatRelativeTime } from "@/design-system/format/date-time";

const now = new Date("2026-11-05T09:00:00Z");

const MINUTE = 60;

const HOUR = 60 * MINUTE;

const DAY = 24 * HOUR;

/**
 * Build the timestamp that lies some seconds before now.
 *
 * @param seconds - The number of seconds.
 * @returns The RFC 3339 timestamp.
 */
function secondsAgo(seconds: number): string {
  return new Date(now.getTime() - seconds * 1000).toISOString();
}

describe("formatDate and formatDateTime (tests run in UTC)", () => {
  it("formats the date as day, short month, and year, like the mockups", () => {
    expect(formatDate("2026-10-02T19:30:00Z")).toBe("2 Oct 2026");
  });

  it("formats the date and the time", () => {
    expect(formatDateTime("2026-10-02T19:30:00Z")).toBe("2 Oct 2026, 19:30");
  });

  it("accepts a timestamp with microseconds, as the contract allows", () => {
    expect(formatDate("2026-11-05T09:30:00.125000Z")).toBe("5 Nov 2026");
  });
});

describe("formatRelativeTime", () => {
  it.each([
    [0, "Just now"],
    [MINUTE - 1, "Just now"],
    [MINUTE, "1 minute ago"],
    [18 * MINUTE, "18 minutes ago"],
    [HOUR - 1, "59 minutes ago"],
    [HOUR, "1 hour ago"],
    [2 * HOUR, "2 hours ago"],
    [DAY - 1, "23 hours ago"],
    [DAY, "1 day ago"],
    [7 * DAY - 1, "6 days ago"],
    [7 * DAY, "1 week ago"],
    [23 * DAY, "3 weeks ago"],
    [30 * DAY - 1, "4 weeks ago"],
    [30 * DAY, "1 month ago"],
    [365 * DAY - 1, "12 months ago"],
    [365 * DAY, "1 year ago"],
    [800 * DAY, "2 years ago"],
  ])("writes %i seconds ago as %s", (seconds, text) => {
    expect(formatRelativeTime(secondsAgo(seconds), now)).toBe(text);
  });

  it("writes a time in the future, from clock drift, as Just now", () => {
    expect(formatRelativeTime(secondsAgo(-5 * MINUTE), now)).toBe("Just now");
  });
});

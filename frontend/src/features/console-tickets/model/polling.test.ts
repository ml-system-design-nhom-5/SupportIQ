import { describe, expect, it } from "vitest";

import {
  getInboxPollingIntervalMs,
  INBOX_POLLING_INTERVAL_MS,
  WORKSPACE_FALLBACK_POLLING_INTERVAL_MS,
} from "@/features/console-tickets/model/polling";

describe("getInboxPollingIntervalMs", () => {
  it("never polls under 30 s, as the lead decided on 2026-11-13", () => {
    expect(INBOX_POLLING_INTERVAL_MS).toBeGreaterThanOrEqual(30_000);
  });

  it("polls a queue that loaded", () => {
    expect(getInboxPollingIntervalMs(true)).toBe(INBOX_POLLING_INTERVAL_MS);
  });

  it("does not poll a queue that has not loaded, such as after a 403", () => {
    expect(getInboxPollingIntervalMs(false)).toBe(false);
  });
});

describe("WORKSPACE_FALLBACK_POLLING_INTERVAL_MS", () => {
  it("never polls under 30 s, as the lead decided on 2026-11-13", () => {
    expect(WORKSPACE_FALLBACK_POLLING_INTERVAL_MS).toBeGreaterThanOrEqual(30_000);
  });
});

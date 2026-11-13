import { describe, expect, it } from "vitest";

import {
  getInboxPollingIntervalMs,
  getWorkspacePollingIntervalMs,
  INBOX_POLLING_INTERVAL_MS,
  WORKSPACE_POLLING_INTERVAL_MS,
} from "@/features/console-tickets/model/polling";
import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { readOperationExample } from "@/test/contract-examples";

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

describe("getWorkspacePollingIntervalMs", () => {
  it.each([
    ["suggestion-pending", WORKSPACE_POLLING_INTERVAL_MS],
    ["draft-ready", false],
    ["manual-mode", false],
  ] as const)("polls the %s example every %s ms", (name, interval) => {
    expect(
      getWorkspacePollingIntervalMs(
        toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name)),
      ),
    ).toBe(interval);
  });

  it("does not poll before the first load", () => {
    expect(getWorkspacePollingIntervalMs(undefined)).toBe(false);
  });
});

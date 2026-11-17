import { describe, expect, it } from "vitest";

import {
  getEmptyQueueText,
  getQueueLabel,
  getQueueOrderLabel,
  getQueueStatuses,
  parseQueueStatus,
} from "@/features/console-tickets/model/queue";
import { readBackendSchema, readEnumValues } from "@/test/contract-schemas";

describe("getQueueStatuses", () => {
  it("offers every status of the contract to a manager, in the order of the contract", () => {
    expect(getQueueStatuses("manager")).toEqual(
      readEnumValues(readBackendSchema("ConsoleTicketStatus")),
    );
  });

  it.each(["staff", "customer", "admin", "unknown"] as const)("offers Open only to %s", (role) => {
    expect(getQueueStatuses(role)).toEqual(["open"]);
  });
});

describe("parseQueueStatus", () => {
  it.each([
    ["the status of a queue of the role", "closed", "closed"],
    ["no status", null, "open"],
    ["an unknown status", "archived", "open"],
    ["an empty status", "", "open"],
  ])("reads %s as %s", (_case, value, status) => {
    expect(parseQueueStatus(value, getQueueStatuses("manager"))).toBe(status);
  });

  it("reads a status of a queue that the role does not have as Open", () => {
    expect(parseQueueStatus("escalated", getQueueStatuses("staff"))).toBe("open");
  });
});

describe("queue texts", () => {
  it.each([
    { status: "open", label: "Open", order: "Oldest first", empty: "No open tickets" },
    {
      status: "awaiting_approval",
      label: "Awaiting approval",
      order: "Oldest first",
      empty: "No tickets awaiting approval",
    },
    {
      status: "escalated",
      label: "Escalated",
      order: "Oldest first",
      empty: "No escalated tickets",
    },
    { status: "closed", label: "Closed", order: "Newest first", empty: "No closed tickets" },
  ] as const)("names the $status queue, its order, and its empty state", (queue) => {
    expect(getQueueLabel(queue.status)).toBe(queue.label);
    expect(getQueueOrderLabel(queue.status)).toBe(queue.order);
    expect(getEmptyQueueText(queue.status)).toBe(queue.empty);
  });
});

import { describe, expect, it } from "vitest";

import { buildQueueSearch, buildTicketPath } from "@/features/console-tickets/model/console-paths";

describe("buildQueueSearch", () => {
  it.each([
    ["open", ""],
    ["closed", "?status=closed"],
    ["awaiting_approval", "?status=awaiting_approval"],
  ] as const)("builds the search of the %s queue", (status, search) => {
    expect(buildQueueSearch(status)).toBe(search);
  });
});

describe("buildTicketPath", () => {
  it("keeps the queue of the inbox", () => {
    expect(buildTicketPath("TCK-1042", "escalated")).toBe(
      "/console/tickets/TCK-1042?status=escalated",
    );
  });

  it("encodes a ticket ID that is not safe in a path (CON-15)", () => {
    expect(buildTicketPath("TCK/1 2", "open")).toBe("/console/tickets/TCK%2F1%202");
  });
});

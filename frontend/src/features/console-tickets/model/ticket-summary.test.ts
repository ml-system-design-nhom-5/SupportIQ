import { describe, expect, it } from "vitest";

import type { TicketSummaryContract } from "@/features/console-tickets/api/contract-types";
import {
  toTicketSummary,
  toTicketSummaryPage,
} from "@/features/console-tickets/model/ticket-summary";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

/**
 * Read a ticket of a queue example.
 *
 * @param name - The example of `listConsoleTickets`.
 * @param index - The position of the ticket.
 * @returns The ticket.
 */
function readQueueItem(name: string, index: number): TicketSummaryContract {
  const item = readOperationExample("listConsoleTickets", 200, name).items[index];
  if (item === undefined) {
    throw new Error(`The example ${name} has no item ${String(index)}.`);
  }
  return item;
}

/** TCK-1042: nobody opened it yet, and its draft is ready. */
const readyTicket = readQueueItem("open-queue", 1);

/** TCK-1042 without its predicted intent and its draft status. */
const ticketWithoutAi = withoutMembers(readyTicket, ["predicted_intent", "draft_status"]);

describe("toTicketSummaryPage", () => {
  it("maps the open queue in the order of backend, with its cursor", () => {
    const page = toTicketSummaryPage(readOperationExample("listConsoleTickets", 200, "open-queue"));

    expect(page.tickets.map((ticket) => ticket.ticketId)).toEqual(["TCK-1038", "TCK-1042"]);
    expect(page.nextCursor).toBe("eyJ0IjoiMTA0MiJ9");
  });

  it("maps an empty queue without a cursor", () => {
    expect(toTicketSummaryPage(readOperationExample("listConsoleTickets", 200, "empty"))).toEqual({
      tickets: [],
    });
  });
});

describe("toTicketSummary", () => {
  it("maps a ticket with a predicted intent and a ready draft", () => {
    expect(toTicketSummary(readyTicket)).toEqual({
      ticketId: "TCK-1042",
      createdAt: "2026-11-05T08:12:30Z",
      customerName: "Lan Tran",
      excerpt: "I asked for a refund for the headphones three weeks ago. When will it be paid?",
      intent: { kind: "predicted", name: "Refund status", band: "high", probability: 0.88 },
      badge: { kind: "ai", status: "draft_ready" },
      isAuthorityRequired: false,
    });
  });

  it("says who opened a ticket and that it has no analysis after an AI failure", () => {
    const summary = toTicketSummary(readQueueItem("open-queue", 0));

    expect(summary.openedAt).toBe("2026-11-01T10:30:00Z");
    expect(summary.intent).toEqual({ kind: "none", text: "No analysis" });
    expect(summary.badge).toEqual({ kind: "ai", status: "unavailable" });
  });

  it.each([
    ["awaiting-approval", "awaiting_approval"],
    ["escalated", "escalated"],
    ["closed", "closed"],
  ] as const)("shows the ticket status of a ticket in the %s queue", (name, status) => {
    expect(toTicketSummary(readQueueItem(name, 0)).badge).toEqual({ kind: "ticket", status });
  });

  it("marks a ticket where authority is required", () => {
    expect(toTicketSummary(readQueueItem("awaiting-approval", 0)).isAuthorityRequired).toBe(true);
  });
});

describe("toTicketSummary without a predicted intent", () => {
  it("says that a manual ticket has no AI", () => {
    const summary = toTicketSummary({ ...ticketWithoutAi, handling_mode: "manual" });

    expect(summary.intent).toEqual({ kind: "none", text: "No AI (manual)" });
    expect(summary.badge).toEqual({ kind: "ai", status: "manual" });
  });

  it.each([
    ["pending", "Analysis in progress"],
    ["draft_ready", "Intent chosen by staff"],
  ] as const)("explains a missing intent when the draft is %s", (draftStatus, text) => {
    const summary = toTicketSummary({ ...ticketWithoutAi, draft_status: draftStatus });

    expect(summary.intent).toEqual({ kind: "none", text });
    expect(summary.badge).toEqual({ kind: "ai", status: draftStatus });
  });

  it("treats an assisted ticket without a draft status as unavailable", () => {
    const summary = toTicketSummary(ticketWithoutAi);

    expect(summary.intent).toEqual({ kind: "none", text: "No analysis" });
    expect(summary.badge).toEqual({ kind: "ai", status: "unavailable" });
  });

  it("stops at a ticket without its required members", () => {
    expect(() => {
      Reflect.apply(toTicketSummary, undefined, [{ ticket_id: "TCK-1" }]);
    }).toThrow("The response has no created_at.");
  });
});

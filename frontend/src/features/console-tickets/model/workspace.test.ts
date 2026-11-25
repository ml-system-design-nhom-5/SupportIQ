import { describe, expect, it } from "vitest";

import { toSuggestion, toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

describe("toTicketWorkspace", () => {
  it("maps the ticket, the customer, the message, the orders, and the suggestion", () => {
    const workspace = toTicketWorkspace(
      readOperationExample("getConsoleTicket", 200, "draft-ready"),
    );

    expect(workspace).toMatchObject({
      ticketId: "TCK-1042",
      status: "open",
      handlingMode: "assisted",
      isAuthorityRequired: false,
      createdAt: "2026-11-05T08:12:30Z",
      customerName: "Lan Tran",
      message: {
        body: "I asked for a refund for the headphones three weeks ago. When will it be paid?",
        createdAt: "2026-11-05T08:12:30Z",
      },
      order: { orderId: "ORD-20931" },
      otherOrders: [{ orderId: "ORD-20990" }],
      suggestion: {
        suggestionId: "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20",
        createdAt: "2026-11-05T08:12:30Z",
        analysis: { status: "ready" },
        draft: { status: "draft_ready" },
      },
    });
    expect(workspace).not.toHaveProperty("reply");
  });

  it("maps a manual ticket without an order, other orders, or a suggestion", () => {
    const workspace = toTicketWorkspace(
      readOperationExample("getConsoleTicket", 200, "manual-mode"),
    );

    expect(workspace.handlingMode).toBe("manual");
    expect(workspace.otherOrders).toEqual([]);
    expect(workspace).not.toHaveProperty("order");
    expect(workspace).not.toHaveProperty("suggestion");
  });
});

describe("toSuggestion", () => {
  it("maps the intent that staff chose", () => {
    expect(
      toSuggestion(readOperationExample("createSuggestion", 202, "intent-override")),
    ).toMatchObject({
      intentOverride: { label: "request_refund", name: "Request refund" },
      analysis: { status: "pending" },
      draft: { status: "pending" },
    });
  });
});

describe("toTicketWorkspace of the allowed actions", () => {
  it("maps the actions that the caller may take", () => {
    const workspace = toTicketWorkspace(
      readOperationExample("getConsoleTicket", 200, "authority-required"),
    );

    expect(workspace.allowedActions).toEqual(
      new Set(["submit_reply_proposal", "escalate", "correct_intent"]),
    );
  });
});

describe("toTicketWorkspace of a closed ticket", () => {
  it("maps the reply of a closed ticket", () => {
    const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, "closed"));

    expect(workspace.status).toBe("closed");
    expect(workspace.allowedActions).toEqual(new Set());
    expect(workspace.reply).toEqual({
      body: "Thank you for writing. Your refund request for the headphones is under review. We will write to you again when it is decided.",
      sentByName: "Mai Nguyen",
      sentAt: "2026-10-14T09:25:00Z",
    });
  });

  it("stops at a workspace without its required members", () => {
    const body = withoutMembers(readOperationExample("getConsoleTicket", 200, "draft-ready"), [
      "message",
    ]);

    expect(() => {
      Reflect.apply(toTicketWorkspace, undefined, [body]);
    }).toThrow("The response has no message.");
  });
});

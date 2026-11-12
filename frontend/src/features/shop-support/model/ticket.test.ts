import { describe, expect, it } from "vitest";

import { MESSAGE_MAX_LENGTH } from "@/features/shop-support/model/message-text";
import {
  buildTicketAnchorId,
  readAnchorIdOfHash,
  toShopTicket,
  toShopTicketPage,
  toShopTicketStatus,
} from "@/features/shop-support/model/ticket";
import { readOperationExample } from "@/test/contract-examples";

describe("readAnchorIdOfHash", () => {
  it("reads the element ID of a fragment", () => {
    expect(readAnchorIdOfHash("#ticket-TCK-1042")).toBe("ticket-TCK-1042");
  });

  it("decodes a fragment", () => {
    expect(readAnchorIdOfHash("#ticket-TCK%201042")).toBe("ticket-TCK 1042");
  });

  it.each(["", "#"])("names no element for the empty fragment %j", (hash) => {
    expect(readAnchorIdOfHash(hash)).toBeUndefined();
  });

  it("names no element for a malformed fragment, which must not break the page", () => {
    expect(readAnchorIdOfHash("#%E0%A4%A")).toBeUndefined();
  });
});

describe("toShopTicket", () => {
  it("maps a received ticket without a reply", () => {
    expect(toShopTicket(readOperationExample("getShopTicket", 200, "received"))).toEqual({
      ticketId: "TCK-1042",
      orderId: "ORD-20931",
      message: "I asked for a refund for the headphones three weeks ago. When will it be paid?",
      createdAt: "2026-11-05T08:12:30Z",
      status: "received",
    });
  });

  it("maps a replied ticket with its reply", () => {
    const ticket = toShopTicket(readOperationExample("getShopTicket", 200, "replied"));

    expect(ticket.status).toBe("replied");
    expect(ticket.reply).toEqual({
      body: "Thank you for writing. Your refund request for the headphones is under review. We will write to you again when it is decided.",
      sentAt: "2026-10-14T09:25:00Z",
    });
  });
});

describe("toShopTicketStatus", () => {
  it.each([
    ["received", "received"],
    ["replied", "replied"],
    ["closed", "received"],
    ["", "received"],
  ])("maps %j to %s, showing an unknown value as received (contract, CON-22)", (value, status) => {
    expect(toShopTicketStatus(value)).toBe(status);
  });
});

describe("toShopTicketPage", () => {
  it("keeps the cursor of the next page", () => {
    const page = toShopTicketPage(readOperationExample("listShopTickets", 200, "first-page"));

    expect(page.tickets.map((ticket) => ticket.ticketId)).toEqual(["TCK-1042", "TCK-1038"]);
    expect(page.nextCursor).toBe("eyJ0IjoiMTAzOCJ9");
  });

  it("has no cursor on the last page and maps an empty list", () => {
    expect(
      toShopTicketPage(readOperationExample("listShopTickets", 200, "last-page")),
    ).not.toHaveProperty("nextCursor");
    expect(toShopTicketPage(readOperationExample("listShopTickets", 200, "empty"))).toEqual({
      tickets: [],
    });
  });
});

describe("buildTicketAnchorId", () => {
  it("names the element of a ticket on its order page", () => {
    expect(buildTicketAnchorId("TCK-1042")).toBe("ticket-TCK-1042");
  });
});

describe("MESSAGE_MAX_LENGTH (MessageText)", () => {
  it("uses the maxLength of the contract", () => {
    expect(MESSAGE_MAX_LENGTH).toBe(2000);
  });
});

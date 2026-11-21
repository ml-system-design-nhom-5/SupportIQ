import { describe, expect, it } from "vitest";

import { supportQueryKeys } from "@/features/shop-support/api/support-query-keys";

describe("supportQueryKeys", () => {
  it("puts both ticket lists under one prefix, so one invalidation reloads both (TS-19)", () => {
    expect(supportQueryKeys.allTickets()).toEqual(["shop-support", "tickets", { orderId: null }]);
    expect(supportQueryKeys.ticketsOfOrder("ORD-1")).toEqual([
      "shop-support",
      "tickets",
      { orderId: "ORD-1" },
    ]);
    expect(supportQueryKeys.ticketLists()).toEqual(["shop-support", "tickets"]);
  });
});

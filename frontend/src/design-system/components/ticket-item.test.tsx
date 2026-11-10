import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { presentationByShopTicketStatus } from "@/design-system/components/status-presentations";
import { TicketItem } from "@/design-system/components/ticket-item";
import { renderUi } from "@/test/render-app";

describe("TicketItem", () => {
  it("shows a received ticket with the customer's message and the no-reply line", () => {
    renderUi(
      <ul aria-label="Tickets">
        <TicketItem
          anchorId="ticket-TCK-1042"
          ticketId="TCK-1042"
          status={presentationByShopTicketStatus.received}
          message="When will my refund be paid?"
          createdAt="2026-11-05T08:12:30Z"
        />
      </ul>,
    );

    const item = screen.getByRole("listitem");
    expect(item).toHaveAttribute("id", "ticket-TCK-1042");
    expect(within(item).getByText("TCK-1042")).toBeVisible();
    expect(within(item).getByText("Received")).toBeVisible();
    expect(within(item).getByText("When will my refund be paid?")).toBeVisible();
    expect(within(item).getByRole("button", { name: "47 minutes ago" })).toBeVisible();
    expect(
      within(item).getByText("No reply yet. A person from our support team replies here."),
    ).toBeVisible();
  });

  it("shows a replied ticket with the reply from support", () => {
    renderUi(
      <ul aria-label="Tickets">
        <TicketItem
          anchorId="ticket-TCK-1017"
          ticketId="TCK-1017"
          status={presentationByShopTicketStatus.replied}
          message="Can I return them?"
          createdAt="2026-10-13T16:45:10Z"
          reply={{ body: "Your refund request is under review.", sentAt: "2026-10-14T09:25:00Z" }}
        />
      </ul>,
    );

    expect(screen.getByText("Replied")).toBeVisible();
    expect(screen.getByText("Reply from support")).toBeVisible();
    expect(screen.getByText("Your refund request is under review.")).toBeVisible();
    expect(screen.queryByText(/No reply yet/)).not.toBeInTheDocument();
  });
});

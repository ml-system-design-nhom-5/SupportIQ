import { describe, expect, it } from "vitest";

import {
  authorityRequiredPresentation,
  presentationByAccountStatus,
  presentationByAiStatus,
  presentationByCompletedDraftStatus,
  presentationByConsoleTicketStatus,
  presentationByDocumentValidity,
  presentationByHandlingMode,
  presentationByInternalRole,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
  presentationByShopTicketStatus,
} from "@/design-system/components/status-presentations";

describe("shop status presentations (UI-12, shop UI design)", () => {
  it.each([
    ["placed", "neutral", "Placed"],
    ["processing", "info", "Processing"],
    ["shipped", "info", "Shipped"],
    ["delivered", "success", "Delivered"],
    ["cancelled", "neutral", "Cancelled"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)("presents the order status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByOrderStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["not_shipped", "neutral", "Not shipped"],
    ["in_transit", "info", "In transit"],
    ["delivered", "success", "Delivered"],
    ["delayed", "warning", "Delayed"],
    ["lost", "danger", "Lost"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)("presents the shipment status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByShipmentStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["requested", "info", "Refund requested"],
    ["under_review", "info", "Refund under review"],
    ["approved", "success", "Refund approved"],
    ["rejected", "danger", "Refund rejected"],
    ["paid", "success", "Refund paid"],
    ["none", "neutral", "No refund"],
    ["unknown", "neutral", "Refund status unknown"],
  ] as const)("presents the refund status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByRefundStatus[status]).toMatchObject({ tone, label });
  });
});

describe("ticket and account status presentations (UI-12, shop UI and admin UI designs)", () => {
  it.each([
    ["received", "info", "Received"],
    ["replied", "success", "Replied"],
  ] as const)("presents the ticket status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByShopTicketStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["staff", "neutral", "Staff"],
    ["manager", "info", "Manager"],
    ["admin", "neutral", "Admin"],
    ["unknown", "neutral", "Unknown role"],
  ] as const)("presents the role %s in the %s tone as %s", (role, tone, label) => {
    expect(presentationByInternalRole[role]).toMatchObject({ tone, label });
  });

  it.each([
    ["active", "success", "Active"],
    ["deactivated", "neutral", "Deactivated"],
  ] as const)("presents the account status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByAccountStatus[status]).toMatchObject({ tone, label });
  });
});

describe("console status presentations (UI-12, console UI design)", () => {
  it.each([
    ["open", "info", "Open"],
    ["awaiting_approval", "warning", "Awaiting approval"],
    ["escalated", "warning", "Escalated"],
    ["closed", "success", "Closed"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)("presents the ticket status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByConsoleTicketStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["pending", "info", "Generating draft"],
    ["draft_ready", "ai", "Draft ready"],
    ["abstained", "warning", "AI abstained"],
    ["escalation_recommended", "warning", "Escalation recommended"],
    ["unavailable", "danger", "AI unavailable"],
    ["manual", "neutral", "Manual handling"],
  ] as const)("presents the AI status %s in the %s tone as %s", (status, tone, label) => {
    expect(presentationByAiStatus[status]).toMatchObject({ tone, label });
  });

  it.each([
    ["assisted", "neutral", "Assisted"],
    ["manual", "neutral", "Manual handling"],
  ] as const)("presents the handling mode %s in the %s tone as %s", (mode, tone, label) => {
    expect(presentationByHandlingMode[mode]).toMatchObject({ tone, label });
  });

  it.each([
    ["valid", "success", "In effect"],
    ["expired", "warning", "Expired"],
    ["conflicting", "danger", "Conflicting"],
  ] as const)("presents the validity %s in the %s tone as %s", (validity, tone, label) => {
    expect(presentationByDocumentValidity[validity]).toMatchObject({ tone, label });
  });

  it("presents a ticket where authority is required in the warning tone", () => {
    expect(authorityRequiredPresentation).toMatchObject({
      tone: "warning",
      label: "Authority required",
    });
  });
});

describe("report status presentations (UI-12, UI-44)", () => {
  it.each([
    ["draft_ready", "ai", "Draft ready"],
    ["abstained", "warning", "AI abstained"],
    ["escalation_recommended", "warning", "Escalation recommended"],
    ["llm_unavailable", "danger", "LLM unavailable"],
    ["unavailable", "danger", "AI unavailable"],
    ["unknown", "neutral", "Status unknown"],
  ] as const)(
    "presents the completed draft status %s in the %s tone as %s",
    (status, tone, label) => {
      expect(presentationByCompletedDraftStatus[status]).toMatchObject({ tone, label });
    },
  );
});

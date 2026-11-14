import { describe, expect, it } from "vitest";

import { canChangeDraft, canEditProposal } from "@/features/console-tickets/model/composer-ticket";
import { readComposerTicket } from "@/test/console-screen";

/** The proposal of the awaiting-approval example. */
const PROPOSAL_ID = "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52";

describe("toComposerTicket of a ticket that awaits approval (FR-06)", () => {
  it("starts a manager from the proposal, with no warning to acknowledge", () => {
    const ticket = readComposerTicket("awaiting-approval");

    expect(ticket).toMatchObject({
      status: "awaiting_approval",
      draft: { kind: "reply_proposal", proposalId: PROPOSAL_ID },
      warningIds: [],
    });
    expect(ticket.draft?.text).toMatch(/^Hello Lan Tran, thank you for your patience\./);
  });

  it("lets the manager edit the proposal, but not staff", () => {
    expect(canEditProposal(readComposerTicket("awaiting-approval"))).toBe(true);
    expect(canEditProposal(readComposerTicket("read-only-for-staff"))).toBe(false);
    expect(canChangeDraft(readComposerTicket("awaiting-approval"))).toBe(false);
  });
});

describe("toComposerTicket of a reply without a draft", () => {
  it.each([
    ["manual-mode", "manual_handling"],
    ["ai-service-unavailable", "manual_handling"],
  ])("says where staff write on the %s example: %s", (name, situation) => {
    expect(readComposerTicket(name)).toMatchObject({ situation });
  });

  it("has no ready text on an escalated ticket without a ready draft", () => {
    const ticket = readComposerTicket("escalated");

    expect(ticket).toMatchObject({ status: "escalated", warningIds: [] });
    expect(ticket).not.toHaveProperty("draft");
    expect(ticket).not.toHaveProperty("situation");
  });

  it("starts from the AI draft on an open ticket", () => {
    expect(readComposerTicket("draft-ready")).not.toHaveProperty("situation");
    expect(canEditProposal(readComposerTicket("draft-ready"))).toBe(false);
  });
});

import { describe, expect, it } from "vitest";

import {
  toReplyProposal,
  toTicketEscalation,
} from "@/features/console-tickets/model/manager-handoff";
import { readOperationExample } from "@/test/contract-examples";

describe("toReplyProposal", () => {
  it("maps the proposal of the awaiting-approval example", () => {
    const { proposal } = readOperationExample("getConsoleTicket", 200, "awaiting-approval");
    const mapped = proposal === undefined ? undefined : toReplyProposal(proposal);

    expect(mapped).toMatchObject({
      proposalId: "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52",
      proposedByName: "Mai Nguyen",
      createdAt: "2026-11-06T09:12:40Z",
    });
    expect(mapped?.body).toMatch(/^Hello Lan Tran, thank you for your patience\./);
  });

  it("stops at a proposal without its body", () => {
    expect(() => {
      Reflect.apply(toReplyProposal, undefined, [{ proposal_id: "p1" }]);
    }).toThrow("The response has no body.");
  });
});

describe("toTicketEscalation", () => {
  it("maps the escalation of the escalated example, with its note", () => {
    const { escalation } = readOperationExample("getConsoleTicket", 200, "escalated");

    expect(escalation === undefined ? undefined : toTicketEscalation(escalation)).toEqual({
      reasonCodes: ["other"],
      note: "The customer asks to talk to a person.",
      escalatedByName: "Mai Nguyen",
      escalatedAt: "2026-11-06T11:41:00Z",
    });
  });

  it("has no note when staff wrote none", () => {
    const { note, ...withoutNote } = readOperationExample("createEscalation", 201, "escalated");

    expect(note).toBeDefined();
    expect(toTicketEscalation(withoutNote)).not.toHaveProperty("note");
  });
});

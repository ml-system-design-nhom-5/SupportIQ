import { describe, expect, it } from "vitest";

import {
  describeHandoffAuthor,
  toProposalBasis,
  toReplyProposal,
  toTicketEscalation,
} from "@/features/console-tickets/model/manager-handoff";
import { toStaffReasonCodes } from "@/features/console-tickets/model/staff-reason-codes";
import { readOperationExample } from "@/test/contract-examples";

describe("toReplyProposal", () => {
  it("maps the proposal of the awaiting-approval example", () => {
    const { proposal } = readOperationExample("getConsoleTicket", 200, "awaiting-approval");
    const mapped = proposal === undefined ? undefined : toReplyProposal(proposal);

    expect(mapped).toMatchObject({
      proposalId: "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52",
      basis: "ai_draft",
      reasonCodes: [],
      proposedBy: { accountId: "9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12", displayName: "Mai Nguyen" },
      createdAt: "2026-11-06T09:12:40Z",
    });
    expect(mapped).not.toHaveProperty("note");
    expect(mapped?.body).toMatch(/^Hello Lan Tran, thank you for your patience\./);
  });

  it("maps the reasons and the note of staff, in the order of the contract", () => {
    const { proposal } = readOperationExample("getConsoleTicket", 200, "awaiting-approval");
    const rejected =
      proposal === undefined
        ? undefined
        : toReplyProposal({
            ...proposal,
            basis: "rejected_ai_draft",
            staff_reason_codes: ["other", "kb_gap"],
            note: "The customer called us.",
          });

    expect(rejected).toMatchObject({
      basis: "rejected_ai_draft",
      reasonCodes: ["kb_gap", "other"],
      note: "The customer called us.",
    });
  });

  it("stops at a proposal without its body", () => {
    expect(() => {
      Reflect.apply(toReplyProposal, undefined, [{ proposal_id: "p1" }]);
    }).toThrow("The response has no body.");
  });
});

describe("toProposalBasis", () => {
  it.each([
    ["ai_draft", "ai_draft"],
    ["rejected_ai_draft", "rejected_ai_draft"],
    ["no_ai_draft", "no_ai_draft"],
    ["a_new_basis", "unknown"],
  ])("maps %s to %s (CON-22)", (value, basis) => {
    expect(toProposalBasis(value)).toBe(basis);
  });
});

describe("toTicketEscalation", () => {
  it("maps the escalation of the escalated example, with its note", () => {
    const { escalation } = readOperationExample("getConsoleTicket", 200, "escalated");

    expect(escalation === undefined ? undefined : toTicketEscalation(escalation)).toEqual({
      reasonCodes: ["other"],
      note: "The customer asks to talk to a person.",
      escalatedBy: { accountId: "9a7d3e21-6c4b-4f8e-b1a2-3c5d7e9f0a12", displayName: "Mai Nguyen" },
      escalatedAt: "2026-11-06T11:41:00Z",
    });
  });

  it("has no note when staff wrote none, which the contract allows without the code other", () => {
    const { note, ...withoutNote } = readOperationExample("createEscalation", 201, "escalated");

    expect(note).toBeDefined();
    expect(
      toTicketEscalation({ ...withoutNote, staff_reason_codes: ["missing_case_info"] }),
    ).not.toHaveProperty("note");
  });

  it("shows a reason code that this version does not know as unknown (CON-22)", () => {
    const escalation = readOperationExample("createEscalation", 201, "escalated");
    const codes: readonly string[] = ["kb_gap", "new_code"];

    expect(toTicketEscalation({ ...escalation, staff_reason_codes: [] }).reasonCodes).toEqual([]);
    expect(toStaffReasonCodes(codes)).toEqual(["kb_gap", "unknown"]);
  });
});

describe("describeHandoffAuthor", () => {
  const author = { accountId: "a1", displayName: "Minh Le" };

  it.each([
    ["the signed-in account", "a1", "Minh Le (you)"],
    ["another account", "a2", "Minh Le (staff)"],
    ["a session that is not known yet", undefined, "Minh Le (staff)"],
  ])("names the author for %s", (_case, signedInAccountId, name) => {
    expect(describeHandoffAuthor(author, signedInAccountId)).toBe(name);
  });
});

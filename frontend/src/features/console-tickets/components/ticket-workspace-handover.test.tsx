import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { consoleQueryKeys } from "@/features/console-tickets/api/console-query-keys";
import { createReplyProposalRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  openReplyArea,
  readSuggestionPart,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
  writeReply,
} from "@/test/console-screen";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer, holdAnswer } from "@/test/fake-backend";

/** The proposal text of the awaiting-approval example. */
const PROPOSAL_BODY =
  readOperationExample("getConsoleTicket", 200, "awaiting-approval").proposal?.body ?? "";

/** The authority-required ticket as a manager sees it while it is open. */
const authorityForManager = workspaceWith("authority-required", {
  allowed_actions: ["send_reply", "correct_intent"],
});

/** A suggestion part that is still pending. */
const pendingDraft = { draft_status: "pending" };

/** The ticket awaiting approval with a proposal that staff wrote after rejecting the AI draft. */
const awaitingWithReasons = workspaceWith("awaiting-approval", {
  proposal: {
    ...readOperationExample("getConsoleTicket", 200, "awaiting-approval").proposal,
    basis: "rejected_ai_draft",
    staff_reason_codes: ["kb_gap", "other"],
    note: "The customer called us about the label.",
  },
});

describe("What staff noted with a proposal (the lead's decision of 2026-11-14)", () => {
  it("shows a manager the basis, the reasons, and the note under the proposal", async () => {
    const { main } = await openReplyArea({ session: "manager", workspace: [awaitingWithReasons] });

    const proposal = within(main).getByRole("region", { name: "Staff proposal" });
    const noted = within(proposal).getByRole("region", { name: "What staff noted" });
    expect(noted).toHaveTextContent("Written after staff rejected the AI draft.");
    expect(noted).toHaveTextContent("KB gap");
    expect(noted).toHaveTextContent("Other");
    expect(noted).toHaveTextContent("The customer called us about the label.");
  });

  it("does not show it to staff", async () => {
    const { main } = await openReplyArea({
      workspace: [
        workspaceWith("read-only-for-staff", { proposal: readProposalOf(awaitingWithReasons) }),
      ],
    });

    expect(
      within(main).queryByRole("region", { name: "What staff noted" }),
    ).not.toBeInTheDocument();
    expect(main).not.toHaveTextContent("The customer called us about the label.");
  });
});

describe("A manager on a ticket whose proposal arrives (FR-06)", () => {
  it("sends the proposal that the screen shows, never the text typed before it arrived", async () => {
    const { user, main, backend, dependencies } = await openReplyArea({
      session: "manager",
      workspace: [authorityForManager, workspaceExample("awaiting-approval")],
      reply: [exampleAnswer(201, "sendReply", "from-reply-proposal")],
    });
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));
    await writeReply(user, main, " My own words.");

    await dependencies.queryClient.invalidateQueries({
      queryKey: consoleQueryKeys.workspace("TCK-1042"),
    });

    const proposal = await within(main).findByRole("region", { name: "Staff proposal" });
    expect(proposal).toHaveTextContent(PROPOSAL_BODY.slice(0, 40));
    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: /^Send this reply to / });
    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));
    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(sendReplyRoute)[0]?.body).toMatchObject({
      basis: "reply_proposal",
      body: PROPOSAL_BODY,
    });
  });

  it("names the staff member who proposed it, and keeps More in place, disabled", async () => {
    const { main } = await openReplyArea({
      session: "manager",
      workspace: [workspaceExample("awaiting-approval")],
    });

    expect(main).toHaveTextContent("Mai Nguyen (staff)");
    expect(within(main).getByRole("button", { name: "More actions" })).toBeDisabled();
  });
});

describe("The writes that hand a ticket to a manager", () => {
  it("disable Send reply and Escalate ticket while Submit for approval is sending", async () => {
    const held = holdAnswer(exampleAnswer(201, "createReplyProposal", "from-ai-draft"));
    const { user, main, backend } = await openReplyArea({ proposal: [held.answer] });
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));

    await user.click(within(main).getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /^Submit for approval/ }));

    await waitFor(() => {
      expect(backend.requestsTo(createReplyProposalRoute)).toHaveLength(1);
    });
    expect(main).toHaveTextContent("The reply is being submitted for approval.");
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Escalate ticket" })).toBeDisabled();
    held.release();
  });

  it("leave no editor after Escalate ticket, also over a ready draft", async () => {
    const escalatedWithDraft = workspaceWithSuggestion("escalated", {
      draft: readSuggestionPart("draft-ready", "draft"),
    });
    const { user, main } = await openReplyArea({
      workspace: [
        workspaceExample("draft-ready"),
        workspaceWith("escalated", { ...readBody(escalatedWithDraft), allowed_actions: [] }),
      ],
    });
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));
    await user.click(within(main).getByRole("button", { name: "Escalate ticket" }));
    const dialog = await screen.findByRole("dialog", { name: /^Escalate ticket / });
    await user.click(within(dialog).getByRole("button", { name: "KB gap" }));

    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    await within(main).findByRole("region", { name: "Escalated by Mai Nguyen (you)" });
    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
  });
});

describe("The main action while the AI works", () => {
  it("stays Submit for approval for staff on a ticket that requires authority", async () => {
    const { main } = await openReplyArea({
      workspace: [workspaceWithSuggestion("authority-required", { draft: pendingDraft })],
    });

    expect(within(main).getByRole("button", { name: "Submit for approval" })).toBeDisabled();
    expect(within(main).queryByRole("button", { name: "Send reply" })).not.toBeInTheDocument();
  });

  it("tells a manager on an escalated ticket that the AI works, not that it is read-only", async () => {
    const { main } = await openReplyArea({
      session: "manager",
      workspace: [workspaceWithSuggestion("escalated", { draft: pendingDraft })],
    });

    expect(main).toHaveTextContent("The AI is still working on this ticket.");
    expect(main).not.toHaveTextContent("read-only");
  });
});

/**
 * Read the body of a workspace answer, to change more of its members.
 *
 * @param answer - An answer with a body.
 * @returns Its members.
 */
function readBody(answer: ReturnType<typeof workspaceWith>): Readonly<Record<string, unknown>> {
  if (answer.kind !== "body" || typeof answer.body !== "object" || answer.body === null) {
    throw new Error("The answer has no body.");
  }
  return Object.fromEntries(Object.entries(answer.body));
}

/**
 * Read the proposal of a workspace answer, to put it on another ticket.
 *
 * @param answer - An answer with a body that has a proposal.
 * @returns The proposal.
 */
function readProposalOf(answer: ReturnType<typeof workspaceWith>): unknown {
  return readBody(answer)["proposal"];
}

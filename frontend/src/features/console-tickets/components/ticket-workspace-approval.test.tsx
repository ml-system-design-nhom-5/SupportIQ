import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createReplyProposalRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  DRAFT_READY_SUGGESTION_ID,
  openReplyArea,
  readDraftText,
  workspaceExample,
  writeReply,
} from "@/test/console-screen";
import { readOperationExample } from "@/test/contract-examples";
import { exampleAnswer } from "@/test/fake-backend";

/** The proposal of the awaiting-approval example. */
const PROPOSAL_ID = "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52";

/** The current suggestion of the authority-required example. */
const AUTHORITY_SUGGESTION_ID = "8d3a1e5c-7b9f-4a2d-8e6c-0f2b4d6a8c41";

/** A UUID in lowercase, as the contract requires of an `Idempotency-Key`. */
const idempotencyKeyPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("Submit for approval (FR-06, UI-16)", () => {
  it("replaces Send reply when authority is required, and submits the draft", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("authority-required"), workspaceExample("read-only-for-staff")],
    });
    expect(within(main).queryByRole("button", { name: "Send reply" })).not.toBeInTheDocument();
    expect(main).toHaveTextContent("A manager sends the reply on this ticket.");

    await user.click(within(main).getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => {
      expect(backend.requestsTo(createReplyProposalRoute)).toHaveLength(1);
    });
    const [request] = backend.requestsTo(createReplyProposalRoute);
    expect(request?.path).toBe("/v1/console/tickets/TCK-1042/reply-proposals");
    expect(request?.headers.get("Idempotency-Key")).toMatch(idempotencyKeyPattern);
    expect(request?.body).toEqual({
      basis: "ai_draft",
      body: readDraftText("authority-required"),
      suggestion_id: AUTHORITY_SUGGESTION_ID,
      acknowledged_warning_ids: [],
    });
    const heading = await within(main).findByRole("heading", { name: "Reply for approval" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
  });

  it("leaves no editor after an edited draft was submitted, on the same suggestion", async () => {
    const { user, main } = await openReplyArea({
      workspace: [workspaceExample("authority-required"), workspaceExample("read-only-for-staff")],
    });
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));
    await writeReply(user, main, " Thank you.");

    await user.click(within(main).getByRole("button", { name: "Submit for approval" }));

    const panel = await within(main).findByRole("region", { name: "Reply for approval" });
    expect(within(panel).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Edit proposal" })).toBeDisabled();
    expect(within(panel).queryByRole("button", { name: "Discard edits" })).not.toBeInTheDocument();
  });

  it("sits in the More menu when authority is not required", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));

    await user.click(within(main).getByRole("button", { name: "More actions" }));
    await user.click(await screen.findByRole("menuitem", { name: /^Submit for approval/ }));

    await waitFor(() => {
      expect(backend.requestsTo(createReplyProposalRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(createReplyProposalRoute)[0]?.body).toMatchObject({
      basis: "ai_draft",
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      acknowledged_warning_ids: ["w1"],
    });
  });

  it("is a visible button in manual handling, enabled once there is a reply", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("manual-mode")],
    });
    const submit = within(main).getByRole("button", { name: "Submit for approval" });
    expect(submit).toBeDisabled();
    expect(main).toHaveTextContent("Write a reply to send it or to submit it for approval.");

    await writeReply(user, main, "Here is the return label.");
    await user.click(submit);

    await waitFor(() => {
      expect(backend.requestsTo(createReplyProposalRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(createReplyProposalRoute)[0]?.body).toEqual({
      basis: "no_ai_draft",
      body: "Here is the return label.",
    });
  });

  it("says what happened after a refusal, keeps the text, and reloads the ticket", async () => {
    const { user, main } = await openReplyArea({
      workspace: [workspaceExample("manual-mode")],
      proposal: [exampleAnswer(403, "problems", "forbidden-role")],
    });
    await writeReply(user, main, "Here is the return label.");

    await user.click(within(main).getByRole("button", { name: "Submit for approval" }));

    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The reply was not submitted. A colleague escalated this ticket or submitted it for approval.",
    );
    expect(within(main).getByRole("textbox", { name: "Reply to the customer" })).toHaveValue(
      "Here is the return label.",
    );
  });

  it("reuses its key when the same reply is submitted again after an unknown outcome", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("manual-mode")],
      proposal: [
        { kind: "network_error" },
        exampleAnswer(201, "createReplyProposal", "without-ai-draft"),
      ],
    });
    await writeReply(user, main, "Here is the return label.");
    const submit = within(main).getByRole("button", { name: "Submit for approval" });

    await user.click(submit);
    expect(await within(main).findByRole("alert")).toHaveTextContent(
      "The reply may have been submitted.",
    );
    await user.click(submit);

    await waitFor(() => {
      expect(backend.requestsTo(createReplyProposalRoute).length).toBeGreaterThanOrEqual(2);
    });
    const keys = new Set(
      backend
        .requestsTo(createReplyProposalRoute)
        .map((request) => request.headers.get("Idempotency-Key")),
    );
    expect(keys.size).toBe(1);
  });
});

describe("A ticket awaiting approval", () => {
  it("lets a manager send the proposal as is with the basis reply_proposal", async () => {
    const { user, main, backend } = await openReplyArea({
      session: "manager",
      workspace: [workspaceExample("awaiting-approval")],
      reply: [exampleAnswer(201, "sendReply", "from-reply-proposal")],
    });
    const panel = within(main).getByRole("region", { name: "Reply for approval" });
    expect(within(panel).getByRole("region", { name: "Staff proposal" })).toBeVisible();
    expect(within(panel).getByRole("region", { name: "AI draft for comparison" })).toBeVisible();
    expect(main).toHaveTextContent(
      "Reject draft and Escalate ticket are not available while the ticket awaits approval.",
    );

    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: /^Send this reply to / });
    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
      basis: "reply_proposal",
      body: readProposalBody(),
      proposal_id: PROPOSAL_ID,
    });
  });

  it("lets a manager edit the proposal and send the edited text", async () => {
    const { user, main, backend } = await openReplyArea({
      session: "manager",
      workspace: [workspaceExample("awaiting-approval")],
      reply: [exampleAnswer(201, "sendReply", "from-reply-proposal")],
    });

    await user.click(within(main).getByRole("button", { name: "Edit proposal" }));
    const editor = within(main).getByRole("textbox", { name: "Reply to the customer" });
    expect(editor).toHaveValue(readProposalBody());
    await user.clear(editor);
    await user.type(editor, "The edited reply.");
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: /^Send this reply to / });
    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
      basis: "reply_proposal",
      body: "The edited reply.",
      proposal_id: PROPOSAL_ID,
    });
  });

  it("is read-only for staff, with every action disabled and the reason", async () => {
    const { main } = await openReplyArea({ workspace: [workspaceExample("read-only-for-staff")] });

    expect(main).toHaveTextContent("This ticket is read-only for you. A manager sends the reply.");
    expect(main).toHaveTextContent("Waiting for a manager");
    for (const name of ["Edit proposal", "Reject draft", "Escalate ticket", "Send reply"]) {
      expect(within(main).getByRole("button", { name })).toBeDisabled();
    }
  });
});

/**
 * Read the text of the proposal of the awaiting-approval example.
 *
 * @returns The text that a manager sends as is.
 */
function readProposalBody(): string {
  return readOperationExample("getConsoleTicket", 200, "awaiting-approval").proposal?.body ?? "";
}

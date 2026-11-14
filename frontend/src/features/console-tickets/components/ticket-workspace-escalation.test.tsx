import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { createEscalationRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  DRAFT_READY_SUGGESTION_ID,
  openReplyArea,
  readSuggestionPart,
  workspaceExample,
  workspaceWith,
  workspaceWithSuggestion,
  writeReply,
} from "@/test/console-screen";
import { exampleAnswer } from "@/test/fake-backend";

/** The name of the dialog on TCK-1042. */
const DIALOG_NAME = "Escalate ticket TCK-1042 to a manager?";

/** The current suggestion of the escalated example. */
const ESCALATED_SUGGESTION_ID = "5a7c9e1b-3d5f-4a7c-9e1b-3d5f7a9c1e64";

/** The escalated ticket as staff see it after they escalated it: read-only. */
const escalatedForStaff = workspaceWith("escalated", { allowed_actions: [] });

/**
 * Open the dialog of the draft-ready ticket.
 *
 * @param answers - The answers that differ, such as those of `createEscalation`.
 * @returns The rendered app, the `main` landmark, and the dialog.
 */
async function openDialog(answers: Parameters<typeof openReplyArea>[0] = {}) {
  const rendered = await openReplyArea({
    workspace: [workspaceExample("draft-ready"), escalatedForStaff],
    ...answers,
  });
  await rendered.user.click(within(rendered.main).getByRole("button", { name: "Escalate ticket" }));
  const dialog = await screen.findByRole("dialog", { name: DIALOG_NAME });
  return { ...rendered, dialog };
}

describe("Escalate ticket (ADR-0006)", () => {
  it("asks for a reason first, and sends nothing without one", async () => {
    const { user, dialog, backend } = await openDialog();

    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    expect(within(dialog).getByRole("alert")).toHaveTextContent("Choose at least one reason.");
    expect(backend.requestsTo(createEscalationRoute)).toHaveLength(0);
  });

  it("escalates with the reason and the suggestion, and moves the focus to the escalation", async () => {
    const { user, main, dialog, backend } = await openDialog();

    await user.click(within(dialog).getByRole("button", { name: "Missing case info" }));
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    await waitFor(() => {
      expect(backend.requestsTo(createEscalationRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(createEscalationRoute)[0]?.body).toEqual({
      staff_reason_codes: ["missing_case_info"],
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
    });
    await waitFor(() => {
      expect(dialog).not.toBeInTheDocument();
    });
    const heading = await within(main).findByRole("heading", {
      name: "Escalated by Mai Nguyen (you)",
    });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(main).toHaveTextContent("This ticket is read-only for you. A manager sends the reply.");
  });

  it("asks for a note with the reason Other, and sends it", async () => {
    const { user, dialog, backend } = await openDialog();
    await user.click(within(dialog).getByRole("button", { name: "Other" }));
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));
    expect(
      within(dialog).getByRole("textbox", { name: "Note (required with Other)" }),
    ).toBeInvalid();

    await user.type(
      within(dialog).getByRole("textbox", { name: "Note (required with Other)" }),
      "The customer called.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    await waitFor(() => {
      expect(backend.requestsTo(createEscalationRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(createEscalationRoute)[0]?.body).toMatchObject({
      staff_reason_codes: ["other"],
      note: "The customer called.",
    });
  });

  it("stays open after an unknown outcome, and escalates again with the same key", async () => {
    const { user, dialog, backend } = await openDialog({
      escalation: [{ kind: "network_error" }, exampleAnswer(201, "createEscalation", "escalated")],
    });
    await user.click(within(dialog).getByRole("button", { name: "KB gap" }));
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "The ticket may have been escalated.",
    );
    await user.click(within(dialog).getByRole("button", { name: "Escalate ticket" }));

    await waitFor(() => {
      expect(backend.requestsTo(createEscalationRoute).length).toBeGreaterThanOrEqual(2);
    });
    const keys = new Set(
      backend
        .requestsTo(createEscalationRoute)
        .map((request) => request.headers.get("Idempotency-Key")),
    );
    expect(keys.size).toBe(1);
  });

  it("is disabled when backend does not allow it", async () => {
    const { main } = await openReplyArea({
      session: "manager",
      workspace: [workspaceExample("awaiting-approval")],
    });

    expect(within(main).getByRole("button", { name: "Escalate ticket" })).toBeDisabled();
  });
});

describe("An escalated ticket", () => {
  it("shows a manager the reasons and the note above the editor, and sends no_ai_draft", async () => {
    const { user, main, backend } = await openReplyArea({
      session: "manager",
      workspace: [workspaceExample("escalated")],
    });
    const escalation = within(main).getByRole("region", {
      name: "Escalated by Mai Nguyen (staff)",
    });
    expect(escalation).toHaveTextContent("Other");
    expect(escalation).toHaveTextContent("The customer asks to talk to a person.");
    expect(main).toHaveTextContent("Write a reply to send it.");

    await writeReply(user, main, "A manager will call you today.");
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: /^Send this reply to / });
    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
    });
    expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
      basis: "no_ai_draft",
      body: "A manager will call you today.",
      suggestion_id: ESCALATED_SUGGESTION_ID,
    });
  });

  it("shows the escalation above a ready draft, which the reply is based on", async () => {
    const { main } = await openReplyArea({
      session: "manager",
      workspace: [
        workspaceWithSuggestion("escalated", { draft: readSuggestionPart("draft-ready", "draft") }),
      ],
    });

    expect(
      within(main).getByRole("region", { name: "Escalated by Mai Nguyen (staff)" }),
    ).toBeVisible();
    expect(within(main).getByRole("region", { name: "AI draft" })).toBeVisible();
  });
});

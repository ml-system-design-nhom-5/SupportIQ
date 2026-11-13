import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { sendReplyRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  readDraftText,
  TICKET_PATH,
  workspaceExample,
} from "@/test/console-screen";

/** The current suggestion of the draft-ready example. */
const SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";

/** A UUID in lowercase, as the contract requires of an `Idempotency-Key`. */
const idempotencyKeyPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/**
 * Open the workspace of TCK-1042 and wait for its reply area.
 *
 * @param answers - The answers that differ from the defaults: the draft-ready workspace.
 * @returns The rendered app and the `main` landmark.
 */
async function openReplyArea(answers: ConsoleAnswers = {}) {
  const rendered = openConsole(TICKET_PATH, answers);
  await screen.findByRole("heading", { level: 1, name: /^Ticket / });
  return { ...rendered, main: screen.getByRole("main") };
}

/**
 * Send the reply on the screen: Send reply, then the Send reply of the confirmation.
 *
 * @param user - The user of the test.
 * @param main - The `main` landmark.
 */
async function sendAndConfirm(user: UserEvent, main: HTMLElement): Promise<void> {
  await user.click(within(main).getByRole("button", { name: "Send reply" }));
  const dialog = await screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });
  await user.click(within(dialog).getByRole("button", { name: "Send reply" }));
}

describe("Send reply of a ready draft (UI-17, UI-18)", () => {
  it("stays disabled until the warning is acknowledged, and says why", async () => {
    const { user, main } = await openReplyArea();
    const send = within(main).getByRole("button", { name: "Send reply" });
    expect(send).toBeDisabled();
    expect(main).toHaveTextContent("Acknowledge 1 warning to send the reply.");

    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));

    expect(send).toBeEnabled();
    expect(main).not.toHaveTextContent("Acknowledge 1 warning");
  });

  it("sends the draft as is with the basis ai_draft, only after the confirmation", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));
    await user.click(within(main).getByRole("button", { name: "Send reply" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Send this reply to Lan Tran?" });
    expect(dialog).toHaveTextContent("A sent reply cannot be changed.");
    expect(backend.requestsTo(sendReplyRoute)).toHaveLength(0);

    await user.click(within(dialog).getByRole("button", { name: "Send reply" }));

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)).toHaveLength(1);
    });
    const [request] = backend.requestsTo(sendReplyRoute);
    expect(request?.path).toBe("/v1/console/tickets/TCK-1042/replies");
    expect(request?.headers.get("Idempotency-Key")).toMatch(idempotencyKeyPattern);
    expect(request?.body).toEqual({
      basis: "ai_draft",
      body: readDraftText("draft-ready"),
      suggestion_id: SUGGESTION_ID,
      acknowledged_warning_ids: ["w1"],
    });
  });

  it("sends nothing after Keep editing, and returns the focus to Send reply", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));
    await user.click(within(main).getByRole("button", { name: "Send reply" }));

    await user.click(await screen.findByRole("button", { name: "Keep editing" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(within(main).getByRole("button", { name: "Send reply" })).toHaveFocus();
    expect(backend.requestsTo(sendReplyRoute)).toHaveLength(0);
  });

  it("shows the sent reply once the ticket loads again", async () => {
    const { user, main } = await openReplyArea({
      workspace: [workspaceExample("draft-ready"), workspaceExample("closed")],
    });
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));

    await sendAndConfirm(user, main);

    expect(await within(main).findByRole("region", { name: "Reply sent" })).toBeVisible();
  });
});

describe("Edit draft", () => {
  it("puts the draft's text in the editor and sends the edited text with the basis ai_draft", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));
    const editor = within(main).getByRole("textbox", { name: "Reply to the customer" });
    expect(editor).toHaveValue(readDraftText("draft-ready"));
    expect(main).toHaveTextContent("Edited text is not checked against the sources.");

    await user.clear(editor);
    await user.type(editor, "Your refund is under review.");
    await user.click(within(main).getByRole("checkbox", { name: /^I have checked this/ }));
    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)[0]?.body).toMatchObject({
        basis: "ai_draft",
        body: "Your refund is under review.",
      });
    });
  });

  it("goes back to the draft with Discard edits", async () => {
    const { user, main } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Edit draft" }));

    await user.click(within(main).getByRole("button", { name: "Discard edits" }));

    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(main).getByRole("region", { name: "AI draft" })).toBeVisible();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { createSuggestionRoute, sendReplyRoute } from "@/test/backend-routes";
import {
  type ConsoleAnswers,
  openConsole,
  TICKET_PATH,
  workspaceExample,
} from "@/test/console-screen";

/** The current suggestion of the draft-ready example. */
const SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";

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
 * Write a reply in the editor.
 *
 * @param user - The user of the test.
 * @param main - The `main` landmark.
 * @param text - The reply.
 */
async function writeReply(user: UserEvent, main: HTMLElement, text: string): Promise<void> {
  await user.type(within(main).getByRole("textbox", { name: "Reply to the customer" }), text);
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

describe("Reject draft (ADR-0006)", () => {
  it("needs a reason code, and sends the basis rejected_ai_draft with it", async () => {
    const { user, main, backend } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Reject draft" }));
    const rejected = within(main).getByRole("region", { name: "Draft rejected" });
    expect(rejected).toHaveTextContent("Rejected");
    await writeReply(user, main, "Your refund is under review.");
    expect(main).toHaveTextContent("Choose why you rejected the draft to send the reply.");

    await user.click(within(rejected).getByRole("button", { name: "Unsupported claim" }));
    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
        basis: "rejected_ai_draft",
        body: "Your refund is under review.",
        suggestion_id: SUGGESTION_ID,
        staff_reason_codes: ["unsupported_claim"],
      });
    });
  });

  it("asks for a note with the reason code Other", async () => {
    const { user, main } = await openReplyArea();
    await user.click(within(main).getByRole("button", { name: "Reject draft" }));
    await writeReply(user, main, "Your refund is under review.");

    await user.click(within(main).getByRole("button", { name: "Other" }));

    expect(main).toHaveTextContent("Write a note for the reason Other to send the reply.");
    await user.type(within(main).getByRole("textbox", { name: "Note for the reason Other" }), "x");
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeEnabled();
  });
});

describe("A reply without a draft", () => {
  it("highlights a placeholder and keeps Send reply disabled until it is replaced (UI-43)", async () => {
    const { user, main } = await openReplyArea({ workspace: [workspaceExample("manual-mode")] });
    // user-event reads "[[" as one "[".
    await writeReply(user, main, "We sent the label to [[EMAIL].");

    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(main).toHaveTextContent("Replace the highlighted text to send the reply.");
    expect(main).toHaveTextContent("Personal data or reserved text: replace before sending.");
    expect(within(main).getByText("[EMAIL]").tagName).toBe("MARK");

    await user.clear(within(main).getByRole("textbox", { name: "Reply to the customer" }));
    await writeReply(user, main, "We sent the label to your email address.");
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeEnabled();
  });

  it("sends the basis no_ai_draft without a suggestion in manual mode", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("manual-mode")],
    });
    await writeReply(user, main, "Here is the return label.");

    await sendAndConfirm(user, main);

    await waitFor(() => {
      expect(backend.requestsTo(sendReplyRoute)[0]?.body).toEqual({
        basis: "no_ai_draft",
        body: "Here is the return label.",
      });
    });
  });

  it("retries the AI with Try AI again after an AI failure (UI-26)", async () => {
    const { user, main, backend } = await openReplyArea({
      workspace: [workspaceExample("ai-service-unavailable")],
      suggestion: [{ kind: "example", status: 202, folder: "createSuggestion", name: "retry" }],
    });

    await user.click(within(main).getByRole("button", { name: "Try AI again" }));

    await waitFor(() => {
      expect(backend.requestsTo(createSuggestionRoute)[0]?.body).toEqual({});
    });
  });
});

describe("Send reply while no draft is ready", () => {
  it.each([
    ["suggestion-pending", "The AI is still working on this ticket."],
    ["abstained-low-confidence", "Choose an intent to get a draft."],
  ])("is disabled on the %s example, with Edit draft and Reject draft", async (name, reason) => {
    const { main } = await openReplyArea({ workspace: [workspaceExample(name)] });

    expect(main).toHaveTextContent(reason);
    expect(within(main).getByRole("button", { name: "Send reply" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Edit draft" })).toBeDisabled();
    expect(within(main).getByRole("button", { name: "Reject draft" })).toBeDisabled();
    expect(within(main).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("is absent on a closed ticket, which shows the sent reply", async () => {
    const { main } = await openReplyArea({ workspace: [workspaceExample("closed")] });

    expect(within(main).getByRole("region", { name: "Reply sent" })).toBeVisible();
    expect(within(main).queryByRole("button", { name: "Send reply" })).not.toBeInTheDocument();
  });
});
